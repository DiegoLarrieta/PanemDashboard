"""Generate the next N days of forecasts and upsert into the forecasts table.

For each (branch, sku) under the active Prophet version we:
  1. Re-fit Prophet quickly on the full history (with operator actuals overlaid).
  2. Predict horizon days forward with 80% prediction intervals.
  3. Upsert into forecasts keyed on (branch, sku, bake_date).

LightGBM forecasts are also produced but not the canonical output unless its
model_run is the active one — the active version wins.

Usage:
    python -m batch.forecast --horizon 7
"""
from __future__ import annotations

import argparse
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlmodel import Session, delete, select

from app.config import settings
from app.db import engine, init_db
from app.models import Forecast, ModelRun

# Service level for asymmetric production bias (see config.py)

from .features import (
    FEATURE_COLS,
    add_calendar_features,
    add_lag_features,
    build_training_frame,
    top_n_skus,
)

warnings.filterwarnings("ignore")


def active(db: Session, algorithm: str) -> ModelRun | None:
    return db.exec(
        select(ModelRun)
        .where(ModelRun.algorithm == algorithm)
        .where(ModelRun.is_active == True)  # noqa: E712
        .order_by(ModelRun.id.desc())
    ).first()


def _build_future_regressors(future: pd.DataFrame, db_session) -> pd.DataFrame:
    """Attach is_quincena, is_holiday, tavg to a Prophet future dataframe.

    For dates beyond the weather table we use the historical same-day-of-year
    average (Monterrey weather is very seasonal, so this is a decent proxy).
    """
    from app.models import Holiday, Weather
    from sqlmodel import select

    holidays = {h.date: h for h in db_session.exec(select(Holiday)).all()}
    weather_rows = db_session.exec(select(Weather)).all()
    wmap = {w.date: w.tavg for w in weather_rows}

    # Build a day-of-year → avg tavg lookup for extrapolation
    from collections import defaultdict
    doy_tavg: dict[int, list[float]] = defaultdict(list)
    for w in weather_rows:
        if w.tavg is not None:
            doy_tavg[w.date.timetuple().tm_yday].append(w.tavg)
    doy_avg = {doy: sum(vs) / len(vs) for doy, vs in doy_tavg.items() if vs}

    is_quincena, is_holiday, tavg_col = [], [], []
    for ds in future["ds"]:
        d = ds.date() if hasattr(ds, "date") else ds
        h = holidays.get(d)
        # A date can be BOTH a holiday and quincena — set both flags
        is_q = 1 if (d.day in (1, 15)) else 0
        is_h = 1 if (h and not h.is_quincena) else 0
        is_quincena.append(is_q)
        is_holiday.append(is_h)

        t = wmap.get(d)
        if t is None:
            t = doy_avg.get(d.timetuple().tm_yday, 22.0)
        tavg_col.append(t)

    future = future.copy()
    future["is_quincena"] = is_quincena
    future["is_holiday"] = is_holiday
    future["tavg"] = tavg_col
    return future


def prophet_predict(df: pd.DataFrame, horizon: int, db_session=None, start_date: date | None = None):
    """Forecast `horizon` days starting from tomorrow (wall-clock today + 1).

    Prophet extrapolates its learned yearly/weekly seasonality forward any number
    of days, so even if training data ends in Feb 2026 we can forecast May 2026
    using the seasonal patterns observed in May 2022–2025.

    Now also includes exogenous regressors: is_quincena, is_holiday, tavg — the
    three features that most directly affect bakery demand in Monterrey.
    """
    from prophet import Prophet
    m = Prophet(
        yearly_seasonality=True, weekly_seasonality=True, daily_seasonality=False,
        interval_width=0.80,
    )
    m.add_country_holidays(country_name="MX")

    # Add exogenous regressors if DB session available
    use_regressors = db_session is not None and all(
        c in df.columns for c in ("is_quincena", "is_holiday", "tavg")
    )
    if use_regressors:
        m.add_regressor("is_quincena", mode="additive")
        m.add_regressor("is_holiday", mode="additive")
        m.add_regressor("tavg", mode="additive")
        train_cols = ["ds", "y", "is_quincena", "is_holiday", "tavg"]
    else:
        train_cols = ["ds", "y"]

    m.fit(df[train_cols])

    # How many days from the last training date to (today + horizon)?
    data_end = df["ds"].max().date()
    today_ = date.today()
    total_periods = max(horizon, (today_ - data_end).days + horizon)
    future = m.make_future_dataframe(periods=total_periods, freq="D")

    if use_regressors:
        future = _build_future_regressors(future, db_session)

    fc_full = m.predict(future)

    # Return `horizon` days starting from start_date (default: tomorrow)
    start = start_date if start_date else today_ + timedelta(days=1)
    end   = start + timedelta(days=horizon - 1)
    fc = fc_full[(fc_full["ds"].dt.date >= start) & (fc_full["ds"].dt.date <= end)]
    return fc


