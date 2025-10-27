from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from app.config import Settings
from app.fetcher import _build_measurement_from_payload, _build_measurement_from_xml
from app.models import Measurement, Trend


@pytest.fixture
def settings() -> Settings:
    return Settings(
        source_url="https://example.com",
        refresh_seconds=120,
        tz="Europe/Berlin",
        port=8000,
    )


def test_parse_json_payload(settings: Settings) -> None:
    previous = Measurement(
        level_cm=350,
        timestamp=datetime(2024, 1, 1, 11, 0, tzinfo=ZoneInfo("Europe/Berlin")),
        trend=Trend.STABLE,
    )
    payload = {
        "level": 356.4,
        "timestamp": "2024-01-01T10:00:00Z",
    }

    measurement = _build_measurement_from_payload(payload, settings, previous)

    assert measurement.level_cm == 356
    assert measurement.trend == Trend.RISING
    assert measurement.timestamp.tzinfo is not None
    assert measurement.timestamp.tzinfo.key == "Europe/Berlin"


def test_parse_xml_payload(settings: Settings) -> None:
    previous = Measurement(
        level_cm=410,
        timestamp=datetime(2024, 1, 1, 12, 0, tzinfo=ZoneInfo("Europe/Berlin")),
        trend=Trend.STABLE,
    )

    xml = """
    <root>
        <Wasserstand>404.2</Wasserstand>
        <Messzeit>2024-01-01T10:00:00Z</Messzeit>
    </root>
    """

    measurement = _build_measurement_from_xml(xml, settings, previous)

    assert measurement.level_cm == 404
    assert measurement.trend == Trend.FALLING
    assert measurement.timestamp.astimezone(ZoneInfo("Europe/Berlin")).hour == 11
