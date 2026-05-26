"""Analytics API routes — Page 4."""
from __future__ import annotations

import datetime as _dt
import glob
import os
from collections import defaultdict
from functools import lru_cache
from typing import Optional

import pandas as pd
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlmodel import Session, select

from ..auth import current_user
from ..config import settings
from ..db import get_session
from ..models import Holiday, SalesHistory, User, Weather

router = APIRouter()

# ---------------------------------------------------------------------------
# CSV data loaders (cached at module level — loaded once on first request)
# ---------------------------------------------------------------------------

# website/app/routes/analytics.py  →  up 5 dirs  →  "Python challenge/"
_CHALLENGE_DIR  = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
_RAW_CSV_DIR    = os.path.join(_CHALLENGE_DIR, "Complete Data", '"Raw" csv')
_DETAIL_CSV_DIR = os.path.join(_CHALLENGE_DIR, "Complete Data", "all csv's")

_branch_df: Optional[pd.DataFrame] = None
_hourly_df: Optional[pd.DataFrame] = None


def _get_branch_df() -> pd.DataFrame:
    global _branch_df
    if _branch_df is None:
        frames = []
        for f in glob.glob(os.path.join(_RAW_CSV_DIR, "*.csv")):
            frames.append(pd.read_csv(f, parse_dates=["operating_date"]))
        df = pd.concat(frames, ignore_index=True)
        df = df[df["quantity"] > 0].copy()
        _DOW_ES = {
            "lunes": "Mon", "martes": "Tue", "miercoles": "Wed",
            "jueves": "Thu", "viernes": "Fri", "sabado": "Sat", "domingo": "Sun"
        }
        df = df.assign(
            branch = df["sucursal"].str.replace("Panem - ", "", regex=False),
            year   = df["operating_date"].dt.year,
            month  = df["operating_date"].dt.month,
            dow    = df["day_name"].str.lower().map(_DOW_ES).fillna(df["day_name"]),
        )
        _branch_df = df
    return _branch_df


