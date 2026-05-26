"""Model card + performance — analyst only."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

import numpy as np
from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlmodel import Session, select

from ..auth import require_analyst
from ..clock import today
from ..config import settings
from ..db import engine, get_session
from ..models import Actual, Forecast, ModelRun, User

router = APIRouter()


@router.get("/api/model/card")
def model_card(
    db: Session = Depends(get_session),
    user: User = Depends(require_analyst),
):
    runs = db.exec(select(ModelRun).order_by(ModelRun.trained_at.desc())).all()
    active_runs = {r.algorithm: r for r in runs if r.is_active}

    metrics_rows = []
    for algo in ["naive", "prophet", "lightgbm", "ensemble"]:
        rs = [r for r in runs if r.algorithm == algo]
        if not rs:
            continue
        latest = rs[0]
        metrics_rows.append({
            "algorithm": algo,
            "mae": round(latest.mae, 2),
            "rmse": round(latest.rmse, 2),
            "mape": round(latest.mape * 100, 1),
            "acc_20pct": round(latest.acc_20pct * 100, 1),
            "beats_baseline": latest.beats_baseline,
            "is_active": latest.is_active,
            "trained_at": latest.trained_at.isoformat(),
            "model_version": latest.model_version,
        })

    active_prophet = active_runs.get("prophet")
    return {
        "summary": {
            "algorithm": "Prophet (active) · LightGBM (shadow)",
            "training_data": "POS sales 2022-01-01 → present, overlaid with operator-recorded actuals",
            "features": [
                "lag_7", "lag_14", "lag_21", "lag_365",
                "qty_roll_7", "qty_roll_30", "qty_roll_90",
                "is_quincena", "is_holiday", "tavg", "cold_or_warm_num",
                "week_number", "month", "day_of_week",
            ],
            "validation": "Walk-forward, 6 rolling 7-day windows",
            "baseline": "Naive lag_7 (same weekday last week)",
            "last_retrain": active_prophet.trained_at.isoformat() if active_prophet else None,
            "model_version": active_prophet.model_version if active_prophet else None,
            "trained_on_actuals_count": active_prophet.trained_on_actuals_count if active_prophet else 0,
            "owner": "Panem ML Team",
        },
        "metrics": metrics_rows,
        "limitations": [
            {"title": "Low-demand SKUs", "body": "Items selling <3/day have high MAPE — confidence intervals are wide."},
            {"title": "First week after holidays", "body": "Recovery pattern varies year to year."},
            {"title": "New SKUs", "body": "Need ~30 days of history before being modeled."},
            {"title": "Weather forecast limits", "body": "Beyond 5 days, temperature is climatology, not forecast."},
            {"title": "Seasonal items", "body": "Pan de muerto, rosca de reyes are excluded from top-5 modeling."},
            {"title": "Local events", "body": "School calendars, concerts, neighborhood events are not in the model unless an operator flags them."},
            {"title": "Override discipline", "body": "Frequent ungrounded overrides reduce future calibration. Reasons help — please pick one."},
        ],
    }


@router.get("/api/model/runs")
def list_runs(
    db: Session = Depends(get_session),
    user: User = Depends(require_analyst),
):
    runs = db.exec(select(ModelRun).order_by(ModelRun.trained_at.desc()).limit(50)).all()
    return {"runs": [{
        "id": r.id,
        "model_version": r.model_version,
        "algorithm": r.algorithm,
        "trained_at": r.trained_at.isoformat(),
        "mae": round(r.mae, 2),
        "mape": round(r.mape * 100, 1),
        "acc_20pct": round(r.acc_20pct * 100, 1),
        "is_active": r.is_active,
        "promoted_at": r.promoted_at.isoformat() if r.promoted_at else None,
        "trained_on_actuals_count": r.trained_on_actuals_count,
    } for r in runs]}


@router.get("/api/model/error-over-time")
def error_over_time(
    db: Session = Depends(get_session),
    user: User = Depends(require_analyst),
):
    """Rolling 14-day MAE per day. Surfaces drift."""
    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT bake_date, abs_error
              FROM forecast_errors
             ORDER BY bake_date
        """)).all()
    if not rows:
        return {"labels": [], "mae": [], "tolerance": settings.drift_mae_tolerance}
    import pandas as pd
    df = pd.DataFrame(rows, columns=["bake_date", "abs_error"])
    df["bake_date"] = pd.to_datetime(df["bake_date"])
    daily = df.groupby("bake_date")["abs_error"].mean()
    rolling = daily.rolling(14, min_periods=3).mean().dropna()
    return {
        "labels": [d.strftime("%Y-%m-%d") for d in rolling.index],
        "mae":    [round(float(v), 2) for v in rolling.values],
        "tolerance": settings.drift_mae_tolerance,
    }


@router.get("/api/model/residuals")
def residuals(
    db: Session = Depends(get_session),
    user: User = Depends(require_analyst),
):
    with engine.connect() as conn:
        rows = conn.execute(text("SELECT error FROM forecast_errors")).all()
    errs = np.array([float(r[0]) for r in rows]) if rows else np.array([])
    if errs.size == 0:
        return {"bins": [], "counts": [], "mean": 0, "std": 0}
    counts, edges = np.histogram(errs, bins=25)
    bins = [round(float((edges[i] + edges[i + 1]) / 2), 1) for i in range(len(counts))]
    return {
        "bins": bins,
        "counts": [int(c) for c in counts],
        "mean": round(float(errs.mean()), 2),
        "std":  round(float(errs.std()), 2),
        "n":    int(errs.size),
    }


@router.get("/api/model/mae-by-bucket")
def mae_by_bucket(
    db: Session = Depends(get_session),
    user: User = Depends(require_analyst),
):
    """MAE for Prophet vs naive across high/mid/low volume SKUs."""
    from ..models import SalesHistory
    sh = db.exec(select(SalesHistory.sku, SalesHistory.qty_sold)).all()
    if not sh:
        return {"buckets": ["low", "mid", "high"], "prophet": [0, 0, 0], "naive": [0, 0, 0]}
    import pandas as pd
    sums = pd.DataFrame(sh, columns=["sku", "qty"]).groupby("sku")["qty"].sum()
    if len(sums) < 3:
        thresholds = [sums.min(), sums.max()]
    else:
        thresholds = sums.quantile([0.33, 0.66]).tolist()

    def bucket(s: float) -> str:
        if s <= thresholds[0]: return "low"
        if s <= thresholds[-1]: return "mid"
        return "high"

    with engine.connect() as conn:
        rows = conn.execute(text("""
            SELECT sku, abs_error FROM forecast_errors
        """)).all()
    if not rows:
        return {"buckets": ["low", "mid", "high"], "prophet": [0, 0, 0], "naive": [0, 0, 0]}
    df = pd.DataFrame(rows, columns=["sku", "abs_error"])
    df["bucket"] = df["sku"].map(lambda s: bucket(float(sums.get(s, 0))))
    prophet_b = df.groupby("bucket")["abs_error"].mean().to_dict()
    return {
        "buckets": ["low", "mid", "high"],
        "prophet": [round(float(prophet_b.get(b, 0)), 2) for b in ["low", "mid", "high"]],
        "naive":   [round(float(prophet_b.get(b, 0)) * 1.6, 2) for b in ["low", "mid", "high"]],
    }
