"""FastAPI application entry point."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from .clock import TZ
from .config import settings
from .db import init_db
from .routes import analytics, auth_routes, feedback, forecast, model, pages, product, retrain

scheduler = AsyncIOScheduler(timezone=TZ)


def _nightly_forecast_job() -> None:
    """Regenerate next-7-day forecasts. Runs daily at 03:00 Monterrey."""
    import subprocess
    import sys
    base = Path(__file__).resolve().parent.parent
    subprocess.Popen(
        [sys.executable, "-m", "batch.forecast", "--horizon", "7"],
        cwd=str(base),
    )


def _nightly_drift_check() -> None:
    """Stub for the drift alarm — analyst sees the chart on /model."""
    # Real implementation would compare rolling-MAE to active model_run.mae
    # and emit a notification. For v1 we surface this in the UI banner.
    pass


def _preload_csv_data() -> None:
    """Pre-load branch + hourly CSV data into memory in a background thread."""
    import threading
    from .routes.analytics import _get_branch_df, _get_hourly_df
    def _load():
        try:
            _get_branch_df()
        except Exception as e:
            print(f"[preload] branch CSV load failed: {e}")
        try:
            _get_hourly_df()
        except Exception as e:
            print(f"[preload] hourly CSV load failed: {e}")
    threading.Thread(target=_load, daemon=True, name="csv-preload").start()


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    _preload_csv_data()
    if not scheduler.running:
        scheduler.add_job(_nightly_forecast_job, CronTrigger(hour=3, minute=0), id="forecast")
        scheduler.add_job(_nightly_drift_check,  CronTrigger(hour=22, minute=0), id="drift")
        scheduler.start()
    yield
    if scheduler.running:
        scheduler.shutdown(wait=False)


app = FastAPI(title="Panem · Daily Bake Planner", lifespan=lifespan)
app.include_router(auth_routes.router)
app.include_router(pages.router)
app.include_router(analytics.router)
app.include_router(forecast.router)
app.include_router(product.router)
app.include_router(feedback.router)
app.include_router(model.router)
app.include_router(retrain.router)

base_dir = Path(__file__).resolve().parent.parent
app.mount("/static", StaticFiles(directory=base_dir / "static"), name="static")
