"""Feature engineering shared by train.py and forecast.py.

Lifted from Panem/Real Models/Evidence_Demand_Forecasting.ipynb:
  lag_7, lag_14, lag_21, lag_365
  qty_roll_7, qty_roll_30, qty_roll_90
  is_quincena, is_holiday, tavg, cold_or_warm_num
  week_number, month, day_of_week
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import Optional

import numpy as np
import pandas as pd
from sqlmodel import Session, select

from app.models import Actual, Holiday, SalesHistory, Weather


def load_sales(db: Session, branch: str, sku: str) -> pd.DataFrame:
    rows = db.exec(
        select(SalesHistory)
        .where(SalesHistory.branch == branch)
        .where(SalesHistory.sku == sku)
        .order_by(SalesHistory.sale_date)
    ).all()
    if not rows:
        return pd.DataFrame(columns=["ds", "y", "unit_price"])
    df = pd.DataFrame([{
        "ds": r.sale_date,
        "y": r.qty_sold,
        "unit_price": r.unit_price,
        "item_name": r.item_name,
    } for r in rows])
    df["ds"] = pd.to_datetime(df["ds"])
    return df


def overlay_actuals(db: Session, branch: str, sku: str, df: pd.DataFrame) -> pd.DataFrame:
    """Replace y with operator-recorded qty_sold for dates that have a recorded Actual.

    This is the feedback signal: the model retrains on what really happened,
    not the POS snapshot.
    """
    if df.empty:
        return df
    acts = db.exec(
        select(Actual).where(Actual.branch == branch).where(Actual.sku == sku)
    ).all()
    if not acts:
        return df
    idx = df.set_index(df["ds"].dt.date).copy()
    for a in acts:
        if a.bake_date in idx.index:
            idx.at[a.bake_date, "y"] = a.qty_sold
        else:
            new = pd.DataFrame([{
                "ds": pd.to_datetime(a.bake_date),
                "y": a.qty_sold,
                "unit_price": idx["unit_price"].iloc[-1] if "unit_price" in idx else 0.0,
                "item_name": idx["item_name"].iloc[-1] if "item_name" in idx else "",
            }])
            new.index = new["ds"].dt.date
            idx = pd.concat([idx, new])
    return idx.sort_index().reset_index(drop=True)


def fill_calendar(df: pd.DataFrame) -> pd.DataFrame:
    """Ensure one row per calendar day between min/max ds (missing days → y=0).

    Preserves all non-'y' columns by forward-filling (for metadata like
    unit_price and item_name) and filling y with 0 for missing days.
    """
    if df.empty:
        return df
    rng = pd.date_range(df["ds"].min(), df["ds"].max(), freq="D")
    # Aggregate y by date, but keep other columns from the first occurrence
    g = df.groupby("ds", as_index=False).agg(
        {c: "sum" if c == "y" else "first" for c in df.columns if c != "ds"}
    )
    g = g.set_index("ds").reindex(rng)
    g["y"] = g["y"].fillna(0)
    # Forward-fill metadata columns (unit_price, item_name, etc.)
    for c in g.columns:
        if c != "y":
            g[c] = g[c].ffill().bfill()
    g = g.rename_axis("ds").reset_index()
    return g


def add_calendar_features(df: pd.DataFrame, db: Session) -> pd.DataFrame:
    """Attach holiday / quincena / weather features."""
    if df.empty:
        return df
    df = df.copy()
    df["day_of_week"] = df["ds"].dt.dayofweek
    df["week_number"] = df["ds"].dt.isocalendar().week.astype(int)
    df["month"] = df["ds"].dt.month

    holidays = db.exec(select(Holiday)).all()
    hmap = {h.date: h for h in holidays}
    # A date can be BOTH a holiday and a quincena (e.g. Jan 1, May 1).
    # Use day-of-month to detect quincena (1st/15th) regardless of DB row.
    df["is_holiday"] = df["ds"].dt.date.map(lambda d: 1 if d in hmap and not hmap[d].is_quincena else 0)
    df["is_quincena"] = df["ds"].dt.day.isin([1, 15]).astype(int)

    weather = db.exec(select(Weather)).all()
    wmap = {w.date: w for w in weather}
    df["tavg"] = df["ds"].dt.date.map(lambda d: wmap[d].tavg if d in wmap else np.nan)
    df["cold_or_warm_num"] = df["ds"].dt.date.map(lambda d: wmap[d].cold_or_warm_num if d in wmap else 0)
    df["tavg"] = df["tavg"].interpolate().bfill().ffill()
    return df


def add_lag_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["lag_7"]   = df["y"].shift(7)
    df["lag_14"]  = df["y"].shift(14)
    df["lag_21"]  = df["y"].shift(21)
    df["lag_365"] = df["y"].shift(365)
    df["qty_roll_7"]  = df["y"].shift(1).rolling(7).mean()
    df["qty_roll_30"] = df["y"].shift(1).rolling(30).mean()
    df["qty_roll_90"] = df["y"].shift(1).rolling(90).mean()
    return df


FEATURE_COLS = [
    "lag_7", "lag_14", "lag_21", "lag_365",
    "qty_roll_7", "qty_roll_30", "qty_roll_90",
    "is_quincena", "is_holiday", "tavg", "cold_or_warm_num",
    "week_number", "month", "day_of_week",
]


def build_training_frame(db: Session, branch: str, sku: str) -> pd.DataFrame:
    raw = load_sales(db, branch, sku)
    raw = overlay_actuals(db, branch, sku, raw)
    raw = fill_calendar(raw)
    raw = add_calendar_features(raw, db)
    raw = add_lag_features(raw)
    return raw


def top_n_skus(db: Session, branch: str, n: int = 5, lookback_days: int = 0) -> list[tuple[str, str]]:
    """Return [(sku, item_name)] for the top-n best-selling SKUs by all-time volume.

    Matches the Evidence_Demand_Forecasting notebooks which rank products on
    total quantity across the full dataset (no rolling window).
    lookback_days is kept for API compatibility but ignored.
    """
    from sqlalchemy import func
    stmt = (
        select(
            SalesHistory.sku,
            SalesHistory.item_name,
            func.sum(SalesHistory.qty_sold).label("total"),
        )
        .where(SalesHistory.branch == branch)
        .group_by(SalesHistory.sku, SalesHistory.item_name)
        .order_by(func.sum(SalesHistory.qty_sold).desc())
        .limit(n)
    )
    rows = db.exec(stmt).all()
    return [(r[0], r[1] or "") for r in rows]
