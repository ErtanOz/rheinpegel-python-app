from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from httpx import ASGITransport, AsyncClient

from app import main
from app.fetcher import FetchResult
from app.models import Measurement, Trend


class FakeService:
    def __init__(self) -> None:
        self._tz = ZoneInfo("Europe/Berlin")
        self._history: list[Measurement] = [
            Measurement(level_cm=400, timestamp=datetime.now(self._tz) - timedelta(minutes=10), trend=Trend.STABLE)
        ]
        self.refresh_seconds = 120

    async def start(self) -> None:  # pragma: no cover - noop for tests
        return None

    async def stop(self) -> None:  # pragma: no cover - noop for tests
        return None

    def is_running(self) -> bool:
        return True

    async def fetch_and_update(self, *, force_demo: bool = False) -> FetchResult:
        base = self._history[-1].level_cm
        level = base + (3 if force_demo else 1)
        measurement = Measurement(
            level_cm=level,
            timestamp=datetime.now(self._tz),
            trend=Trend.RISING if level > base else Trend.STABLE,
            is_demo=force_demo,
        )
        self._history.append(measurement)
        return FetchResult(measurement=measurement, latency_ms=42.0, is_demo=force_demo)

    async def latest(self) -> Measurement | None:
        return self._history[-1]

    async def history(self) -> list[Measurement]:
        return list(self._history[-5:])


@pytest.fixture
async def test_client(monkeypatch) -> AsyncClient:
    fake_service = FakeService()
    monkeypatch.setattr(main, "service", fake_service)
    main.app.dependency_overrides[main.get_service] = lambda: fake_service
    transport = ASGITransport(app=main.app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    main.app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_api_latest_returns_measurement(test_client: AsyncClient) -> None:
    response = await test_client.get("/api/latest")
    assert response.status_code == 200
    payload = response.json()
    assert payload["measurement"]["level_cm"] >= 401
    assert payload["history"]
    assert payload["latency_ms"] == 42.0


@pytest.mark.asyncio
async def test_api_history_returns_entries(test_client: AsyncClient) -> None:
    response = await test_client.get("/api/history")
    assert response.status_code == 200
    payload = response.json()
    assert "data" in payload
    assert len(payload["data"]) <= 5
