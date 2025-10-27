from __future__ import annotations

from datetime import datetime
from enum import Enum, IntEnum
from typing import Final

from pydantic import BaseModel, ConfigDict, Field


class Trend(IntEnum):
    FALLING = -1
    STABLE = 0
    RISING = 1

    @property
    def symbol(self) -> str:
        return {self.FALLING: "↓", self.STABLE: "→", self.RISING: "↑"}[self]

    @property
    def color(self) -> str:
        return {self.FALLING: "badge-falling", self.STABLE: "badge-stable", self.RISING: "badge-rising"}[self]


class WarningLevel(str, Enum):
    NORMAL = "normal"
    ATTENTION = "attention"
    WARNING = "warning"
    ALARM = "alarm"

    @property
    def label(self) -> str:
        return {
            self.NORMAL: "Normal",
            self.ATTENTION: "Aufmerksamkeit",
            self.WARNING: "Warnung",
            self.ALARM: "Alarm",
        }[self]

    @property
    def color(self) -> str:
        return {
            self.NORMAL: "badge-normal",
            self.ATTENTION: "badge-attention",
            self.WARNING: "badge-warning",
            self.ALARM: "badge-alarm",
        }[self]


WARN_THRESHOLDS: Final[tuple[tuple[int, WarningLevel], ...]] = (
    (400, WarningLevel.NORMAL),
    (600, WarningLevel.ATTENTION),
    (800, WarningLevel.WARNING),
)


def determine_warning(level_cm: int) -> WarningLevel:
    for threshold, level in WARN_THRESHOLDS:
        if level_cm < threshold:
            return level
    return WarningLevel.ALARM


class Measurement(BaseModel):
    model_config = ConfigDict(frozen=True)

    level_cm: int = Field(ge=0, description="Water level in centimeters")
    timestamp: datetime = Field(description="Timestamp of the measurement with tz info")
    trend: Trend = Field(description="Trend indicator: -1 falling, 0 stable, 1 rising")
    is_demo: bool = False

    @property
    def warning(self) -> WarningLevel:
        return determine_warning(self.level_cm)


class HistoryResponse(BaseModel):
    data: list[Measurement]
    demo_mode: bool = False


class LatestResponse(BaseModel):
    measurement: Measurement
    history: list[Measurement] = Field(default_factory=list)
    latency_ms: float | None = None
    error: str | None = None
    demo_mode: bool = False


def resolve_trend(
    current_level: int,
    provided_trend: int | None,
    previous: Measurement | None,
) -> Trend:
    if provided_trend in (-1, 0, 1):
        return Trend(provided_trend)
    if previous is None:
        return Trend.STABLE

    delta = current_level - previous.level_cm
    if delta > 2:
        return Trend.RISING
    if delta < -2:
        return Trend.FALLING
    return Trend.STABLE

