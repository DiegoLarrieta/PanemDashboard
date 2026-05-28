"""Seed panem.db with POS sales history, users, holidays, weather.

Usage:
    python -m batch.seed --data-dir "../../Complete Data"

The script is idempotent: re-running it wipes sales_history before loading.
Users are inserted only if missing (no clobber).
"""
from __future__ import annotations

import argparse
import glob
import re
from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd
from sqlmodel import Session, delete, select

from app.auth import hash_password
from app.config import settings
from app.db import engine, init_db
from app.models import Holiday, SalesHistory, User, Weather

# Mapping from filename token → canonical branch name (matches settings.branches).
BRANCH_FROM_FILENAME = {
    "Punto-Valle": "Punto Valle",
    "Punto Valle": "Punto Valle",
    "Hotel-Kavia": "Hotel Kavia",
    "Hotel Kavia": "Hotel Kavia",
    "Plaza-QIN": "Plaza QIN",
    "Plaza QIN": "Plaza QIN",
    "Hospital-Zambrano": "Hospital Zambrano",
    "Hospital Zambrano": "Hospital Zambrano",
    "Carreta": "La Carreta",
    "La-Carreta": "La Carreta",
    "Plaza-Nativa": "Plaza Nativa",
    "Plaza Nativa": "Plaza Nativa",
    "Credi-Club": "Credi Club",
    "Credi Club": "Credi Club",
}

FILENAME_RE = re.compile(r"detail_Panem-?(.+?)_(\d{4}-\d{2}-\d{2})_(\d{4}-\d{2}-\d{2})\.csv$")


def branch_from_filename(p: Path) -> str | None:
    m = FILENAME_RE.search(p.name)
    if not m:
        return None
    token = m.group(1).strip()
    for k, v in BRANCH_FROM_FILENAME.items():
        if k.lower() in token.lower():
            return v
    return None


def load_pos_csvs(data_dir: Path) -> pd.DataFrame:
    """Load and concatenate every detail_Panem-*.csv under data_dir."""
    files = sorted(glob.glob(str(data_dir / "**/detail_Panem*.csv"), recursive=True))
    if not files:
        files = sorted(glob.glob(str(data_dir / "detail_Panem*.csv")))
    if not files:
        raise SystemExit(f"No POS CSVs found in {data_dir}")
    frames = []
    for f in files:
        try:
            df = pd.read_csv(f, low_memory=False)
        except Exception as e:
            print(f"  ! skipping {f}: {e}")
            continue
        if "is_modifier" in df.columns:
            df = df[df["is_modifier"] != True]  # noqa: E712
        b = branch_from_filename(Path(f))
        if b:
            df["__branch__"] = b
        frames.append(df)
        print(f"  + {Path(f).name}: {len(df):,} rows (branch={b})")
    return pd.concat(frames, ignore_index=True)


def aggregate_daily(df: pd.DataFrame) -> pd.DataFrame:
    """Aggregate to (branch, sku, date) → qty_sold, revenue, unit_price."""
    if "operating_date" in df.columns:
        df["date"] = pd.to_datetime(df["operating_date"], errors="coerce").dt.date
    elif "fecha" in df.columns:
        df["date"] = pd.to_datetime(df["fecha"], errors="coerce").dt.date
    else:
        raise SystemExit("No operating_date / fecha column found")

    sku_col = "clave_platillo" if "clave_platillo" in df.columns else "sku"
    name_col = next((c for c in ["item", "description", "platillo", "item_name", "nombre"] if c in df.columns), None)
    qty_col = next((c for c in ["quantity", "qty_sold", "cantidad", "qty"] if c in df.columns), None)
    rev_col = next((c for c in ["total_item", "total", "revenue"] if c in df.columns), None)
    if qty_col is None:
        raise SystemExit("No qty_sold column found")
    branch_col = "__branch__" if "__branch__" in df.columns else (
        "sucursal" if "sucursal" in df.columns else None
    )
    if branch_col is None:
        raise SystemExit("No branch column found")

    df = df.dropna(subset=["date", sku_col])
    agg_dict = {qty_col: "sum"}
    if rev_col:
        agg_dict[rev_col] = "sum"

    grp_cols = [branch_col, sku_col, "date"]
    if name_col:
        grp_cols.append(name_col)
    g = df.groupby(grp_cols, dropna=False).agg(agg_dict).reset_index()
    g = g.rename(columns={
        branch_col: "branch",
        sku_col: "sku",
        name_col or "_skip_": "item_name",
        qty_col: "qty_sold",
        rev_col or "_skip_": "revenue",
    })
    if "item_name" not in g.columns:
        g["item_name"] = ""
    if "revenue" not in g.columns:
        g["revenue"] = 0.0
    g["unit_price"] = (g["revenue"] / g["qty_sold"]).replace([float("inf"), -float("inf")], 0).fillna(0)
    return g[["branch", "sku", "item_name", "date", "qty_sold", "unit_price", "revenue"]]