def upsert_forecasts(db: Session, rows: list[Forecast]) -> int:
    """Replace any existing forecasts for the same (branch, sku, bake_date)."""
    keys = {(r.branch, r.sku, r.bake_date) for r in rows}
    if keys:
        existing = db.exec(select(Forecast)).all()
        for f in existing:
            if (f.branch, f.sku, f.bake_date) in keys:
                db.delete(f)
        db.commit()
    db.add_all(rows)
    db.commit()
    return len(rows)


def forecast_branch(db: Session, branch: str, horizon: int, top_n: int, version: str, start_date: date | None = None) -> int:
    # Only wipe forecasts in the date range we're about to write so we don't
    # delete other weeks when generating just the next 7 days.
    if start_date:
        end_date = start_date + timedelta(days=horizon - 1)
        old = db.exec(
            select(Forecast)
            .where(Forecast.branch == branch)
            .where(Forecast.bake_date >= start_date)
            .where(Forecast.bake_date <= end_date)
        ).all()
    else:
        old = db.exec(select(Forecast).where(Forecast.branch == branch)).all()
    for f in old:
        db.delete(f)
    db.commit()

    skus = top_n_skus(db, branch, n=top_n)
    out: list[Forecast] = []
    for sku, item_name in skus:
        df = build_training_frame(db, branch, sku)
        if len(df) < 30:
            print(f"  [{branch}] {sku}: skip ({len(df)} rows)")
            continue
        try:
            fc = prophet_predict(df, horizon=horizon, db_session=db, start_date=start_date)
        except Exception as e:
            print(f"  [{branch}] {sku}: prophet error {e}")
            continue
        for _, r in fc.iterrows():
            bake_date = r["ds"].date()
            yhat_raw = float(r["yhat"])
            lo = max(0.0, float(r["yhat_lower"]))
            hi = max(0.0, float(r["yhat_upper"]))
            # Asymmetric production target: shift from median toward the upper
            # CI proportional to the service_level. At 0.50 → yhat (median),
            # at 1.0 → yhat_upper. E.g. 0.65 means "produce 30% of the way
            # between the median and the 90th percentile."
            sl = settings.service_level
            alpha = max(0.0, min(1.0, (sl - 0.5) / 0.5))  # 0 at sl=0.5, 1 at sl=1.0
            yhat = max(0.0, yhat_raw + alpha * (hi - yhat_raw))
            out.append(Forecast(
                branch=branch, sku=sku, item_name=item_name,
                bake_date=bake_date,
                predicted_units=round(yhat, 2),
                confidence_low=round(lo, 2),
                confidence_high=round(hi, 2),
                model_version=version, algorithm="prophet",
                generated_at=datetime.utcnow(),
            ))
        print(f"  [{branch}] {sku}: {len(fc)} predictions written")
    n = upsert_forecasts(db, out)
    return n


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--horizon", type=int, default=7)
    ap.add_argument("--branch", default="all")
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--start", type=str, default=None,
                    help="ISO date to start forecasts from (e.g. 2026-05-30). Defaults to tomorrow.")
    args = ap.parse_args()

    start_date = date.fromisoformat(args.start) if args.start else None

    init_db()
    with Session(engine) as db:
        active_run = active(db, "prophet")
        if not active_run:
            raise SystemExit("No active Prophet model — run `python -m batch.train` first.")
        version = active_run.model_version
        print(f"Active version: {version}  start: {start_date or 'tomorrow'}  horizon: {args.horizon}")

        branches = settings.branches if args.branch == "all" else [args.branch]
        total = 0
        for b in branches:
            n = forecast_branch(db, b, args.horizon, args.top_n, version, start_date=start_date)
            total += n
        print(f"\nWrote {total} forecast rows ({args.horizon} days from {start_date or 'tomorrow'}).")


if __name__ == "__main__":
    main()