def _get_hourly_df() -> pd.DataFrame:
    global _hourly_df
    if _hourly_df is None:
        frames = []
        for f in glob.glob(os.path.join(_DETAIL_CSV_DIR, "*.csv")):
            try:
                chunk = pd.read_csv(
                    f,
                    usecols=["sucursal", "captured_time", "item", "quantity", "is_modifier"],
                    low_memory=False,
                )
                frames.append(chunk)
            except Exception:
                pass
        df = pd.concat(frames, ignore_index=True)
        df = df[df["is_modifier"] != True].copy()
        df = df[df["quantity"] > 0].copy()
        # Parse timestamps explicitly — some files have mixed types
        df["captured_time"] = pd.to_datetime(df["captured_time"], errors="coerce")
        df = df.dropna(subset=["captured_time"])
        df = df.assign(
            branch = df["sucursal"].str.replace("Panem - ", "", regex=False),
            hour   = df["captured_time"].dt.hour,
            dow    = df["captured_time"].dt.day_name().str[:3],
            month  = df["captured_time"].dt.month,
            year   = df["captured_time"].dt.year,
        )
        _hourly_df = df
    return _hourly_df

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _branch_filter(stmt, branch: str):
    """Append a branch WHERE clause when branch != 'all'."""
    if branch != "all":
        stmt = stmt.where(SalesHistory.branch == branch)
    return stmt


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/api/analytics/sales-over-time")
def sales_over_time(
    branch: str = Query("all"),
    granularity: str = Query("month"),
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """
    Returns per-branch (or single-branch) time-series of qty_sold.
    granularity: "month" → YYYY-MM labels; "week" → ISO week YYYY-WXX labels.
    """
    stmt = select(
        SalesHistory.branch,
        SalesHistory.sale_date,
        func.sum(SalesHistory.qty_sold).label("qty"),
    )
    stmt = _branch_filter(stmt, branch)
    stmt = stmt.group_by(SalesHistory.branch, SalesHistory.sale_date).order_by(
        SalesHistory.sale_date
    )
    rows = db.exec(stmt).all()

    # Aggregate into the requested granularity per branch
    # rows: (branch, sale_date, qty)
    branch_data: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    all_labels: set[str] = set()

    for r_branch, r_date, r_qty in rows:
        if granularity == "week":
            iso = r_date.isocalendar()
            label = f"{iso[0]}-W{iso[1]:02d}"
        else:
            label = r_date.strftime("%Y-%m")
        branch_data[r_branch][label] += float(r_qty or 0)
        all_labels.add(label)

    sorted_labels = sorted(all_labels)

    datasets = []
    branches = sorted(branch_data.keys()) if branch == "all" else [branch]
    for b in branches:
        series = branch_data.get(b, {})
        datasets.append(
            {
                "branch": b,
                "data": [round(series.get(lbl, 0), 1) for lbl in sorted_labels],
            }
        )

    return {"labels": sorted_labels, "datasets": datasets}


@router.get("/api/analytics/top-products")
def top_products(
    branch: str = Query("all"),
    top_n: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """Top N products by total qty_sold for the selected branch(es)."""
    stmt = select(
        SalesHistory.item_name,
        func.sum(SalesHistory.qty_sold).label("total_qty"),
    )
    stmt = _branch_filter(stmt, branch)
    stmt = stmt.group_by(SalesHistory.item_name).order_by(
        func.sum(SalesHistory.qty_sold).desc()
    )
    rows = db.exec(stmt).all()

    top = rows[:top_n]
    labels = [r[0] or "Unknown" for r in top]
    values = [round(float(r[1] or 0), 1) for r in top]
    return {"labels": labels, "values": values}


@router.get("/api/analytics/weekday-heatmap")
def weekday_heatmap(
    branch: str = Query("all"),
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """
    Top-10 products × 7 weekdays — avg qty_sold per (product, weekday).
    Returns:
      { days: [...], products: [...], matrix: [[...]] }
    matrix[product_idx][day_idx] = avg qty
    """
    # Fetch top-10 products by volume first
    top_stmt = select(
        SalesHistory.item_name,
        func.sum(SalesHistory.qty_sold).label("total"),
    )
    top_stmt = _branch_filter(top_stmt, branch)
    top_stmt = top_stmt.group_by(SalesHistory.item_name).order_by(
        func.sum(SalesHistory.qty_sold).desc()
    )
    top_rows = db.exec(top_stmt).all()
    # Show top-5 in the heatmap (matches what the JS renders).
    top_products_list = [r[0] for r in top_rows[:5] if r[0]]

    if not top_products_list:
        return {"days": _DAY_NAMES, "products": [], "matrix": []}

    # Fetch all (item_name, sale_date, qty) for those products
    detail_stmt = select(
        SalesHistory.item_name,
        SalesHistory.sale_date,
        func.sum(SalesHistory.qty_sold).label("qty"),
    )
    detail_stmt = _branch_filter(detail_stmt, branch)
    detail_stmt = detail_stmt.where(SalesHistory.item_name.in_(top_products_list))
    detail_stmt = detail_stmt.group_by(
        SalesHistory.item_name, SalesHistory.sale_date
    )
    detail_rows = db.exec(detail_stmt).all()

    # Accumulate sums and counts per (product, weekday)
    sums: dict[tuple[str, int], float] = defaultdict(float)
    counts: dict[tuple[str, int], int] = defaultdict(int)

    for item_name, sale_date, qty in detail_rows:
        wd = sale_date.weekday()  # 0=Mon … 6=Sun
        sums[(item_name, wd)] += float(qty or 0)
        counts[(item_name, wd)] += 1

    matrix = []
    for product in top_products_list:
        row = []
        for day_idx in range(7):
            key = (product, day_idx)
            if counts[key]:
                row.append(round(sums[key] / counts[key], 2))
            else:
                row.append(0.0)
        matrix.append(row)

    return {"days": _DAY_NAMES, "products": top_products_list, "matrix": matrix}


@router.get("/api/analytics/monthly-seasonality")
def monthly_seasonality(
    branch: str = Query("all"),
    sku: Optional[str] = Query(None),
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """
    Avg daily qty by calendar month (1–12) across all years.
    Returns: { labels: ["Jan",…,"Dec"], values: [...] }
    """
    # Group by (sale_date) so we get one row per day with the total across the
    # selected branch(es). func.sum(qty) ensures multi-branch days are summed
    # into a single row before averaging by month.
    stmt = select(
        SalesHistory.sale_date,
        func.sum(SalesHistory.qty_sold).label("qty"),
    )
    stmt = _branch_filter(stmt, branch)
    if sku:
        # The seeded DB uses item_name == sku, accept either column to be safe.
        stmt = stmt.where(
            (SalesHistory.sku == sku) | (SalesHistory.item_name == sku)
        )
    stmt = stmt.group_by(SalesHistory.sale_date)
    rows = db.exec(stmt).all()

    # Accumulate per month. counts[m] = number of distinct days in month m.
    sums: dict[int, float] = defaultdict(float)
    counts: dict[int, int] = defaultdict(int)
    for sale_date, qty in rows:
        m = sale_date.month
        sums[m] += float(qty or 0)
        counts[m] += 1

    month_labels = [
        "Jan", "Feb", "Mar", "Apr", "May", "Jun",
        "Jul", "Aug", "Sep", "Oct", "Nov", "Dec",
    ]
    values = []
    for m in range(1, 13):
        if counts[m]:
            values.append(round(sums[m] / counts[m], 2))
        else:
            values.append(0.0)

    return {"labels": month_labels, "values": values}


@router.get("/api/analytics/weather-impact")
def weather_impact(
    branch: str = Query("all"),
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """
    Avg daily total qty by weather category (cold / mild / warm).
    Joins sales_history with weather on sale_date.
    Returns: { cold: float, mild: float, warm: float }
    """
    # Build a daily-total sub-query from sales_history
    sales_stmt = select(
        SalesHistory.sale_date,
        func.sum(SalesHistory.qty_sold).label("daily_qty"),
    )
    sales_stmt = _branch_filter(sales_stmt, branch)
    sales_stmt = sales_stmt.group_by(SalesHistory.sale_date)
    daily_rows = db.exec(sales_stmt).all()  # (date, qty)

    if not daily_rows:
        return {"cold": 0.0, "mild": 0.0, "warm": 0.0}

    # Pull weather for those dates — bin by tavg so we get a real Mild bucket
    # (the seeded `cold_or_warm_num` is only -1/+1, never 0, so we can't use it here).
    dates = [r[0] for r in daily_rows]
    weather_rows = db.exec(
        select(Weather.date, Weather.tavg).where(Weather.date.in_(dates))
    ).all()
    weather_map = {r[0]: r[1] for r in weather_rows}

    def categorize(tavg: float) -> str:
        if tavg is None:
            return None
        if tavg < 18:   return "cold"
        if tavg > 28:   return "warm"
        return "mild"

    sums: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)

    for sale_date, daily_qty in daily_rows:
        tavg = weather_map.get(sale_date)
        cat = categorize(tavg)
        if cat is None:
            continue
        sums[cat] += float(daily_qty or 0)
        counts[cat] += 1

    result = {}
    for cat in ("cold", "mild", "warm"):
        result[cat] = round(sums[cat] / counts[cat], 2) if counts[cat] else 0.0
    return result


@router.get("/api/analytics/holiday-impact")
def holiday_impact(
    branch: str = Query("all"),
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """
    Avg daily total qty by holiday status.
    Returns: { labels: ["No holiday","Quincena","Holiday"], values: [...] }
    """
    # Daily totals
    sales_stmt = select(
        SalesHistory.sale_date,
        func.sum(SalesHistory.qty_sold).label("daily_qty"),
    )
    sales_stmt = _branch_filter(sales_stmt, branch)
    sales_stmt = sales_stmt.group_by(SalesHistory.sale_date)
    daily_rows = db.exec(sales_stmt).all()

    if not daily_rows:
        return {"labels": ["No holiday", "Quincena", "Holiday"], "values": [0.0, 0.0, 0.0]}

    dates = [r[0] for r in daily_rows]
    holiday_rows = db.exec(
        select(Holiday.date, Holiday.is_quincena).where(
            Holiday.date.in_(dates)
        )
    ).all()
    # date → "quincena" or "holiday"
    holiday_map: dict = {}
    for h_date, is_quincena in holiday_rows:
        holiday_map[h_date] = "quincena" if is_quincena else "holiday"

    sums: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)

    for sale_date, daily_qty in daily_rows:
        cat = holiday_map.get(sale_date, "none")
        sums[cat] += float(daily_qty or 0)
        counts[cat] += 1

    labels = ["No holiday", "Quincena", "Holiday"]
    keys = ["none", "quincena", "holiday"]
    values = [
        round(sums[k] / counts[k], 2) if counts[k] else 0.0 for k in keys
    ]
    return {"labels": labels, "values": values}


@router.get("/api/analytics/branch-comparison")
def branch_comparison(
    sku: str = Query(...),
    db: Session = Depends(get_session),
    user: User = Depends(current_user),
):
    """
    Total all-time sales for a given SKU, per branch.
    Returns: { labels: [...branches], values: [...total_qty] }
    """
    stmt = select(
        SalesHistory.branch,
        func.sum(SalesHistory.qty_sold).label("total_qty"),
    ).where(SalesHistory.sku == sku).group_by(SalesHistory.branch)
    rows = db.exec(stmt).all()

    # Preserve settings.branches order, fill missing with 0
    branch_map = {r[0]: float(r[1] or 0) for r in rows}
    labels = settings.branches
    values = [round(branch_map.get(b, 0.0), 1) for b in labels]
    return {"labels": labels, "values": values}


# ---------------------------------------------------------------------------
# Heatmap endpoint
# ---------------------------------------------------------------------------

_MONTH_LABELS = ["Jan","Feb","Mar","Apr","May","Jun",
                 "Jul","Aug","Sep","Oct","Nov","Dec"]
_DOW_ORDER    = ["Mon","Tue","Wed","Thu","Fri","Sat","Sun"]


@router.get("/api/analytics/heatmap")
def heatmap(
    view:   str = Query("monthly"),   # monthly | weekly | hourly
    branch: str = Query("all"),
    item:   str = Query("all"),
    year:   Optional[str] = Query(None),
    month:  Optional[str] = Query(None),
    user:   User = Depends(current_user),
):
    if view == "hourly":
        df = _get_hourly_df()
    else:
        df = _get_branch_df()

    # Branch filter
    if branch != "all":
        df = df[df["branch"] == branch]

    # Item filter
    if item and item != "all":
        df = df[df["item"].str.upper() == item.upper()]

    # Year filter (hourly + weekly)
    if year and year != "all":
        df = df[df["year"] == int(year)]

    # Month filter (hourly only)
    if month and month != "all":
        df = df[df["month"] == int(month)]

    if view == "monthly":
        # rows = month, cols = year
        pivot = (
            df.groupby(["year","month"])["quantity"].sum()
            .reset_index()
            .pivot(index="month", columns="year", values="quantity")
            .fillna(0)
        )
        pivot.index = [_MONTH_LABELS[m - 1] for m in pivot.index]
        cols = [str(c) for c in pivot.columns]

    elif view == "weekly":
        # rows = day-of-week, cols = month
        pivot = (
            df.groupby(["dow","month"])["quantity"].mean()
            .reset_index()
            .pivot(index="dow", columns="month", values="quantity")
            .reindex(_DOW_ORDER)
            .fillna(0)
        )
        pivot.columns = [_MONTH_LABELS[m - 1] for m in pivot.columns]
        cols = pivot.columns.tolist()

    else:  # hourly
        # rows = hour, cols = day-of-week
        pivot = (
            df.groupby(["hour","dow"])["quantity"].sum()
            .reset_index()
            .pivot(index="hour", columns="dow", values="quantity")
            .reindex(columns=_DOW_ORDER)
            .reindex(range(24))
            .fillna(0)
        )
        pivot.index = [f"{h:02d}:00" for h in range(24)]
        cols = _DOW_ORDER

    return {
        "z":    pivot.values.tolist(),
        "x":    cols,
        "y":    pivot.index.tolist(),
    }


@router.get("/api/analytics/heatmap-items")
def heatmap_items(
    branch: str = Query("all"),
    user:   User = Depends(current_user),
):
    """Return sorted list of unique item names for the heatmap filter."""
    df = _get_branch_df()
    if branch != "all":
        df = df[df["branch"] == branch]
    items = sorted(df["item"].dropna().unique().tolist())
    return {"items": items}