def seed_sales(df: pd.DataFrame) -> int:
    with Session(engine) as s:
        s.exec(delete(SalesHistory))
        s.commit()
        rows = [
            SalesHistory(
                branch=r.branch,
                sku=str(r.sku),
                item_name=str(r.item_name)[:200],
                sale_date=r.date,
                qty_sold=float(r.qty_sold),
                unit_price=float(r.unit_price),
                revenue=float(r.revenue),
            )
            for r in df.itertuples()
        ]
        s.add_all(rows)
        s.commit()
        return len(rows)


def seed_holidays() -> int:
    """Mexican public holidays + quincena dates (1st and 15th of each month).

    IMPORTANT: a date can be BOTH a holiday AND a quincena (e.g. Jan 1st is
    Año Nuevo and also payday). We store one row per date but set BOTH flags.
    Previously the dedup logic lost the quincena signal for holiday dates.
    """
    fixed = [
        (1, 1,  "Año Nuevo"),
        (2, 5,  "Día de la Constitución"),
        (3, 21, "Natalicio Benito Juárez"),
        (5, 1,  "Día del Trabajo"),
        (9, 16, "Día de la Independencia"),
        (11, 20, "Revolución Mexicana"),
        (12, 12, "Día de la Virgen"),
        (12, 24, "Nochebuena"),
        (12, 25, "Navidad"),
        (12, 31, "Fin de Año"),
    ]
    # Build a map: date → (name, is_quincena, is_holiday_flag)
    date_map: dict[date, dict] = {}
    for y in range(2022, 2027):
        # Mark quincena dates first (1st and 15th of every month)
        for m in range(1, 13):
            for d_ in (1, 15):
                dt = date(y, m, d_)
                date_map[dt] = {"name": "Quincena", "is_quincena": True, "is_holiday": False}
        # Now overlay public holidays — if the date is already a quincena, keep both flags
        for (m, d_, name) in fixed:
            dt = date(y, m, d_)
            if dt in date_map and date_map[dt]["is_quincena"]:
                # Both holiday AND quincena — preserve both signals
                date_map[dt]["name"] = f"{name} + Quincena"
                date_map[dt]["is_holiday"] = True
            else:
                date_map[dt] = {"name": name, "is_quincena": False, "is_holiday": True}

    with Session(engine) as s:
        s.exec(delete(Holiday))
        s.commit()
        for dt, info in sorted(date_map.items()):
            s.add(Holiday(
                date=dt,
                name=info["name"],
                is_quincena=info["is_quincena"],
            ))
        s.commit()
    return len(date_map)


def seed_weather(start: date, end: date) -> int:
    """Synthetic Monterrey weather. Replace with real CSV import if available."""
    import math
    rows = []
    d = start
    while d <= end:
        doy = d.timetuple().tm_yday
        # Monterrey: ~14C in Jan, ~30C in July.
        tavg = 22 + 8 * math.sin((doy - 100) / 365 * 2 * math.pi)
        cold = -1 if tavg < 16 else (1 if tavg > 28 else 0)
        rows.append(Weather(date=d, tavg=round(tavg, 1), cold_or_warm_num=cold))
        d += timedelta(days=1)
    with Session(engine) as s:
        s.exec(delete(Weather))
        s.commit()
        s.add_all(rows)
        s.commit()
    return len(rows)


def seed_users() -> None:
    defaults = [
        ("operator", "panem", "operator"),
        ("analyst",  "panem", "analyst"),
    ]
    with Session(engine) as s:
        for username, pw, role in defaults:
            existing = s.exec(select(User).where(User.username == username)).first()
            if existing:
                continue
            s.add(User(username=username, password_hash=hash_password(pw), role=role))
        s.commit()
    print(f"  Users ready: {', '.join(u for u, _, _ in defaults)}")


BRANCH_NAME_MAP = {
    "Panem - Punto Valle":      "Punto Valle",
    "Panem - Carreta":          "La Carreta",
    "Panem - Credi Club":       "Credi Club",
    "Panem - Hospital Zambrano":"Hospital Zambrano",
    "Panem - Hotel Kavia":      "Hotel Kavia",
    "Panem - Plaza Nativa":     "Plaza Nativa",
    "Panem - Plaza QIN":        "Plaza QIN",
}


