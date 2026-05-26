"""Analyst-triggered retrain. Kicks batch/train.py as a background subprocess."""
from __future__ import annotations

import asyncio
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlmodel import Session, select

from ..auth import require_analyst
from ..config import settings
from ..db import get_session
from ..models import User
from ..schemas import RetrainIn

router = APIRouter()

_state: dict = {"running": False, "started_at": None, "log": "", "last_finished_at": None, "last_status": None}


def _run_subprocess(branch: str, top_n: int) -> None:
    import subprocess
    _state["running"] = True
    _state["started_at"] = datetime.utcnow().isoformat()
    _state["log"] = ""
    _state["last_status"] = "running"
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "batch.train", "--branch", branch, "--top-n", str(top_n)],
            cwd=str(Path(__file__).resolve().parents[2]),
            capture_output=True, text=True, timeout=60 * 60,
        )
        _state["log"] = (proc.stdout or "") + ("\n[stderr]\n" + proc.stderr if proc.stderr else "")
        _state["last_status"] = "ok" if proc.returncode == 0 else f"error (exit {proc.returncode})"

        # Regenerate forecasts after a successful retrain.
        if proc.returncode == 0:
            fproc = subprocess.run(
                [sys.executable, "-m", "batch.forecast", "--horizon", "7"],
                cwd=str(Path(__file__).resolve().parents[2]),
                capture_output=True, text=True, timeout=60 * 30,
            )
            _state["log"] += "\n\n[forecast]\n" + (fproc.stdout or "") + (fproc.stderr or "")
    except Exception as e:
        _state["log"] = f"crashed: {e}"
        _state["last_status"] = "crashed"
    finally:
        _state["running"] = False
        _state["last_finished_at"] = datetime.utcnow().isoformat()


_fc_state: dict = {"running": False, "started_at": None, "last_finished_at": None, "last_status": None}


def _run_forecast(start_date: str) -> None:
    """Generate 7 days of forecasts starting from start_date."""
    import subprocess
    _fc_state["running"] = True
    _fc_state["started_at"] = datetime.utcnow().isoformat()
    _fc_state["last_status"] = "running"
    _fc_state["start_date"] = start_date
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "batch.forecast",
             "--horizon", "7", "--start", start_date],
            cwd=str(Path(__file__).resolve().parents[2]),
            capture_output=True, text=True, timeout=60 * 30,
        )
        _fc_state["last_status"] = "ok" if proc.returncode == 0 else f"error (exit {proc.returncode})"
        _fc_state["log"] = (proc.stdout or "") + (proc.stderr or "")
    except Exception as e:
        _fc_state["last_status"] = f"crashed: {e}"
    finally:
        _fc_state["running"] = False
        _fc_state["last_finished_at"] = datetime.utcnow().isoformat()


@router.post("/api/forecast/generate")
def trigger_forecast(
    bg: BackgroundTasks,
    db: Session = Depends(get_session),
    user: User = Depends(require_analyst),
):
    if _fc_state["running"]:
        raise HTTPException(409, "Forecast generation already running")
    if _state["running"]:
        raise HTTPException(409, "A retrain is running — wait for it to finish")

    # Find the latest forecast date in the DB and start from the day after.
    from sqlalchemy import func as safunc
    from app.models import Forecast as FcModel
    latest = db.exec(
        select(safunc.max(FcModel.bake_date))
    ).first()
    from datetime import date as date_type, timedelta as td
    if latest:
        start = latest + td(days=1)
    else:
        start = date_type.today() + td(days=1)

    bg.add_task(_run_forecast, start.isoformat())
    return {"ok": True, "started": True, "start_date": start.isoformat()}


@router.get("/api/forecast/generate/status")
def forecast_generate_status(user: User = Depends(require_analyst)):
    return _fc_state


@router.post("/api/retrain")
def trigger_retrain(
    body: RetrainIn,
    bg: BackgroundTasks,
    user: User = Depends(require_analyst),
):
    if _state["running"]:
        raise HTTPException(409, "A retrain is already running")
    branch = body.branches[0] if body.branches and len(body.branches) == 1 else "all"
    bg.add_task(_run_subprocess, branch, body.top_n)
    return {"ok": True, "started": True}


@router.get("/api/retrain/status")
def retrain_status(user: User = Depends(require_analyst)):
    return _state
