"""Operator feedback: overrides + actuals. The closed-loop input layer."""
from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, select

from ..auth import current_user, require_analyst
from ..clock import now, plan_mode_for, today
from ..config import settings
from ..db import get_session
from ..models import Actual, Forecast, Override, PlanLock, User
from ..schemas import ActualIn, LockIn, OverrideIn

router = APIRouter()


@router.post("/api/feedback/override")
def post_override(
    body: OverrideIn,
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    f = db.get(Forecast, body.forecast_id)
    if not f:
        raise HTTPException(404, "Forecast not found")
    # Block edits if the plan is locked.
    locked = db.exec(
        select(PlanLock).where(PlanLock.branch == f.branch).where(PlanLock.bake_date == f.bake_date)
    ).first()
    if locked:
        raise HTTPException(409, "Plan is locked")

    valid_reasons = {"weather", "local_event", "promo", "gut_feel", "other"}
    if body.reason not in valid_reasons:
        raise HTTPException(422, f"reason must be one of {valid_reasons}")

    # Upsert: one override per forecast.
    existing = db.exec(select(Override).where(Override.forecast_id == body.forecast_id)).first()
    if existing:
        existing.override_units = body.override_units
        existing.reason = body.reason
        existing.note = body.note or ""
        existing.user_id = user.id  # type: ignore
        existing.created_at = datetime.utcnow()
        db.add(existing)
    else:
        db.add(Override(
            forecast_id=body.forecast_id,
            user_id=user.id,  # type: ignore
            override_units=body.override_units,
            reason=body.reason,
            note=body.note or "",
        ))
    db.commit()
    return {"ok": True}


@router.delete("/api/feedback/override/{forecast_id}")
def delete_override(
    forecast_id: int,
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    existing = db.exec(select(Override).where(Override.forecast_id == forecast_id)).first()
    if existing:
        db.delete(existing)
        db.commit()
    return {"ok": True}


@router.post("/api/feedback/actual")
def post_actual(
    body: ActualIn,
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    if body.bake_date > today():
        raise HTTPException(409, "Cannot record actuals for a future date")
    if body.qty_sold < 0 or body.qty_wasted < 0:
        raise HTTPException(422, "Quantities must be non-negative")

    existing = db.exec(
        select(Actual)
        .where(Actual.branch == body.branch)
        .where(Actual.sku == body.sku)
        .where(Actual.bake_date == body.bake_date)
    ).first()
    if existing:
        existing.qty_sold = body.qty_sold
        existing.qty_wasted = body.qty_wasted
        existing.recorded_by = user.id  # type: ignore
        existing.recorded_at = datetime.utcnow()
        db.add(existing)
    else:
        db.add(Actual(
            branch=body.branch, sku=body.sku, bake_date=body.bake_date,
            qty_sold=body.qty_sold, qty_wasted=body.qty_wasted,
            recorded_by=user.id,  # type: ignore
        ))
    db.commit()
    return {"ok": True}


@router.get("/api/feedback/actuals")
def get_actuals(
    branch: str = Query(...),
    week_start: str = Query(...),
    week_end: str = Query(...),
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Return all logged actuals for a branch in a date range, keyed by (sku, date)."""
    start = date.fromisoformat(week_start)
    end = date.fromisoformat(week_end)
    rows = db.exec(
        select(Actual)
        .where(Actual.branch == branch)
        .where(Actual.bake_date >= start)
        .where(Actual.bake_date <= end)
    ).all()
    # Return as dict keyed by "sku|date" for easy JS lookup
    result = {}
    for r in rows:
        result[f"{r.sku}|{r.bake_date.isoformat()}"] = {
            "qty_sold": r.qty_sold,
            "qty_wasted": r.qty_wasted,
        }
    # Also return which dates have ANY actuals logged (for the day strip)
    dates_logged = list({r.bake_date.isoformat() for r in rows})
    return {"actuals": result, "dates_logged": dates_logged}


@router.post("/api/feedback/lock")
def post_lock(
    body: LockIn,
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    existing = db.exec(
        select(PlanLock).where(PlanLock.branch == body.branch).where(PlanLock.bake_date == body.bake_date)
    ).first()
    if existing:
        return {"ok": True, "already_locked": True}
    db.add(PlanLock(branch=body.branch, bake_date=body.bake_date, locked_by=user.id))  # type: ignore
    db.commit()
    return {"ok": True}


@router.delete("/api/feedback/lock")
def delete_lock(
    branch: str = Query(...),
    bake_date: str = Query(...),
    db: Session = Depends(get_session),
    user: User = Depends(require_analyst),
):
    bd = date.fromisoformat(bake_date)
    existing = db.exec(
        select(PlanLock).where(PlanLock.branch == branch).where(PlanLock.bake_date == bd)
    ).first()
    if existing:
        db.delete(existing)
        db.commit()
    return {"ok": True}


@router.get("/api/feedback/log")
def feedback_log(
    branch: Optional[str] = Query(None),
    days: int = Query(14, ge=1, le=90),
    db: Session = Depends(get_session),
    user: User = Depends(require_analyst),
):
    cutoff = datetime.utcnow() - timedelta(days=days)
    ov_stmt = select(Override).where(Override.created_at >= cutoff)
    ac_stmt = select(Actual).where(Actual.recorded_at >= cutoff)
    overrides = db.exec(ov_stmt).all()
    actuals = db.exec(ac_stmt).all()

    enriched_ov = []
    for o in overrides:
        f = db.get(Forecast, o.forecast_id)
        if not f or (branch and f.branch != branch):
            continue
        u = db.get(User, o.user_id)
        enriched_ov.append({
            "kind": "override",
            "branch": f.branch, "sku": f.sku, "item_name": f.item_name,
            "bake_date": f.bake_date.isoformat(),
            "predicted_units": f.predicted_units,
            "override_units": o.override_units,
            "delta": round(o.override_units - f.predicted_units, 1),
            "reason": o.reason, "note": o.note,
            "user": u.username if u else "?",
            "at": o.created_at.isoformat(),
        })

    enriched_ac = []
    for a in actuals:
        if branch and a.branch != branch:
            continue
        u = db.get(User, a.recorded_by)
        # Try to attach the forecast that day to compute error.
        f = db.exec(
            select(Forecast)
            .where(Forecast.branch == a.branch)
            .where(Forecast.sku == a.sku)
            .where(Forecast.bake_date == a.bake_date)
        ).first()
        enriched_ac.append({
            "kind": "actual",
            "branch": a.branch, "sku": a.sku,
            "bake_date": a.bake_date.isoformat(),
            "qty_sold": a.qty_sold, "qty_wasted": a.qty_wasted,
            "predicted_units": f.predicted_units if f else None,
            "error": round(f.predicted_units - a.qty_sold, 1) if f else None,
            "user": u.username if u else "?",
            "at": a.recorded_at.isoformat(),
        })

    combined = sorted(enriched_ov + enriched_ac, key=lambda r: r["at"], reverse=True)
    return {"rows": combined}