def load_branch_csvs(branches_dir: Path) -> pd.DataFrame:
    """Load the 7 pre-aggregated branch3_*.csv files produced by the Evidence notebooks."""

    files = sorted(branches_dir.glob("branch3_*.csv"))

    if not files:
        raise SystemExit(f"No branch3_*.csv files found in {branches_dir}")

    frames = []

    for f in files:

        df = pd.read_csv(f, low_memory=False)

        # CLEAN COLUMN NAMES FIRST
        df.columns = (
            df.columns
            .str.strip()
            .str.lower()
            .str.replace(" ", "_")
        )

        # Parse dates
        df["operating_date"] = pd.to_datetime(
            df["operating_date"],
            errors="coerce"
        )

        df["date"] = df["operating_date"].dt.date

        # Normalize branch names
        df["branch"] = (
            df["sucursal"]
            .astype(str)
            .str.strip()
            .map(BRANCH_NAME_MAP)
            .fillna(df["sucursal"])
        )

        # Rename columns
        df = df.rename(columns={
            "item": "sku",
            "quantity": "qty_sold"
        })

        # Clean item names
        df["item_name"] = (
            df["sku"]
            .astype(str)
            .str.strip()
        )

        # Numeric cleanup
        df["unit_price"] = pd.to_numeric(
            df.get("unit_price", 0.0),
            errors="coerce"
        ).fillna(0.0)

        df["revenue"] = pd.to_numeric(
            df.get("revenue", 0.0),
            errors="coerce"
        ).fillna(0.0)

        df["qty_sold"] = pd.to_numeric(
            df.get("qty_sold", 0.0),
            errors="coerce"
        ).fillna(0.0)

        frames.append(
            df[
                [
                    "branch",
                    "sku",
                    "item_name",
                    "date",
                    "qty_sold",
                    "unit_price",
                    "revenue"
                ]
            ]
        )

        print(f"  + {f.name}: {len(df):,} rows")

    return pd.concat(frames, ignore_index=True)


def seed_weather_from_branches(branches_dir: Path) -> int:
    """Seed weather table from the actual tavg/cold_or_warm data in the branch CSVs."""

    files = sorted(branches_dir.glob("branch3_*.csv"))

    frames = []

    for f in files:

        df = pd.read_csv(f, low_memory=False)

        # CLEAN COLUMN NAMES
        df.columns = (
            df.columns
            .str.strip()
            .str.lower()
            .str.replace(" ", "_")
        )

        # Keep only needed columns
        df = df[["operating_date", "tavg", "cold_or_warm"]]

        df["date"] = pd.to_datetime(
            df["operating_date"],
            errors="coerce"
        ).dt.date

        frames.append(
            df[["date", "tavg", "cold_or_warm"]]
        )

    combined = pd.concat(frames).dropna(subset=["tavg"])

    combined = (
        combined
        .groupby("date")
        .first()
        .reset_index()
    )

    combined["cold_or_warm_num"] = combined["cold_or_warm"].map(
        {
            "cold": -1,
            "warm": 1
        }
    ).fillna(0).astype(int)

    rows = [
        Weather(
            date=r.date,
            tavg=float(r.tavg),
            cold_or_warm_num=int(r.cold_or_warm_num)
        )
        for r in combined.itertuples()
    ]

    with Session(engine) as s:

        s.exec(delete(Weather))
        s.commit()

        s.add_all(rows)
        s.commit()

    return len(rows)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-dir", required=True,
                    help="Complete Data folder — pass the Branches/ subfolder or its parent")
    ap.add_argument("--skip-sales", action="store_true", help="Skip loading CSVs")
    args = ap.parse_args()

    init_db()

    data_dir = Path(args.data_dir).expanduser().resolve()
    # Accept either .../Complete Data  or  .../Complete Data/Branches
    branches_dir = data_dir / "Branches" if (data_dir / "Branches").is_dir() else data_dir

    if not args.skip_sales:
        print(f"Loading branch CSVs from: {branches_dir}")
        daily = load_branch_csvs(branches_dir)
        print(f"  Loaded {len(daily):,} (branch, sku, date) rows")
        n = seed_sales(daily)
        print(f"  sales_history: {n:,} rows")

        start = daily["date"].min()
        end = max(daily["date"].max(), date.today() + timedelta(days=14))
    else:
        start = date(2022, 1, 1)
        end = date.today() + timedelta(days=14)

    nh = seed_holidays()
    print(f"  holidays: {nh} rows")

    # Use real Monterrey weather from the branch CSVs, not synthetic values
    if not args.skip_sales:
        nw = seed_weather_from_branches(branches_dir)
        print(f"  weather (real): {nw} rows ({start} → {end})")
    else:
        nw = seed_weather(start, end)
        print(f"  weather (synthetic): {nw} rows ({start} → {end})")

    seed_users()
    print("Seed complete.")


if __name__ == "__main__":
    main()
