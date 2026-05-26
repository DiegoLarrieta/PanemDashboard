"""Train Prophet + LightGBM per (branch, sku) with walk-forward validation.

- Reads sales_history overlaid with actuals (operator feedback).
- Persists per-(branch,sku) joblib bundles under models/v<N>/.
- Writes one model_runs row per algorithm with aggregate metrics.
- Marks the new version is_active=True ONLY if it beats the active one.

Usage:
    python -m batch.train --branch all --top-n 5
"""
from __future__ import annotations

import argparse
import json
import warnings
from datetime import date, datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlmodel import Session, select

from app.config import settings
from app.db import engine, init_db
from app.models import ModelRun

from .features import (
    FEATURE_COLS,
    build_training_frame,
    top_n_skus,
)

warnings.filterwarnings("ignore")


# ---------- Metrics ----------
def metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict[str, float]:
    y_true = np.asarray(y_true, dtype=float)
    y_pred = np.asarray(y_pred, dtype=float)
    err = y_pred - y_true
    abs_err = np.abs(err)
    mae = float(np.mean(abs_err))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    with np.errstate(divide="ignore", invalid="ignore"):
        pct = np.where(y_true > 0, abs_err / y_true, np.nan)
    mape = float(np.nanmean(pct)) if np.any(np.isfinite(pct)) else float("nan")
    acc20 = float(np.nanmean(pct <= 0.20)) if np.any(np.isfinite(pct)) else 0.0
    return {"mae": mae, "rmse": rmse, "mape": mape, "acc_20pct": acc20}


# ---------- Baseline (lag-7 naive) ----------
def naive_lag7(df: pd.DataFrame, test_idx: pd.Index) -> np.ndarray:
    return df.loc[test_idx, "lag_7"].fillna(0).values


# ---------- Prophet ----------
def fit_prophet(train: pd.DataFrame, horizon: int):
    from prophet import Prophet
    m = Prophet(
        yearly_seasonality=True, weekly_seasonality=True, daily_seasonality=False,
        interval_width=0.80,
    )
    m.add_country_holidays(country_name="MX")
    df = train[["ds", "y"]].copy()
    m.fit(df)
    future = m.make_future_dataframe(periods=horizon, freq="D")
    fc = m.predict(future)
    return m, fc


