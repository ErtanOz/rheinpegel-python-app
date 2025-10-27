from __future__ import annotations

from prometheus_client import Counter, Gauge, Histogram

FETCH_LATENCY_HIST = Histogram(
    "rheinpegel_fetch_latency_seconds",
    "Latency for Rheinpegel upstream fetch operations",
)
FETCH_LAST_LATENCY = Gauge(
    "rheinpegel_fetch_last_latency_seconds",
    "Most recent upstream fetch latency in seconds",
)
FETCH_OUTCOME_COUNTER = Counter(
    "rheinpegel_fetch_total",
    "Count of Rheinpegel upstream fetch attempts by outcome",
    labelnames=("outcome",),
)
DATA_AGE_GAUGE = Gauge(
    "rheinpegel_data_age_seconds",
    "Age of the latest Rheinpegel measurement in seconds",
)
BACKGROUND_LOOP_GAUGE = Gauge(
    "rheinpegel_background_loop_running",
    "Indicates whether the background polling task is running",
)


def record_fetch(latency_ms: float | None, outcome: str) -> None:
    if latency_ms is not None:
        latency_seconds = latency_ms / 1000.0
        FETCH_LATENCY_HIST.observe(latency_seconds)
        FETCH_LAST_LATENCY.set(latency_seconds)
    FETCH_OUTCOME_COUNTER.labels(outcome=outcome).inc()


def set_data_age(age_seconds: float | None) -> None:
    if age_seconds is None:
        DATA_AGE_GAUGE.set(float("nan"))
    else:
        DATA_AGE_GAUGE.set(max(0.0, age_seconds))


def set_background_state(running: bool) -> None:
    BACKGROUND_LOOP_GAUGE.set(1.0 if running else 0.0)
