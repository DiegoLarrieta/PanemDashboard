"""Product deep-dive: 90-day history, forecast vs actual, seasonality, peers, revenue curve."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlmodel import Session, select

from ..auth import current_user
from ..clock import default_bake_date, today
from ..config import settings
from ..db import get_session
from ..models import Actual, Forecast, Holiday, ModelRun, SalesHistory, User, Weather

router = APIRouter()


@router.get("/api/product/{sku}/deep-dive")
def product_deep_dive(
    sku: str,
    branch: str = Query(...),
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    today_ = today()

    # Anchor to the latest date in our data so history windows don't fall
    # outside the dataset when the POS snapshot lags the wall clock.
    data_end = db.exec(
        select(func.max(SalesHistory.sale_date))
        .where(SalesHistory.branch == branch)
        .where(SalesHistory.sku == sku)
    ).first() or today_

    # ---- 90-day history ----
    start_90 = data_end - timedelta(days=90)
    hist = db.exec(
        select(SalesHistory)
        .where(SalesHistory.branch == branch)
        .where(SalesHistory.sku == sku)
        .where(SalesHistory.sale_date >= start_90)
        .order_by(SalesHistory.sale_date)
    ).all()
    if not hist:
        raise HTTPException(404, "SKU not found at this branch")
    item_name = hist[-1].item_name if hist else ""

    history_chart = {
        "labels": [h.sale_date.isoformat() for h in hist],
        "qty":    [h.qty_sold for h in hist],
    }

    # ---- Next-bake forecast (the recommendation) ----
    # Use earliest available forecast date for this SKU (data may lag wall clock).
    next_bake_row = db.exec(
        select(func.min(Forecast.bake_date))
        .where(Forecast.branch == branch)
        .where(Forecast.sku == sku)
    ).first()
    next_bake = next_bake_row if next_bake_row else (data_end + timedelta(days=1))
    fc = db.exec(
        select(Forecast)
        .where(Forecast.branch == branch)
        .where(Forecast.sku == sku)
        .where(Forecast.bake_date == next_bake)
    ).first()
    # Baseline lag-7
    baseline_date = next_bake - timedelta(days=7)
    baseline = db.exec(
        select(SalesHistory.qty_sold)
        .where(SalesHistory.branch == branch)
        .where(SalesHistory.sku == sku)
        .where(SalesHistory.sale_date == baseline_date)
    ).first()

    # ---- Forecast vs actual ----
    # Timeline: last 14 days of actual sales data  +  upcoming forecast window.
    # This gives a continuous picture: history rolling into the prediction so
    # the operator can see trend continuity and—once actuals are logged—compare.
    start_14 = data_end - timedelta(days=13)   # 14 days inclusive

    # Historical sales for the look-back window
    hist14 = db.exec(
        select(SalesHistory.sale_date, SalesHistory.qty_sold)
        .where(SalesHistory.branch == branch).where(SalesHistory.sku == sku)
        .where(SalesHistory.sale_date >= start_14).where(SalesHistory.sale_date <= data_end)
        .order_by(SalesHistory.sale_date)
    ).all()
    hist_map = {row[0]: row[1] for row in hist14}

    # Forecast window for this SKU (next 7 days starting from earliest forecast date)
    fc_all = db.exec(
        select(Forecast)
        .where(Forecast.branch == branch).where(Forecast.sku == sku)
        .order_by(Forecast.bake_date)
    ).all()
    fc_window = fc_all[:7] if fc_all else []
    f_map = {f.bake_date: f for f in fc_window}

    # Any logged actuals for the forecast dates
    if fc_window:
        fc_start = fc_window[0].bake_date
        fc_end   = fc_window[-1].bake_date
        logged_actuals = db.exec(
            select(Actual)
            .where(Actual.branch == branch).where(Actual.sku == sku)
            .where(Actual.bake_date >= fc_start).where(Actual.bake_date <= fc_end)
        ).all()
        a_map = {a.bake_date: a for a in logged_actuals}
    else:
        a_map = {}

    # Build a single sorted day-list covering both windows
    all_days: set[date] = set(hist_map.keys()) | set(f_map.keys())
    days = sorted(all_days)

    fc_chart = {
        "labels":    [d.isoformat() for d in days],
        # "actual" = real historical sales for past dates; logged actuals for forecast dates
        "actual":    [
            hist_map.get(d, a_map[d].qty_sold if d in a_map else None)
            for d in days
        ],
        "predicted": [f_map[d].predicted_units if d in f_map else None for d in days],
        "ci_low":    [f_map[d].confidence_low  if d in f_map else None for d in days],
        "ci_high":   [f_map[d].confidence_high if d in f_map else None for d in days],
    }

    # ---- Weekday seasonality ----
    by_dow = {i: [] for i in range(7)}
    for h in hist:
        by_dow[h.sale_date.weekday()].append(h.qty_sold)
    seasonality = {
        "labels": ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        "avg":    [round(float(np.mean(by_dow[i])), 1) if by_dow[i] else 0 for i in range(7)],
    }

    # ---- Cold vs warm, quincena vs non-quincena ----
    holidays = {h.date: h for h in db.exec(select(Holiday)).all()}
    weather  = {w.date: w for w in db.exec(select(Weather)).all()}
    cold, warm, q, nq = [], [], [], []
    for h in hist:
        w = weather.get(h.sale_date)
        if w:
            (cold if w.cold_or_warm_num == -1 else warm if w.cold_or_warm_num == 1 else None).append(h.qty_sold) if w.cold_or_warm_num != 0 else None
        is_q = h.sale_date in holidays and holidays[h.sale_date].is_quincena
        (q if is_q else nq).append(h.qty_sold)
    response = {
        "cold":  round(float(np.mean(cold)), 1) if cold else 0,
        "warm":  round(float(np.mean(warm)), 1) if warm else 0,
        "quincena":     round(float(np.mean(q)),  1) if q else 0,
        "non_quincena": round(float(np.mean(nq)), 1) if nq else 0,
    }

    # ---- Peer comparison: same SKU across all branches (predicted units for next_bake) ----
    peer_rows = db.exec(
        select(Forecast.branch, Forecast.predicted_units)
        .where(Forecast.sku == sku).where(Forecast.bake_date == next_bake)
    ).all()
    peers = {
        "labels": [r[0] for r in peer_rows],
        "qty":    [round(float(r[1]), 1) for r in peer_rows],
    }

    # ---- Similar SKUs at same branch (top-5 by Pearson r on last 90d) ----
    other_rows = db.exec(
        select(SalesHistory)
        .where(SalesHistory.branch == branch)
        .where(SalesHistory.sale_date >= start_90)
    ).all()
    # Build (sku, item_name) -> list of (date, qty)
    import pandas as pd
    df = pd.DataFrame([{
        "sku": r.sku, "item_name": r.item_name, "date": r.sale_date, "qty": r.qty_sold,
    } for r in other_rows])
    similar = []
    if not df.empty:
        pivot = df.pivot_table(index="date", columns="sku", values="qty", aggfunc="sum").fillna(0)
        if sku in pivot.columns and len(pivot) > 5:
            target = pivot[sku]
            corrs = pivot.corrwith(target).drop(sku, errors="ignore")
            top = corrs.dropna().sort_values(ascending=False).head(5)
            name_map = df.drop_duplicates("sku").set_index("sku")["item_name"].to_dict()
            similar = [{
                "sku": s, "item_name": name_map.get(s, ""),
                "r": round(float(v), 3),
            } for s, v in top.items()]

    # ---- Revenue vs units (scatter) ----
    rev_points = [{"x": h.qty_sold, "y": h.revenue} for h in hist if h.revenue > 0]
    predicted_point = None
    if fc:
        avg_price = db.exec(
            select(func.avg(SalesHistory.unit_price))
            .where(SalesHistory.branch == branch).where(SalesHistory.sku == sku)
        ).first() or 0
        predicted_point = {
            "x": fc.predicted_units,
            "y": float(fc.predicted_units) * float(avg_price or 0),
        }

    # ---- Model card mini ----
    active = db.exec(
        select(ModelRun).where(ModelRun.algorithm == "prophet").where(ModelRun.is_active == True)  # noqa: E712
        .order_by(ModelRun.id.desc())
    ).first()

    # ---- 7-day totals for recommendation banner (matches the plan page) ----
    next7_pred = round(sum(f.predicted_units for f in fc_window), 1) if fc_window else None
    next7_lo   = round(sum(f.confidence_low   for f in fc_window), 1) if fc_window else None
    next7_hi   = round(sum(f.confidence_high  for f in fc_window), 1) if fc_window else None
    week_start = fc_window[0].bake_date if fc_window else next_bake
    week_end   = fc_window[-1].bake_date if fc_window else next_bake

    return {
        "sku": sku,
        "branch": branch,
        "item_name": item_name,
        "next_bake": next_bake.isoformat(),
        "recommendation": {
            "predicted_units": next7_pred,
            "ci_low":  next7_lo,
            "ci_high": next7_hi,
            "week_start": week_start.isoformat(),
            "week_end":   week_end.isoformat(),
            "baseline_lag7": float(baseline) if baseline is not None else None,
            "model_version": fc.model_version if fc else (active.model_version if active else None),
            "last_retrain": active.trained_at.isoformat() if active else None,
            "forecast_id": fc.id if fc else None,
        },
        "history_chart": history_chart,
        "forecast_vs_actual": fc_chart,
        "seasonality": seasonality,
        "response": response,
        "peers": peers,
        "similar": similar,
        "revenue_curve": {"points": rev_points, "predicted": predicted_point},
    }