def prophet_walk_forward(df: pd.DataFrame, n_windows: int = 6, window: int = 7) -> tuple[list, list]:
    """Walk-forward: train on [start, T], predict next `window` days, slide n_windows times."""
    preds, trues = [], []
    if len(df) < window * (n_windows + 4):
        n_windows = max(1, (len(df) - window * 4) // window)
    for k in range(n_windows, 0, -1):
        cut = len(df) - k * window
        if cut < 60:
            continue
        train = df.iloc[:cut].copy()
        test  = df.iloc[cut:cut + window].copy()
        try:
            _, fc = fit_prophet(train, horizon=window)
        except Exception:
            continue
        yhat = fc.tail(window)["yhat"].values
        preds.extend(yhat.tolist())
        trues.extend(test["y"].values.tolist())
    return preds, trues


# ---------- LightGBM ----------
def fit_lgbm(train_X: pd.DataFrame, train_y: pd.Series):
    import lightgbm as lgb
    model = lgb.LGBMRegressor(
        n_estimators=400, learning_rate=0.05, num_leaves=31,
        min_child_samples=10, subsample=0.9, colsample_bytree=0.9,
        random_state=42, verbose=-1,
    )
    model.fit(train_X, train_y)
    return model


def lgbm_walk_forward(df: pd.DataFrame, n_windows: int = 6, window: int = 7) -> tuple[list, list, object]:
    """Returns (preds, trues, last_model_fit_on_full_data)."""
    preds, trues = [], []
    dff = df.dropna(subset=FEATURE_COLS + ["y"]).reset_index(drop=True)
    if len(dff) < window * (n_windows + 2):
        n_windows = max(1, (len(dff) - window * 2) // window)
    for k in range(n_windows, 0, -1):
        cut = len(dff) - k * window
        if cut < 60:
            continue
        train = dff.iloc[:cut]
        test  = dff.iloc[cut:cut + window]
        try:
            mdl = fit_lgbm(train[FEATURE_COLS], train["y"])
            yhat = mdl.predict(test[FEATURE_COLS])
        except Exception:
            continue
        preds.extend(yhat.tolist())
        trues.extend(test["y"].values.tolist())

    # Final fit on all data for inference.
    final = fit_lgbm(dff[FEATURE_COLS], dff["y"]) if len(dff) >= 60 else None
    return preds, trues, final


# ---------- Orchestration ----------
def next_model_version(db: Session) -> str:
    latest = db.exec(
        select(ModelRun).order_by(ModelRun.id.desc())
    ).first()
    if not latest:
        return "v1"
    try:
        n = int(latest.model_version.lstrip("v"))
        return f"v{n + 1}"
    except ValueError:
        return f"v{(latest.id or 0) + 1}"


def active_version(db: Session, algorithm: str) -> str | None:
    row = db.exec(
        select(ModelRun)
        .where(ModelRun.algorithm == algorithm)
        .where(ModelRun.is_active == True)  # noqa: E712
        .order_by(ModelRun.id.desc())
    ).first()
    return row.model_version if row else None


def train_branch(db: Session, branch: str, top_n: int, version: str, models_root: Path) -> dict:
    skus = top_n_skus(db, branch, n=top_n)
    if not skus:
        print(f"  [{branch}] no SKUs in sales_history")
        return {"prophet": [], "lgbm": []}

    all_prophet, all_lgbm, all_naive = [], [], []
    actuals_used = 0
    out_dir = models_root / version / branch.replace(" ", "_")
    out_dir.mkdir(parents=True, exist_ok=True)

    for sku, item_name in skus:
        print(f"  [{branch}] {sku} {item_name[:40]}...", end=" ", flush=True)
        df = build_training_frame(db, branch, sku)
        if len(df) < 60:
            print(f"skip (only {len(df)} rows)")
            continue

        # Naive — walk-forward on same windows as Prophet for fair comparison
        dff_naive = df.dropna(subset=["lag_7", "y"]).reset_index(drop=True)
        n_win_naive = 6
        win_naive = 7
        if len(dff_naive) < win_naive * (n_win_naive + 2):
            n_win_naive = max(1, (len(dff_naive) - win_naive * 2) // win_naive)
        naive_preds_wf, naive_trues_wf = [], []
        for k in range(n_win_naive, 0, -1):
            cut = len(dff_naive) - k * win_naive
            if cut < 60:
                continue
            test_slice = dff_naive.iloc[cut:cut + win_naive]
            naive_preds_wf.extend(test_slice["lag_7"].values.tolist())
            naive_trues_wf.extend(test_slice["y"].values.tolist())
        naive_preds = naive_preds_wf
        naive_trues = naive_trues_wf

        # Prophet
        p_preds, p_trues = prophet_walk_forward(df)

        # LightGBM
        l_preds, l_trues, l_final = lgbm_walk_forward(df)

        all_prophet.append((p_trues, p_preds))
        all_lgbm.append((l_trues, l_preds))
        if naive_trues:
            all_naive.append((naive_trues, naive_preds))

        # Persist final-fit models for inference
        bundle = {
            "branch": branch, "sku": sku, "item_name": item_name,
            "version": version,
            "lgbm_model": l_final,
            "feature_cols": FEATURE_COLS,
            "trained_at": datetime.utcnow().isoformat(),
            "history_ds": df["ds"].tolist(),
            "history_y": df["y"].tolist(),
        }
        joblib.dump(bundle, out_dir / f"{_safe(sku)}.joblib")
        actuals_used += int((df["y"] > 0).sum())

        print(f"prophet MAE={metrics(p_trues, p_preds)['mae']:.2f} | lgbm MAE={metrics(l_trues, l_preds)['mae']:.2f}")

    return {
        "prophet": all_prophet,
        "lgbm": all_lgbm,
        "naive": all_naive,
        "actuals_used": actuals_used,
    }


def _safe(s: str) -> str:
    return "".join(c if c.isalnum() or c in "._-" else "_" for c in s)


def aggregate_metrics(pairs: list[tuple[list, list]]) -> dict:
    trues, preds = [], []
    for t, p in pairs:
        trues.extend(t); preds.extend(p)
    if not trues:
        return {"mae": 0.0, "rmse": 0.0, "mape": 0.0, "acc_20pct": 0.0}
    m = metrics(np.array(trues), np.array(preds))
    # Coerce NaN → 0 so we can persist the row even if some windows had no signal.
    return {k: (0.0 if (v != v) else v) for k, v in m.items()}


def record_run(db: Session, *, version: str, algorithm: str, m: dict, baseline_mae: float,
               actuals_used: int, training_window_start: date | None,
               training_window_end: date | None, promote: bool) -> ModelRun:
    run = ModelRun(
        model_version=version,
        algorithm=algorithm,
        trained_at=datetime.utcnow(),
        training_window_start=training_window_start,
        training_window_end=training_window_end,
        mae=m["mae"], rmse=m["rmse"], mape=m["mape"], acc_20pct=m["acc_20pct"],
        beats_baseline=bool(m["mae"] < baseline_mae) if baseline_mae == baseline_mae else False,
        is_active=promote,
        promoted_at=datetime.utcnow() if promote else None,
        trained_on_actuals_count=actuals_used,
        notes="",
    )
    if promote:
        # Demote previous active for this algorithm.
        prev = db.exec(
            select(ModelRun)
            .where(ModelRun.algorithm == algorithm)
            .where(ModelRun.is_active == True)  # noqa: E712
        ).all()
        for r in prev:
            r.is_active = False
            db.add(r)
    db.add(run)
    db.commit()
    db.refresh(run)
    return run


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--branch", default="all", help="'all' or one branch name")
    ap.add_argument("--top-n", type=int, default=5)
    ap.add_argument("--force-promote", action="store_true", help="Promote regardless of MAE comparison")
    args = ap.parse_args()

    init_db()
    branches = settings.branches if args.branch == "all" else [args.branch]
    print(f"Training {branches} top-{args.top_n} SKUs each")

    with Session(engine) as db:
        version = next_model_version(db)
        print(f"Model version: {version}")
        models_root = settings.models_dir

        agg = {"prophet": [], "lgbm": [], "naive": []}
        actuals_used = 0
        for b in branches:
            r = train_branch(db, b, args.top_n, version, models_root)
            agg["prophet"].extend(r.get("prophet", []))
            agg["lgbm"].extend(r.get("lgbm", []))
            agg["naive"].extend(r.get("naive", []))
            actuals_used += r.get("actuals_used", 0)

        naive_m = aggregate_metrics(agg["naive"])
        prophet_m = aggregate_metrics(agg["prophet"])
        lgbm_m = aggregate_metrics(agg["lgbm"])

        print("\nAggregate metrics:")
        for name, m in [("naive", naive_m), ("prophet", prophet_m), ("lgbm", lgbm_m)]:
            print(f"  {name:8s}  MAE={m['mae']:.2f}  RMSE={m['rmse']:.2f}  MAPE={m['mape']*100:.1f}%  Acc20={m['acc_20pct']*100:.1f}%")

        # Decide promotion: new version is active only if MAE <= current active * 1.0
        def should_promote(algo: str, new_mae: float) -> bool:
            if args.force_promote:
                return True
            cur_v = active_version(db, algo)
            if not cur_v:
                return True
            cur = db.exec(
                select(ModelRun)
                .where(ModelRun.algorithm == algo)
                .where(ModelRun.model_version == cur_v)
            ).first()
            return cur is None or new_mae <= cur.mae

        record_run(db, version=version, algorithm="naive", m=naive_m,
                   baseline_mae=naive_m["mae"], actuals_used=actuals_used,
                   training_window_start=None, training_window_end=None,
                   promote=False)
        record_run(db, version=version, algorithm="prophet", m=prophet_m,
                   baseline_mae=naive_m["mae"], actuals_used=actuals_used,
                   training_window_start=None, training_window_end=None,
                   promote=should_promote("prophet", prophet_m["mae"]))
        record_run(db, version=version, algorithm="lightgbm", m=lgbm_m,
                   baseline_mae=naive_m["mae"], actuals_used=actuals_used,
                   training_window_start=None, training_window_end=None,
                   promote=should_promote("lightgbm", lgbm_m["mae"]))

        # Write a manifest for the version dir.
        manifest = {
            "version": version,
            "trained_at": datetime.utcnow().isoformat(),
            "branches": branches,
            "top_n": args.top_n,
            "metrics": {
                "naive": naive_m, "prophet": prophet_m, "lightgbm": lgbm_m,
            },
        }
        (models_root / version).mkdir(parents=True, exist_ok=True)
        with open(models_root / version / "manifest.json", "w") as f:
            json.dump(manifest, f, indent=2, default=str)

    print(f"\nDone. Wrote models to {models_root / version}")


if __name__ == "__main__":
    main()
