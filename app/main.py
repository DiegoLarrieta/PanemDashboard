"""FastAPI application entry point."""
from __future__ import annotations

import sqlite3
import subprocess
import sys
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
BASE = Path(__file__).resolve().parent.parent


def _db_count(query: str) -> int:
    db_path = BASE / "panem.db"
    with sqlite3.connect(db_path) as conn:
        return conn.execute(query).fetchone()[0]


def _run(cmd: list[str]) -> None:
    subprocess.run([sys.executable, *cmd], cwd=str(BASE), check=True)


def _auto_setup() -> None:
    data_dir = BASE / "CompleteData"
    if not data_dir.exists():
        print("[setup] CompleteData folder not found — skipping auto-setup")
        return

    if _db_count("SELECT COUNT(*) FROM user") == 0:
        print("[setup] No users found — running seed...")
        _run(["-m", "batch.seed", "--data-dir", str(data_dir)])

    if _db_count("SELECT COUNT(*) FROM modelrun") == 0:
        print("[setup] No trained models found — running train (this may take a few minutes)...")
        _run(["-m", "batch.train", "--branch", "all", "--top-n", "5"])

    if _db_count("SELECT COUNT(*) FROM forecast WHERE bake_date >= date('now')") == 0:
        print("[setup] No upcoming forecasts found — running forecast...")
        _run(["-m", "batch.forecast", "--horizon", "7"])


def _nightly_forecast_job() -> None:
    """Regenerate next-7-day forecasts. Runs daily at 03:00 Monterrey."""
    subprocess.Popen(
        [sys.executable, "-m", "batch.forecast", "--horizon", "7"],
        cwd=str(BASE),
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
    _auto_setup()
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

app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")
