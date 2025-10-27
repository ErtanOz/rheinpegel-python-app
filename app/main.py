from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager, suppress
from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest

from .cache import MeasurementCache
from .config import Settings, get_settings
from .fetcher import FetchResult, fetch_latest
from .metrics import record_fetch, set_background_state, set_data_age
from .models import HistoryResponse, LatestResponse, Measurement

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))

@asynccontextmanager
async def lifespan(app: FastAPI):
    logging.basicConfig(level=logging.INFO)
    await service.start()
    try:
        yield
    finally:
        await service.stop()


app = FastAPI(title="Rheinpegel App", version="0.1.0", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


class PegelService:
    def __init__(self, settings: Settings, cache: MeasurementCache) -> None:
        self.settings = settings
        self.cache = cache
        self._lock = asyncio.Lock()
        self._task: asyncio.Task[None] | None = None

    async def start(self) -> None:
        if self._task and not self._task.done():
            return

        if len(self.cache) == 0:
            try:
                await self.fetch_and_update()
            except Exception as exc:  # noqa: BLE001
                logger.warning("Initial fetch failed, cache remains empty: %s", exc)

        self._task = asyncio.create_task(self._run_loop())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None
        set_background_state(False)

    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def fetch_and_update(
        self,
        *,
        force_demo: bool = False,
    ) -> FetchResult:
        async with self._lock:
            previous = await self.cache.get_latest()
            result = await fetch_latest(self.settings, previous, force_demo=force_demo)
            await self.cache.add(result.measurement)

        self._update_metrics(result)
        return result

    async def latest(self) -> Measurement | None:
        return await self.cache.get_latest()

    async def history(self) -> list[Measurement]:
        return await self.cache.get_history()

    async def _run_loop(self) -> None:
        set_background_state(True)
        try:
            while True:
                try:
                    await self.fetch_and_update()
                except Exception as exc:  # noqa: BLE001
                    logger.exception("Background fetch failure: %s", exc)
                await asyncio.sleep(self.settings.refresh_seconds)
        except asyncio.CancelledError:
            raise
        finally:
            set_background_state(False)

    def _update_metrics(self, result: FetchResult) -> None:
        outcome = "success"
        if result.error:
            outcome = "error"
        elif result.is_demo:
            outcome = "demo"
        record_fetch(result.latency_ms, outcome)

        if result.measurement:
            now = datetime.now(self.settings.timezone)
            age = max(0.0, (now - result.measurement.timestamp).total_seconds())
            set_data_age(age)
        else:
            set_data_age(None)


settings = get_settings()
cache = MeasurementCache()
service = PegelService(settings=settings, cache=cache)


async def get_service() -> PegelService:
    return service


def _warning_levels() -> list[dict[str, str | int]]:
    return [
        {"label": "Normal", "range": "< 400 cm", "color": "badge-normal", "min": 0, "max": 399},
        {"label": "Aufmerksamkeit", "range": "400 – 599 cm", "color": "badge-attention", "min": 400, "max": 599},
        {"label": "Warnung", "range": "600 – 799 cm", "color": "badge-warning", "min": 600, "max": 799},
        {"label": "Alarm", "range": "≥ 800 cm", "color": "badge-alarm", "min": 800, "max": 9999},
    ]


def _sparkline_path(measurements: list[Measurement]) -> str:
    if not measurements:
        return ""
    levels = [m.level_cm for m in measurements]
    min_level = min(levels)
    max_level = max(levels)
    span = max(max_level - min_level, 1)
    step = 100 / max(len(levels) - 1, 1)
    points = []
    for idx, level in enumerate(levels):
        x = idx * step
        y = 40 - ((level - min_level) / span * 40)
        points.append(f"{x:.2f},{y:.2f}")
    return "M " + " L ".join(points)


@app.get("/", response_class=HTMLResponse)
async def dashboard(
    request: Request,
    demo: Annotated[bool, Query(alias="demo")] = False,
    service: PegelService = Depends(get_service),
) -> HTMLResponse:
    if demo:
        await service.fetch_and_update(force_demo=True)

    latest = await service.latest()
    if latest is None:
        result = await service.fetch_and_update(force_demo=demo)
        latest = result.measurement

    history = await service.history()
    sparkline = history[-24:]
    sparkline_path = _sparkline_path(sparkline)
    initial_payload = {
        "latest": latest.model_dump(mode="json") if latest else None,
        "history": [item.model_dump(mode="json") for item in history],
        "autoRefresh": settings.refresh_seconds,
        "demo": demo or (latest.is_demo if latest else False),
    }

    context = {
        "request": request,
        "latest": latest,
        "history": history,
        "sparkline": sparkline,
        "sparkline_path": sparkline_path,
        "auto_refresh_seconds": settings.refresh_seconds,
        "timezone": settings.tz,
        "warning_levels": _warning_levels(),
        "demo_mode": demo or (latest.is_demo if latest else False),
        "initial_payload": initial_payload,
    }
    return TEMPLATES.TemplateResponse("index.html.j2", context)


@app.get("/api/latest")
async def api_latest(
    demo: Annotated[bool, Query(alias="demo")] = False,
    service: PegelService = Depends(get_service),
) -> JSONResponse:
    result = await service.fetch_and_update(force_demo=demo)
    history = await service.history()
    response = LatestResponse(
        measurement=result.measurement,
        history=history,
        latency_ms=result.latency_ms,
        error=result.error,
        demo_mode=result.is_demo,
    )
    return JSONResponse(response.model_dump(mode="json"))


@app.get("/api/history")
async def api_history(service: PegelService = Depends(get_service)) -> JSONResponse:
    history = await service.history()
    response = HistoryResponse(data=history, demo_mode=any(item.is_demo for item in history))
    return JSONResponse(response.model_dump(mode="json"))


@app.get("/healthz")
async def healthz(service: PegelService = Depends(get_service)) -> PlainTextResponse:
    if not service.is_running():
        raise HTTPException(status_code=503, detail="Background task not running")
    return PlainTextResponse("ok")


@app.get("/metrics")
async def metrics_endpoint(service: PegelService = Depends(get_service)) -> PlainTextResponse:
    latest = await service.latest()
    if latest is None:
        set_data_age(None)
    else:
        age = max(0.0, (datetime.now(settings.timezone) - latest.timestamp).total_seconds())
        set_data_age(age)
    data = generate_latest()
    return PlainTextResponse(content=data.decode("utf-8"), media_type=CONTENT_TYPE_LATEST)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.port, reload=True)
