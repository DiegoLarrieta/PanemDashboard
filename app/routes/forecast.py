"""Read forecasts + KPI summary for Page 1."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlmodel import Session, select

from ..auth import current_user
from ..clock import default_bake_date, now, plan_mode_for, server_now_iso, today
from ..config import settings
from ..db import get_session
from ..models import Actual, Forecast, ModelRun, Override, PlanLock, SalesHistory, User

router = APIRouter()


def _last_week_total(db: Session, branch: str, sku: str, ref: date) -> Optional[float]:
    """Total units sold in the 7 days ending on ref (inclusive)."""
    start = ref - timedelta(days=6)
    stmt = (
        select(func.sum(SalesHistory.qty_sold))
        .where(SalesHistory.branch == branch)
        .where(SalesHistory.sku == sku)
        .where(SalesHistory.sale_date >= start)
        .where(SalesHistory.sale_date <= ref)
    )
    val = db.exec(stmt).first()
    return round(float(val), 0) if val else None


@router.get("/api/now")
def get_now():
    return {
        "server_now": server_now_iso(),
        "today": today().isoformat(),
        "default_bake_date": default_bake_date().isoformat(),
        "plan_lock_hour": settings.plan_lock_hour,
        "actuals_open_hour": settings.actuals_open_hour,
    }


@router.get("/api/forecast")
def list_forecast(
    branch: str = Query(...),
    bake_date: Optional[str] = Query(None),
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    if bake_date:
        bd = date.fromisoformat(bake_date)
    else:
        bd = default_bake_date()

    # Find the closest forecast date to bd: prefer bd itself, else snap to
    # the latest available date before bd, else the earliest date after bd.
    exact = db.exec(
        select(func.max(Forecast.bake_date))
        .where(Forecast.branch == branch)
        .where(Forecast.bake_date <= bd)
    ).first()
    if not exact:
        exact = db.exec(
            select(func.min(Forecast.bake_date))
            .where(Forecast.branch == branch)
        ).first()
    if not exact:
        return {"rows": [], "kpis": {"units_to_bake": 0, "projected_revenue": 0.0,
                "expected_waste": 0, "stockout_risk_skus": 0},
                "bake_date": bd.isoformat(), "week_start": bd.isoformat(),
                "week_end": bd.isoformat(), "mode": plan_mode_for(bd),
                "is_locked": False, "server_now": server_now_iso()}

    # Start the 7-day window from the snapped date.
    week_start = exact
    week_end   = week_start + timedelta(days=6)

    # "Last 7d sold" = the 7 days ending on the last date we have sales data for.
    # This works whether data is current or lags the wall clock.
    data_end = db.exec(
        select(func.max(SalesHistory.sale_date))
        .where(SalesHistory.branch == branch)
    ).first() or (week_start - timedelta(days=1))
    last_week_end = data_end

    # All 7-day forecasts grouped by SKU
    all_fc = db.exec(
        select(Forecast)
        .where(Forecast.branch == branch)
        .where(Forecast.bake_date >= week_start)
        .where(Forecast.bake_date <= week_end)
    ).all()

    # Group by SKU
    from collections import defaultdict
    sku_fc: dict = defaultdict(list)
    for f in all_fc:
        sku_fc[f.sku].append(f)

    # Sort SKUs by total predicted desc
    sku_order = sorted(sku_fc.keys(), key=lambda s: sum(f.predicted_units for f in sku_fc[s]), reverse=True)

    # Pull overrides for all forecast ids
    all_ids = [f.id for f in all_fc]
    ov_rows = db.exec(select(Override).where(Override.forecast_id.in_(all_ids))).all() if all_ids else []
    ov_map = {o.forecast_id: o for o in ov_rows}

    out = []
    for sku in sku_order:
        fc_list = sorted(sku_fc[sku], key=lambda f: f.bake_date)
        item_name = fc_list[0].item_name
        model_version = fc_list[0].model_version

        next7_pred  = round(sum(f.predicted_units for f in fc_list), 0)
        next7_lo    = round(sum(f.confidence_low   for f in fc_list), 0)
        next7_hi    = round(sum(f.confidence_high  for f in fc_list), 0)

        # Check if any override exists across the 7 days
        overrides = [ov_map[f.id] for f in fc_list if f.id in ov_map]
        total_override = round(sum(o.override_units for o in overrides), 0) if overrides else None
        override_reason = overrides[0].reason if overrides else None

        last_week_total = _last_week_total(db, branch, sku, last_week_end)

        daily = [
            {
                "date":  f.bake_date.isoformat(),
                "pred":  round(f.predicted_units, 0),
                "lo":    round(f.confidence_low, 0),
                "hi":    round(f.confidence_high, 0),
                "override": round(ov_map[f.id].override_units, 0) if f.id in ov_map else None,
            }
            for f in fc_list
        ]

        out.append({
            "id": fc_list[0].id,
            "branch": branch,
            "sku": sku,
            "item_name": item_name,
            "week_start": week_start.isoformat(),
            "week_end": week_end.isoformat(),
            "next7_pred": next7_pred,
            "next7_lo": next7_lo,
            "next7_hi": next7_hi,
            "last_week_total": last_week_total,
            "model_version": model_version,
            "override": total_override,
            "override_reason": override_reason,
            "daily": daily,
            # Keep single-day fields for backwards compat
            "predicted_units": next7_pred,
            "confidence_low": next7_lo,
            "confidence_high": next7_hi,
            "last_week_avg": last_week_total,
        })

    # KPI summary (weekly totals)
    total_units = sum((o["override"] or o["next7_pred"]) for o in out)
    projected_revenue = 0.0
    for o in out:
        units = o["override"] or o["next7_pred"]
        avg_price = db.exec(
            select(func.avg(SalesHistory.unit_price))
            .where(SalesHistory.branch == branch)
            .where(SalesHistory.sku == o["sku"])
        ).first() or 0.0
        projected_revenue += float(units) * float(avg_price or 0)
    expected_waste = sum(max(0, o["next7_pred"] - o["next7_lo"]) for o in out)
    stockout_risk  = sum(1 for o in out if (o["last_week_total"] or 0) > o["next7_lo"])

    is_locked = db.exec(
        select(PlanLock).where(PlanLock.branch == branch).where(PlanLock.bake_date == bd)
    ).first() is not None

    # Historical waste rate from logged actuals (last 30 days of recorded data)
    recent_actuals = db.exec(
        select(func.sum(Actual.qty_wasted), func.sum(Actual.qty_sold))
        .where(Actual.branch == branch)
    ).first()
    total_wasted = float(recent_actuals[0] or 0) if recent_actuals else 0
    total_sold_actual = float(recent_actuals[1] or 0) if recent_actuals else 0
    waste_rate = round(total_wasted / (total_sold_actual + total_wasted), 3) if (total_sold_actual + total_wasted) > 0 else None

    return {
        "rows": out,
        "kpis": {
            "units_to_bake": round(total_units),
            "projected_revenue": round(projected_revenue, 2),
            "expected_waste": round(expected_waste),
            "stockout_risk_skus": stockout_risk,
            "waste_rate": waste_rate,
        },
        "bake_date": week_start.isoformat(),
        "week_start": week_start.isoformat(),
        "week_end": week_end.isoformat(),
        "mode": "locked" if is_locked else plan_mode_for(bd),
        "is_locked": is_locked,
        "server_now": server_now_iso(),
    }


@router.get("/api/forecast/branches-summary")
def branches_summary(
    bake_date: Optional[str] = Query(None),
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Total predicted units per branch for the given bake_date."""
    bd = date.fromisoformat(bake_date) if bake_date else default_bake_date()
    stmt = (
        select(Forecast.branch, func.sum(Forecast.predicted_units))
        .where(Forecast.bake_date == bd)
        .group_by(Forecast.branch)
    )
    rows = db.exec(stmt).all()
    return {
        "bake_date": bd.isoformat(),
        "data": [{"branch": r[0], "units": round(float(r[1] or 0))} for r in rows],
    }


