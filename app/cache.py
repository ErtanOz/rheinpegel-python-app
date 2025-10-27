from __future__ import annotations

import asyncio
import json
import logging
from collections import deque
from pathlib import Path
from typing import Deque

from .models import Measurement

logger = logging.getLogger(__name__)


class MeasurementCache:
    def __init__(self, *, maxlen: int = 48, storage_path: Path | str = "data/cache.json") -> None:
        self._buffer: Deque[Measurement] = deque(maxlen=maxlen)
        self._lock = asyncio.Lock()
        self._path = Path(storage_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text("utf-8"))
        except json.JSONDecodeError as exc:
            logger.warning("Failed to read cache file %s: %s", self._path, exc)
            return

        if not isinstance(raw, list):
            logger.warning("Invalid cache file format: expected list, got %s", type(raw))
            return

        for item in raw[-self._buffer.maxlen :]:
            try:
                measurement = Measurement.model_validate(item)
            except Exception as exc:  # noqa: BLE001
                logger.debug("Skipping invalid cache entry %s: %s", item, exc)
                continue
            self._buffer.append(measurement)

        logger.info("Loaded %s cached measurements", len(self._buffer))

    def _dump_to_disk(self) -> None:
        data = [m.model_dump(mode="json") for m in self._buffer]
        tmp_path = self._path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(self._path)

    async def add(self, measurement: Measurement, *, persist: bool = True) -> None:
        async with self._lock:
            latest = self._buffer[-1] if self._buffer else None
            if latest and latest.timestamp == measurement.timestamp:
                self._buffer.pop()
            self._buffer.append(measurement)

        if persist:
            await asyncio.to_thread(self._dump_to_disk)

    async def get_latest(self) -> Measurement | None:
        async with self._lock:
            return self._buffer[-1] if self._buffer else None

    async def get_history(self) -> list[Measurement]:
        async with self._lock:
            return list(self._buffer)

    def __len__(self) -> int:
        return len(self._buffer)

