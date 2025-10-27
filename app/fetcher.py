from __future__ import annotations

import asyncio
import logging
import random
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx
from dateutil import parser as date_parser
from defusedxml import ElementTree as ET

from .config import Settings
from .models import Measurement, resolve_trend

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 4
BASE_BACKOFF = 0.5
TIMEOUT_SECONDS = 8.0

LEVEL_KEYS = ("level", "levelcm", "pegel", "wasserstand", "value", "stand")
TIME_KEYS = (
    "timestamp",
    "zeit",
    "time",
    "datetime",
    "datum",
    "messzeit",
    "uhrzeit",
)
TREND_KEYS = ("trend", "tendency", "richtung")


@dataclass(slots=True)
class FetchResult:
    measurement: Measurement
    latency_ms: float | None
    is_demo: bool
    error: str | None = None


class FetchError(Exception):
    """Raised when fetching from the remote source fails."""


async def fetch_latest(
    settings: Settings,
    previous: Measurement | None,
    *,
    force_demo: bool = False,
) -> FetchResult:
    if force_demo:
        measurement = _generate_demo(previous, settings)
        return FetchResult(measurement=measurement, latency_ms=None, is_demo=True)

    try:
        measurement, latency = await _fetch_from_source(settings, previous)
        return FetchResult(measurement=measurement, latency_ms=latency, is_demo=False)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falling back to demo mode due to: %s", exc)
        measurement = _generate_demo(previous, settings)
        return FetchResult(
            measurement=measurement,
            latency_ms=None,
            is_demo=True,
            error=str(exc),
        )


async def _fetch_from_source(
    settings: Settings,
    previous: Measurement | None,
) -> tuple[Measurement, float]:
    url = str(settings.source_url)
    timeout = httpx.Timeout(TIMEOUT_SECONDS)

    async with httpx.AsyncClient(timeout=timeout) as client:
        last_error: Exception | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            start = time.perf_counter()
            try:
                response = await client.get(url)
                elapsed_ms = (time.perf_counter() - start) * 1000
                response.raise_for_status()
                measurement = _parse_response(response, settings, previous)
                return measurement, elapsed_ms
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                delay = BASE_BACKOFF * 2 ** (attempt - 1)
                logger.debug(
                    "Fetch attempt %s failed (%s); retrying in %.2fs",
                    attempt,
                    exc,
                    delay,
                )
                if attempt == MAX_ATTEMPTS:
                    break
                await asyncio.sleep(delay)

        raise FetchError(f"Failed to fetch data from {url}") from last_error


def _parse_response(
    response: httpx.Response,
    settings: Settings,
    previous: Measurement | None,
) -> Measurement:
    content_type = response.headers.get("content-type", "").lower()

    if "json" in content_type:
        payload = response.json()
        return _build_measurement_from_payload(payload, settings, previous)

    text = response.text
    # Try JSON first regardless of header to be robust
    try:
        payload = response.json()
        return _build_measurement_from_payload(payload, settings, previous)
    except Exception:  # noqa: BLE001
        pass

    return _build_measurement_from_xml(text, settings, previous)


def _build_measurement_from_payload(
    payload: Any,
    settings: Settings,
    previous: Measurement | None,
) -> Measurement:
    record = _select_record(payload)
    if record is None:
        raise ValueError("No valid record found in payload")

    normalized = {str(k).lower(): v for k, v in record.items()}
    level_cm = _extract_level(normalized)
    timestamp = _extract_timestamp(normalized, settings)
    provided_trend = _extract_trend(normalized)

    trend = resolve_trend(level_cm, provided_trend, previous)
    return Measurement(level_cm=level_cm, timestamp=timestamp, trend=trend)


def _build_measurement_from_xml(
    text: str,
    settings: Settings,
    previous: Measurement | None,
) -> Measurement:
    root = ET.fromstring(text)

    flat: dict[str, Any] = {}
    for element in root.iter():
        if element.text and element.text.strip():
            flat[element.tag.lower()] = element.text.strip()
        for key, value in element.attrib.items():
            flat[f"{element.tag.lower()}_{key.lower()}"] = value

    if not flat:
        raise ValueError("XML payload did not contain any usable data")

    level_cm = _extract_level(flat)
    timestamp = _extract_timestamp(flat, settings)
    provided_trend = _extract_trend(flat)
    trend = resolve_trend(level_cm, provided_trend, previous)
    return Measurement(level_cm=level_cm, timestamp=timestamp, trend=trend)


def _select_record(payload: Any) -> dict[str, Any] | None:
    if isinstance(payload, dict):
        if any(isinstance(v, (dict, list)) for v in payload.values()):
            for key in ("latest", "current", "data", "value", "measurement", "item", "werte"):
                if key in payload:
                    nested = _select_record(payload[key])
                    if nested:
                        return nested
        return payload

    if isinstance(payload, list):
        for item in reversed(payload):
            nested = _select_record(item)
            if nested:
                return nested
    return None


def _extract_level(data: dict[str, Any]) -> int:
    for key in LEVEL_KEYS:
        if key in data:
            value = data[key]
            numeric = _coerce_float(value)
            if numeric is not None:
                # Values below 20 are likely metres; convert to centimetres.
                if numeric < 20:
                    numeric *= 100
                return max(0, int(round(numeric)))
    raise ValueError("Could not determine level value")


def _extract_timestamp(data: dict[str, Any], settings: Settings) -> datetime:
    tz = settings.timezone

    # Handle separate date/time fields (e.g. Datum + Uhrzeit)
    date_value = data.get("datum") or data.get("date")
    time_value = (
        data.get("uhrzeit")
        or data.get("zeit")
        or data.get("time")
        or data.get("messzeit")
    )
    if date_value and time_value:
        combined = f"{date_value} {time_value}"
        parsed = _coerce_datetime(combined, tz)
        if parsed is not None:
            return parsed

    for key in TIME_KEYS:
        if key in data and data[key] is not None:
            value = data[key]
            parsed = _coerce_datetime(value, tz)
            if parsed is not None:
                return parsed
    return datetime.now(tz)


def _extract_trend(data: dict[str, Any]) -> int | None:
    for key in TREND_KEYS:
        if key in data:
            raw = data[key]
            if raw is None:
                continue
            if isinstance(raw, (int, float)) and raw in (-1, 0, 1):
                return int(raw)
            text = str(raw).strip().lower()
            if text in {"-1", "falling", "down", "sinkend"}:
                return -1
            if text in {"1", "rising", "up", "steigend"}:
                return 1
            if text in {"0", "stable", "gleich", "steady"}:
                return 0
    return None


def _coerce_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def _coerce_datetime(value: Any, tz) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        # Assume Unix timestamp (seconds)
        return datetime.fromtimestamp(float(value), tz=tz)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = date_parser.parse(text)
    except (ValueError, TypeError) as exc:
        logger.debug("Failed to parse datetime %s: %s", value, exc)
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=tz)
    return parsed.astimezone(tz)


def _generate_demo(previous: Measurement | None, settings: Settings) -> Measurement:
    base = previous.level_cm if previous else 380
    jitter = random.randint(-10, 10)
    drift = random.choice([-3, -2, -1, 0, 1, 2, 3])
    level = max(250, min(900, base + drift + jitter))
    timestamp = datetime.now(settings.timezone)
    trend = resolve_trend(level, None, previous)
    return Measurement(level_cm=level, timestamp=timestamp, trend=trend, is_demo=True)