@router.get("/api/forecast/vs-actual")
def forecast_vs_actual(
    branch: str = Query(...),
    days: int = Query(7, ge=1, le=60),
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Last `days` daily totals: predicted vs actual."""
    end = today()
    start = end - timedelta(days=days - 1)
    f_rows = db.exec(
        select(Forecast.bake_date, func.sum(Forecast.predicted_units))
        .where(Forecast.branch == branch)
        .where(Forecast.bake_date >= start)
        .where(Forecast.bake_date <= end)
        .group_by(Forecast.bake_date)
    ).all()
    a_rows = db.exec(
        select(Actual.bake_date, func.sum(Actual.qty_sold))
        .where(Actual.branch == branch)
        .where(Actual.bake_date >= start)
        .where(Actual.bake_date <= end)
        .group_by(Actual.bake_date)
    ).all()
    f_map = {r[0]: float(r[1] or 0) for r in f_rows}
    a_map = {r[0]: float(r[1] or 0) for r in a_rows}
    labels, preds, acts = [], [], []
    d = start
    while d <= end:
        labels.append(d.isoformat())
        preds.append(round(f_map.get(d, 0)))
        acts.append(round(a_map.get(d, 0)))
        d += timedelta(days=1)
    return {"labels": labels, "predicted": preds, "actual": acts}
