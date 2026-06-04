"""Streamlit conversion of the Panem FastAPI/Jinja dashboard.

All code in this file maps existing pages/routes/JS into Streamlit equivalents.
The original project files are intentionally left untouched.
"""
from __future__ import annotations

import sqlite3
import subprocess
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import pytz
import streamlit as st


ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "panem.db"
CSV_DIR = ROOT / "CompleteData"
TZ = pytz.timezone("America/Monterrey")

BRANCHES = [
    "Punto Valle",
    "Hotel Kavia",
    "Plaza QIN",
    "Hospital Zambrano",
    "La Carreta",
    "Plaza Nativa",
    "Credi Club",
]
BRANCH_PALETTE = ["#f0a04b", "#9bcf6b", "#ff9eb5", "#7ecfff", "#c49bff", "#ffdc6b", "#ff8c42"]
MONTH_LABELS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
DOW_ORDER = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
PLAN_LOCK_HOUR = 16
ACTUALS_OPEN_HOUR = 21
DRIFT_MAE_TOLERANCE = 1.25


def now() -> datetime:
    return datetime.now(TZ)


def today() -> date:
    return now().date()


def default_bake_date() -> date:
    n = now()
    return n.date() + timedelta(days=1 if n.hour < PLAN_LOCK_HOUR else 2)


def plan_mode_for(bake_date: date) -> str:
    n = now()
    today_ = n.date()
    if bake_date > today_:
        if bake_date == today_ + timedelta(days=1) and n.hour >= PLAN_LOCK_HOUR:
            return "locked"
        return "plan"
    if bake_date == today_:
        return "actuals" if n.hour >= ACTUALS_OPEN_HOUR else "locked"
    return "actuals"


def conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def read_sql(query: str, params: Iterable | dict = ()) -> pd.DataFrame:
    with conn() as c:
        return pd.read_sql_query(query, c, params=params)


def exec_sql(query: str, params: Iterable | dict = ()) -> None:
    with conn() as c:
        c.execute(query, params)
        c.commit()


def scalar(query: str, params: Iterable | dict = ()):
    with conn() as c:
        row = c.execute(query, params).fetchone()
        return row[0] if row else None


def fmt_int(value) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "-"
    return f"{int(round(float(value))):,}"


def fmt_money(value) -> str:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return "-"
    return f"${int(round(float(value))):,}"


def fmt_date(value) -> str:
    if not value:
        return "-"
    d = pd.to_datetime(value).date()
    return d.strftime("%a, %b %-d") if sys.platform != "win32" else d.strftime("%a, %b %#d")


def date_range(start: date, end: date) -> list[date]:
    days = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    return days


def style_plot(fig: go.Figure, height: int = 360) -> go.Figure:
    fig.update_layout(
        height=height,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(5,3,0,0.35)",
        font={"color": "#f7f4ee", "size": 12},
        margin={"l": 30, "r": 20, "t": 25, "b": 45},
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02, "xanchor": "right", "x": 1},
        # Avoid Plotly's unified hover because it shows all bars/traces
        # that share the same x-axis value. Operators need the exact bar
        # under the cursor, especially in Top Products and Weekday Demand.
        hovermode="closest",
        hoverlabel={
            "bgcolor": "rgba(20,13,6,0.96)",
            "bordercolor": "rgba(240,160,75,0.75)",
            "font": {"color": "#f7f4ee"},
        },
    )
    fig.update_xaxes(gridcolor="rgba(255,255,255,0.08)", zerolinecolor="rgba(255,255,255,0.08)")
    fig.update_yaxes(gridcolor="rgba(255,255,255,0.08)", zerolinecolor="rgba(255,255,255,0.08)", rangemode="tozero")
    return fig


def bar_fig(labels, values, *, horizontal=False, color="#f0a04b", name="", value_label="Units") -> go.Figure:
    fig = go.Figure()
    if horizontal:
        fig.add_bar(
            y=labels,
            x=values,
            orientation="h",
            marker_color=color,
            name=name or value_label,
            hovertemplate=f"<b>%{{y}}</b><br>{value_label}: <b>%{{x:,.0f}}</b><extra></extra>",
        )
        fig.update_layout(yaxis={"autorange": "reversed"})
    else:
        fig.add_bar(
            x=labels,
            y=values,
            marker_color=color,
            name=name or value_label,
            hovertemplate=f"<b>%{{x}}</b><br>{value_label}: <b>%{{y:,.0f}}</b><extra></extra>",
        )
    return style_plot(fig)


def line_fig(labels, series: list[dict], height: int = 360) -> go.Figure:
    fig = go.Figure()
    for s in series:
        fig.add_trace(go.Scatter(
            x=labels,
            y=s["data"],
            mode="lines",
            name=s.get("name", ""),
            line={"color": s.get("color", "#f0a04b"), "dash": s.get("dash", "solid"), "width": 2.5},
            fill=s.get("fill"),
            fillcolor=s.get("fillcolor"),
            connectgaps=s.get("connectgaps", False),
        ))
    return style_plot(fig, height)


def apply_css() -> None:
    """Centralized Streamlit theme for the Panem prototype.

    This pass only changes the shell/layout styling. Forecasting, model, API,
    database, and data pipeline logic are intentionally left untouched.
    """
    st.markdown(
        """
        <style>
        :root {
          --accent:#f0a04b;
          --accent-strong:#ffad55;
          --accent2:#9bcf6b;
          --warn:#ff6b5a;
          --ink:#f7f4ee;
          --muted:rgba(247,244,238,.68);
          --muted2:rgba(247,244,238,.48);
          --panel:rgba(255,247,235,.095);
          --panel2:rgba(255,247,235,.155);
          --line:rgba(255,255,255,.16);
          --bg0:#050300;
          --bg1:#0a0704;
          --bg2:#140d06;
        }

        .stApp {
          color: var(--ink);
          background:
            radial-gradient(at 18% 8%, rgba(243,217,181,.16), transparent 38%),
            radial-gradient(at 86% 92%, rgba(201,138,74,.13), transparent 50%),
            linear-gradient(135deg, var(--bg0) 0%, var(--bg1) 58%, var(--bg2) 100%);
        }

        /* Keep the prototype dashboard-first: no sidebar navigation. */
        [data-testid="stSidebar"], [data-testid="collapsedControl"] {
          display: none !important;
        }
        .block-container {
          max-width: 1440px;
          padding-top: 1.1rem;
          padding-bottom: 3rem;
        }

        h1 {
          color:#fff;
          letter-spacing:-.45px;
          margin-bottom:.15rem;
        }
        h2, h3 {
          color:var(--accent);
          text-transform:uppercase;
          letter-spacing:1.15px;
        }
        p, label, span, div { color: inherit; }
        div[data-testid="stCaptionContainer"] { color: var(--muted); }

        .panem-navbar {
          position: sticky;
          top: 0;
          z-index: 999;
          display:flex;
          align-items:center;
          justify-content:space-between;
          gap:18px;
          margin:-.35rem 0 .75rem 0;
          padding:13px 16px;
          border:1px solid rgba(255,255,255,.18);
          border-radius:20px;
          background:linear-gradient(135deg, rgba(18,11,5,.94), rgba(7,4,1,.90));
          box-shadow:0 18px 44px rgba(0,0,0,.35), inset 0 1px 0 rgba(255,255,255,.14);
          backdrop-filter: blur(14px);
        }
        .panem-brand {
          display:flex;
          align-items:center;
          gap:11px;
          min-width:190px;
          color:#fff;
          font-weight:900;
          letter-spacing:2.4px;
          font-size:18px;
        }
        .panem-mark {
          width:34px;
          height:34px;
          border-radius:12px;
          display:inline-flex;
          align-items:center;
          justify-content:center;
          background:linear-gradient(135deg, var(--accent), #c96a00);
          color:#1a0d00;
          box-shadow:0 8px 22px rgba(240,160,75,.28);
          font-weight:900;
        }
        .panem-nav-status {
          display:flex;
          align-items:center;
          justify-content:flex-end;
          gap:10px;
          flex-wrap:wrap;
          font-size:12px;
          color:var(--muted);
        }
        .nav-pill, .modepill {
          display:inline-flex;
          align-items:center;
          justify-content:center;
          padding:7px 13px;
          border-radius:999px;
          border:1px solid rgba(255,255,255,.18);
          font-size:11px;
          text-transform:uppercase;
          letter-spacing:1.25px;
          font-weight:800;
          color:var(--accent);
          background:rgba(240,160,75,.14);
          white-space:nowrap;
        }
        .nav-pill.neutral {
          color:var(--ink);
          background:rgba(255,255,255,.07);
        }
        .nav-pill.logout {
          color:rgba(247,244,238,.72);
          background:rgba(255,255,255,.05);
        }
        .nav-help {
          margin:-.15rem 0 .35rem 0;
          color:var(--muted2);
          font-size:12px;
        }

        .control-strip {
          margin:.45rem 0 1rem 0;
          padding:14px 16px;
          border:1px solid rgba(255,255,255,.16);
          border-radius:20px;
          background:linear-gradient(135deg, rgba(255,247,235,.10), rgba(255,247,235,.055));
          box-shadow:0 12px 34px rgba(0,0,0,.22), inset 0 1px 0 rgba(255,255,255,.14);
        }
        .control-strip-title {
          color:var(--muted);
          font-size:11px;
          letter-spacing:1.25px;
          text-transform:uppercase;
          font-weight:800;
          margin-bottom:8px;
        }

        div[data-testid="stMetric"], .glass-card {
          background: var(--panel);
          border: 1px solid rgba(255,255,255,.18);
          border-radius: 18px;
          padding: 16px 18px;
          box-shadow: 0 8px 32px rgba(20,12,4,.25), inset 0 1px 0 rgba(255,255,255,.22);
        }
        div[data-testid="stMetricValue"] { color:#fff; }
        div[data-testid="stMetricLabel"] { color:var(--muted); }
        .small-muted { color:var(--muted); font-size:12px; }

        .stDataFrame, div[data-testid="stDataFrame"] {
          border: 1px solid rgba(255,255,255,.12);
          border-radius: 14px;
          overflow:hidden;
        }

        /* Streamlit controls: keep the native behavior, style the shell. */
        .stSelectbox, .stDateInput, .stSlider, .stRadio, .stNumberInput, .stTextArea {
          color:var(--ink);
        }
        div[data-baseweb="select"] > div,
        div[data-baseweb="input"] > div,
        textarea {
          background:rgba(255,255,255,.08) !important;
          border-color:rgba(255,255,255,.18) !important;
          border-radius:14px !important;
          color:var(--ink) !important;
        }
        .stButton > button,
        div[data-testid="stFormSubmitButton"] button {
          width:100%;
          border-radius:999px;
          border:1px solid rgba(255,255,255,.18);
          background:rgba(255,255,255,.07);
          color:var(--ink);
          font-weight:800;
          letter-spacing:.25px;
          transition:all .15s ease;
        }
        .stButton > button:hover,
        div[data-testid="stFormSubmitButton"] button:hover {
          border-color:rgba(240,160,75,.72);
          color:#fff;
          transform:translateY(-1px);
          box-shadow:0 10px 24px rgba(240,160,75,.16);
        }
        .stButton > button[kind="primary"],
        div[data-testid="stFormSubmitButton"] button[kind="primary"] {
          color:#1b0e02;
          background:linear-gradient(135deg, var(--accent), #c96a00);
          border-color:rgba(240,160,75,.92);
          box-shadow:0 10px 24px rgba(240,160,75,.22);
        }
        .stButton > button:disabled,
        div[data-testid="stFormSubmitButton"] button:disabled {
          opacity:.45;
          transform:none;
          box-shadow:none;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

# Original route: /api/forecast, UI: templates/plan.html + static/js/plan.js
def get_forecast(branch: str, bake_date: date) -> dict:
    bd = bake_date
    exact = scalar(
        "select max(bake_date) from forecast where branch = ? and bake_date <= ?",
        (branch, bd.isoformat()),
    )
    if not exact:
        exact = scalar("select min(bake_date) from forecast where branch = ?", (branch,))
    if not exact:
        return {
            "rows": pd.DataFrame(),
            "kpis": {"units_to_bake": 0, "projected_revenue": 0, "expected_waste": 0, "stockout_risk_skus": 0, "waste_rate": None},
            "week_start": bd,
            "week_end": bd,
            "mode": plan_mode_for(bd),
            "is_locked": False,
        }

    week_start = pd.to_datetime(exact).date()
    week_end = week_start + timedelta(days=6)
    data_end_raw = scalar("select max(sale_date) from sales_history where branch = ?", (branch,))
    data_end = pd.to_datetime(data_end_raw).date() if data_end_raw else week_start - timedelta(days=1)

    fc = read_sql(
        """
        select * from forecast
        where branch = ? and bake_date >= ? and bake_date <= ?
        """,
        (branch, week_start.isoformat(), week_end.isoformat()),
    )
    if fc.empty:
        rows = pd.DataFrame()
    else:
        ov = read_sql(
            f"select * from override where forecast_id in ({','.join(['?'] * len(fc))})",
            tuple(fc["id"].tolist()),
        )
        ov_map = ov.set_index("forecast_id").to_dict("index") if not ov.empty else {}
        out = []
        for sku, grp in fc.groupby("sku"):
            grp = grp.sort_values("bake_date")
            last_week_start = data_end - timedelta(days=6)
            last_week_total = scalar(
                """
                select sum(qty_sold) from sales_history
                where branch = ? and sku = ? and sale_date >= ? and sale_date <= ?
                """,
                (branch, sku, last_week_start.isoformat(), data_end.isoformat()),
            )
            overrides = [ov_map[int(fid)] for fid in grp["id"].tolist() if int(fid) in ov_map]
            total_override = round(sum(float(o["override_units"]) for o in overrides), 0) if overrides else None
            daily = []
            for _, f in grp.iterrows():
                ov_row = ov_map.get(int(f["id"]))
                daily.append({
                    "date": f["bake_date"],
                    "pred": round(float(f["predicted_units"]), 0),
                    "lo": round(float(f["confidence_low"]), 0),
                    "hi": round(float(f["confidence_high"]), 0),
                    "forecast_id": int(f["id"]),
                    "override": round(float(ov_row["override_units"]), 0) if ov_row else None,
                })
            out.append({
                "id": int(grp.iloc[0]["id"]),
                "branch": branch,
                "sku": sku,
                "item_name": grp.iloc[0]["item_name"],
                "week_start": week_start,
                "week_end": week_end,
                "next7_pred": round(float(grp["predicted_units"].sum()), 0),
                "next7_lo": round(float(grp["confidence_low"].sum()), 0),
                "next7_hi": round(float(grp["confidence_high"].sum()), 0),
                "last_week_total": round(float(last_week_total), 0) if last_week_total else None,
                "model_version": grp.iloc[0]["model_version"],
                "override": total_override,
                "override_reason": overrides[0]["reason"] if overrides else None,
                "daily": daily,
            })
        rows = pd.DataFrame(out).sort_values("next7_pred", ascending=False)

    total_units = 0 if rows.empty else rows.apply(lambda r: r["override"] if pd.notna(r["override"]) else r["next7_pred"], axis=1).sum()
    projected_revenue = 0.0
    expected_waste = 0
    stockout_risk = 0
    if not rows.empty:
        for _, r in rows.iterrows():
            units = r["override"] if pd.notna(r["override"]) else r["next7_pred"]
            avg_price = scalar("select avg(unit_price) from sales_history where branch = ? and sku = ?", (branch, r["sku"])) or 0
            projected_revenue += float(units) * float(avg_price)
            expected_waste += max(0, float(r["next7_pred"]) - float(r["next7_lo"]))
            stockout_risk += int((r["last_week_total"] or 0) > r["next7_lo"])

    actuals = read_sql("select sum(qty_wasted) as wasted, sum(qty_sold) as sold from actual where branch = ?", (branch,))
    total_wasted = float(actuals.iloc[0]["wasted"] or 0) if not actuals.empty else 0
    total_sold = float(actuals.iloc[0]["sold"] or 0) if not actuals.empty else 0
    waste_rate = round(total_wasted / (total_sold + total_wasted), 3) if total_sold + total_wasted > 0 else None
    is_locked = scalar("select id from plan_lock where branch = ? and bake_date = ?", (branch, bd.isoformat())) is not None

    return {
        "rows": rows,
        "kpis": {
            "units_to_bake": round(total_units),
            "projected_revenue": round(projected_revenue, 2),
            "expected_waste": round(expected_waste),
            "stockout_risk_skus": stockout_risk,
            "waste_rate": waste_rate,
        },
        "week_start": week_start,
        "week_end": week_end,
        "mode": "locked" if is_locked else plan_mode_for(bd),
        "is_locked": is_locked,
    }


def branches_summary(bake_date: date) -> pd.DataFrame:
    return read_sql(
        """
        select branch, round(sum(predicted_units), 0) as units
        from forecast
        where bake_date = ?
        group by branch
        """,
        (bake_date.isoformat(),),
    )


def forecast_vs_actual(branch: str, days: int = 7) -> pd.DataFrame:
    end = today()
    start = end - timedelta(days=days - 1)
    f = read_sql(
        """
        select bake_date as d, sum(predicted_units) as predicted
        from forecast where branch = ? and bake_date >= ? and bake_date <= ?
        group by bake_date
        """,
        (branch, start.isoformat(), end.isoformat()),
    )
    a = read_sql(
        """
        select bake_date as d, sum(qty_sold) as actual
        from actual where branch = ? and bake_date >= ? and bake_date <= ?
        group by bake_date
        """,
        (branch, start.isoformat(), end.isoformat()),
    )
    frame = pd.DataFrame({"d": [d.isoformat() for d in date_range(start, end)]})
    frame = frame.merge(f, how="left", on="d").merge(a, how="left", on="d").fillna(0)
    return frame


def upsert_override(forecast_id: int, units: float, reason: str, note: str, user_id: int) -> None:
    existing = scalar("select id from override where forecast_id = ?", (forecast_id,))
    if existing:
        exec_sql(
            """
            update override
            set override_units = ?, reason = ?, note = ?, user_id = ?, created_at = ?
            where forecast_id = ?
            """,
            (units, reason, note, user_id, datetime.utcnow().isoformat(), forecast_id),
        )
    else:
        exec_sql(
            """
            insert into override (forecast_id, user_id, override_units, reason, note, created_at)
            values (?, ?, ?, ?, ?, ?)
            """,
            (forecast_id, user_id, units, reason, note, datetime.utcnow().isoformat()),
        )


def delete_override(forecast_id: int) -> None:
    exec_sql("delete from override where forecast_id = ?", (forecast_id,))


def upsert_actual(branch: str, sku: str, bake_date: date, sold: float, wasted: float, user_id: int) -> None:
    existing = scalar("select id from actual where branch = ? and sku = ? and bake_date = ?", (branch, sku, bake_date.isoformat()))
    if existing:
        exec_sql(
            """
            update actual
            set qty_sold = ?, qty_wasted = ?, recorded_by = ?, recorded_at = ?
            where id = ?
            """,
            (sold, wasted, user_id, datetime.utcnow().isoformat(), existing),
        )
    else:
        exec_sql(
            """
            insert into actual (branch, sku, bake_date, qty_sold, qty_wasted, recorded_by, recorded_at)
            values (?, ?, ?, ?, ?, ?, ?)
            """,
            (branch, sku, bake_date.isoformat(), sold, wasted, user_id, datetime.utcnow().isoformat()),
        )


def lock_plan(branch: str, bake_date: date, user_id: int) -> None:
    if scalar("select id from plan_lock where branch = ? and bake_date = ?", (branch, bake_date.isoformat())):
        return
    exec_sql(
        "insert into plan_lock (branch, bake_date, locked_at, locked_by) values (?, ?, ?, ?)",
        (branch, bake_date.isoformat(), datetime.utcnow().isoformat(), user_id),
    )


def allowed_pages_for_role(role: str) -> list[str]:
    """Role-based navigation rules for the Streamlit shell.

    Product is intentionally allowed as a hidden route for both roles because
    the original dashboard opened Product from Recommended Bake instead of
    exposing it as a primary navbar tab.
    """
    role_key = role.lower()
    if role_key == "analyst":
        return ["Bake Plan", "Product", "Analytics", "Model", "Feedback"]
    return ["Bake Plan", "Product", "Analytics"]


def init_session_state() -> None:
    """Initialize UI state without touching business/data logic."""
    st.session_state.setdefault("selected_role", "operator")
    st.session_state.setdefault("selected_page", "Bake Plan")
    st.session_state.setdefault("show_actuals_editor", False)
    st.session_state.setdefault("product_branch", BRANCHES[0])
    st.session_state.setdefault("product_sku", None)

    allowed = allowed_pages_for_role(st.session_state.selected_role)
    if st.session_state.selected_page not in allowed:
        st.session_state.selected_page = "Bake Plan"


def active_user() -> dict:
    """Resolve a database user for the selected role.

    The original Streamlit prototype selected a specific DB user from the sidebar.
    The reviewed dashboard flow uses role buttons instead. To preserve all write
    logic that needs user_id, this function maps the selected role to the first
    matching user in the existing `user` table.
    """
    role_key = st.session_state.get("selected_role", "operator").lower()
    df = read_sql(
        "select id, username, role from user where lower(role) = ? order by username",
        (role_key,),
    )
    if df.empty:
        fallback = read_sql("select id, username, role from user order by role, username limit 1")
        if fallback.empty:
            return {"id": 1, "username": role_key, "role": role_key}
        row = fallback.iloc[0]
    else:
        row = df.iloc[0]
    return {"id": int(row["id"]), "username": row["username"], "role": row["role"]}


def set_role(role: str) -> None:
    role_key = role.lower()
    st.session_state.selected_role = role_key
    if st.session_state.selected_page not in allowed_pages_for_role(role_key):
        st.session_state.selected_page = "Bake Plan"


def render_top_navbar(user: dict) -> None:
    """Top dashboard shell replacing sidebar navigation."""
    role_label = st.session_state.selected_role.title()
    active_page = st.session_state.selected_page
    allowed_pages = allowed_pages_for_role(st.session_state.selected_role)

    st.markdown(
        f"""
        <div class="panem-navbar">
          <div class="panem-brand"><span class="panem-mark">P</span><span>PANEM</span></div>
          <div class="panem-nav-status">
            <span class="nav-pill">{active_page}</span>
            <span class="nav-pill neutral">{user['username']} · {role_label}</span>
            <span class="nav-pill neutral">{now():%a, %b %d · %H:%M}</span>
            <span class="nav-pill logout">Logout</span>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("<div class='nav-help'>Role and page navigation</div>", unsafe_allow_html=True)
    role_cols = st.columns([0.9, 0.9, 0.25, 1, 1, 1, 1, 1.8])
    with role_cols[0]:
        if st.button("Operator", type="primary" if st.session_state.selected_role == "operator" else "secondary", key="nav_role_operator"):
            set_role("operator")
            st.rerun()
    with role_cols[1]:
        if st.button("Analyst", type="primary" if st.session_state.selected_role == "analyst" else "secondary", key="nav_role_analyst"):
            set_role("analyst")
            st.rerun()

    for i, page_name in enumerate(["Bake Plan", "Analytics", "Model", "Feedback"], start=3):
        with role_cols[i]:
            disabled = page_name not in allowed_pages
            if st.button(page_name, type="primary" if active_page == page_name else "secondary", disabled=disabled, key=f"nav_page_{page_name}"):
                st.session_state.selected_page = page_name
                st.rerun()


def dataframe_selected_rows(event) -> list[int]:
    """Return selected row positions from Streamlit dataframe events safely."""
    if event is None:
        return []
    try:
        if isinstance(event, dict):
            return event.get("selection", {}).get("rows", []) or []
        selection = getattr(event, "selection", None)
        if selection is None:
            return []
        if isinstance(selection, dict):
            return selection.get("rows", []) or []
        return getattr(selection, "rows", []) or []
    except Exception:
        return []


def open_product_detail(branch: str, sku: str) -> None:
    """Navigate to the hidden Product route using the selected product context."""
    st.session_state.product_branch = branch
    st.session_state.product_sku = sku
    st.session_state.selected_page = "Product"
    st.rerun()


def render_bake_plan(user: dict) -> None:
    # Original page: templates/plan.html. Original JS/API: static/js/plan.js + /api/forecast.
    # UI-only refactor: controls/actions moved to top; business logic is preserved.
    st.title("Weekly bake plan")
    st.caption("Operator workflow for weekly production recommendations.")

    st.markdown("<div class='control-strip-title'>Bake plan controls</div>", unsafe_allow_html=True)
    c1, c2, c3, c4, c5, c6, c7 = st.columns([1.35, 1.15, 1.35, .9, 1.0, 1.18, 1.55])
    with c1:
        branch = st.selectbox("Branch", BRANCHES, index=0, key="bake_branch")
    with c2:
        selected_date = st.date_input("Bake date", default_bake_date(), key="bake_date")
    with c3:
        min_conf = st.slider("Min confidence", 0, 100, 0, help="Lower bound confidence threshold (%)", key="bake_min_conf")

    data = get_forecast(branch, selected_date)
    rows = data["rows"]

    with c4:
        st.markdown("<div style='height:1.72rem'></div>", unsafe_allow_html=True)
        st.markdown(f"<span class='modepill'>{data['mode']}</span>", unsafe_allow_html=True)
    with c5:
        st.markdown("<div style='height:1.72rem'></div>", unsafe_allow_html=True)
        if st.button("Log Actuals", key="top_log_actuals"):
            st.session_state.show_actuals_editor = not st.session_state.get("show_actuals_editor", False)
    with c6:
        st.markdown("<div style='height:1.72rem'></div>", unsafe_allow_html=True)
        if st.button("Generate forecast", help="Runs the same batch.forecast module used by the FastAPI app.", key="top_generate_forecast"):
            run_forecast_generation()
    with c7:
        st.markdown("<div style='height:1.72rem'></div>", unsafe_allow_html=True)
        if st.button("Lock plan & send to oven", disabled=data["mode"] != "plan" or data["is_locked"], key="top_lock_plan"):
            lock_plan(branch, selected_date, user["id"])
            st.success("Plan locked.")
            st.rerun()

    st.caption(f"{branch} · {fmt_date(data['week_start'])} - {fmt_date(data['week_end'])}")

    if data["is_locked"]:
        st.success("Plan locked. Bake order has been sent to the oven.")
    elif data["mode"] == "locked":
        st.info(f"Plan window closed. Locks daily at {PLAN_LOCK_HOUR}:00.")
    elif data["mode"] == "actuals":
        st.info("End-of-day actuals are open. Record what really sold to feed the next retrain.")

    k1, k2, k3, k4, k5 = st.columns(5)
    k1.metric("Units to bake", fmt_int(data["kpis"]["units_to_bake"]), help="Across top-5 SKUs")
    k2.metric("Projected revenue", fmt_money(data["kpis"]["projected_revenue"]), help="At avg historical price")
    k3.metric("Expected waste", fmt_int(data["kpis"]["expected_waste"]), help="Units above lower CI")
    k4.metric("Stock-out risk SKUs", fmt_int(data["kpis"]["stockout_risk_skus"]), help="Last week > lower CI")
    k5.metric("Recorded waste rate", "-" if data["kpis"]["waste_rate"] is None else f"{data['kpis']['waste_rate'] * 100:.1f}%")

    left, right = st.columns([2, 1])
    with left:
        st.subheader("Recommended bake")
        if rows.empty:
            st.warning("No forecasts for this branch/date. Run forecast generation from the top controls.")
        else:
            display = rows.copy()
            display["certainty_pct"] = display.apply(
                lambda r: max(0, 100 * (1 - max(0, r["next7_pred"] - r["next7_lo"]) / (r["next7_pred"] or 1))),
                axis=1,
            )
            display = display[display["certainty_pct"] >= min_conf].copy()
            display["recommended"] = display.apply(lambda r: r["override"] if pd.notna(r["override"]) else r["next7_pred"], axis=1)
            display["CI 80%"] = display.apply(lambda r: f"{fmt_int(r['next7_lo'])}-{fmt_int(r['next7_hi'])}", axis=1)
            display["stockout_risk"] = display.apply(lambda r: bool((r["last_week_total"] or 0) > r["next7_lo"]), axis=1)
            recommended_view = display[["sku", "item_name", "last_week_total", "recommended", "next7_pred", "CI 80%", "override_reason", "stockout_risk"]].copy()
            st.caption("Select one product row to open its Product detail view, matching the original dashboard flow.")
            try:
                table_event = st.dataframe(
                    recommended_view,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "sku": "SKU",
                        "item_name": "Item",
                        "last_week_total": "Last 7d sold",
                        "recommended": "Next 7d pred.",
                        "next7_pred": "Model pred.",
                        "override_reason": "Reason",
                        "stockout_risk": "Risk",
                    },
                    on_select="rerun",
                    selection_mode="single-row",
                    key="recommended_bake_table",
                )
                selected_rows = dataframe_selected_rows(table_event)
                if selected_rows:
                    selected_sku = str(recommended_view.iloc[selected_rows[0]]["sku"])
                    open_product_detail(branch, selected_sku)
            except TypeError:
                # Compatibility fallback for older Streamlit versions without dataframe row selection.
                st.dataframe(
                    recommended_view,
                    use_container_width=True,
                    hide_index=True,
                    column_config={
                        "sku": "SKU",
                        "item_name": "Item",
                        "last_week_total": "Last 7d sold",
                        "recommended": "Next 7d pred.",
                        "next7_pred": "Model pred.",
                        "override_reason": "Reason",
                        "stockout_risk": "Risk",
                    },
                )
                detail_sku = st.selectbox(
                    "Open product detail",
                    recommended_view["sku"].tolist(),
                    format_func=lambda s: f"{s} · {recommended_view.loc[recommended_view['sku'] == s, 'item_name'].iloc[0]}",
                    key="product_detail_fallback_select",
                )
                if st.button("Open Product detail", key="open_product_detail_fallback"):
                    open_product_detail(branch, str(detail_sku))

            st.markdown("#### Override prediction")
            ov_row = st.selectbox(
                "SKU to override",
                rows["sku"].tolist(),
                format_func=lambda s: f"{s} · {rows.loc[rows['sku'] == s, 'item_name'].iloc[0]}",
            )
            selected = rows.loc[rows["sku"] == ov_row].iloc[0]
            with st.form("plan_override_form"):
                units = st.number_input("Override units", min_value=0.0, value=float(selected["override"] if pd.notna(selected["override"]) else selected["next7_pred"]), step=1.0)
                reason = st.selectbox("Reason", ["weather", "local_event", "promo", "gut_feel", "other"], index=3)
                note = st.text_area("Note (optional)", height=80)
                a, b = st.columns(2)
                save = a.form_submit_button("Save override", disabled=data["mode"] != "plan")
                clear = b.form_submit_button("Delete override", disabled=data["mode"] != "plan")
            if save:
                upsert_override(int(selected["id"]), units, reason, note, user["id"])
                st.success("Override saved.")
                st.rerun()
            if clear:
                delete_override(int(selected["id"]))
                st.info("Override deleted.")
                st.rerun()

    with right:
        st.subheader("Units by branch")
        summary = branches_summary(data["week_start"])
        if not summary.empty:
            st.plotly_chart(bar_fig(summary["branch"], summary["units"], horizontal=True), use_container_width=True)

        st.subheader("Forecast vs actual · 7 days")
        fva = forecast_vs_actual(branch)
        st.plotly_chart(
            line_fig(fva["d"], [
                {"name": "Predicted", "data": fva["predicted"], "color": "#f0a04b"},
                {"name": "Actual", "data": fva["actual"], "color": "#9bcf6b"},
            ], 300),
            use_container_width=True,
        )

    if st.session_state.get("show_actuals_editor", False):
        st.subheader("Log daily actuals")
        if not rows.empty:
            actual_day = st.selectbox("Day", date_range(data["week_start"], data["week_end"]), format_func=lambda d: f"{d:%a %Y-%m-%d}")
            actual_existing = read_sql(
                "select sku, qty_sold, qty_wasted from actual where branch = ? and bake_date = ?",
                (branch, actual_day.isoformat()),
            )
            existing_map = actual_existing.set_index("sku").to_dict("index") if not actual_existing.empty else {}
            ac_rows = []
            for _, r in rows.iterrows():
                daily = next((d for d in r["daily"] if d["date"] == actual_day.isoformat()), {})
                ex = existing_map.get(r["sku"], {})
                ac_rows.append({
                    "sku": r["sku"],
                    "item": r["item_name"],
                    "predicted": daily.get("pred", 0),
                    "sold": float(ex.get("qty_sold", 0) or 0),
                    "wasted": float(ex.get("qty_wasted", 0) or 0),
                })
            edited = st.data_editor(pd.DataFrame(ac_rows), use_container_width=True, hide_index=True, disabled=["sku", "item", "predicted"])
            if st.button("Save this day", key="save_actuals_day"):
                for r in edited.to_dict("records"):
                    if r["sold"] or r["wasted"]:
                        upsert_actual(branch, r["sku"], actual_day, float(r["sold"]), float(r["wasted"]), user["id"])
                st.success(f"Saved actuals for {actual_day.isoformat()}.")
                st.rerun()
        else:
            st.info("No forecast rows are available for actuals logging.")


# Original route: /api/product/{sku}/deep-dive, UI: templates/product.html + static/js/product.js
def get_product_deep_dive(sku: str, branch: str) -> dict | None:
    data_end_raw = scalar("select max(sale_date) from sales_history where branch = ? and sku = ?", (branch, sku))
    if not data_end_raw:
        return None
    data_end = pd.to_datetime(data_end_raw).date()
    start_90 = data_end - timedelta(days=90)
    hist = read_sql(
        """
        select * from sales_history
        where branch = ? and sku = ? and sale_date >= ?
        order by sale_date
        """,
        (branch, sku, start_90.isoformat()),
    )
    if hist.empty:
        return None
    item_name = hist.iloc[-1]["item_name"]
    next_bake_raw = scalar("select min(bake_date) from forecast where branch = ? and sku = ?", (branch, sku))
    next_bake = pd.to_datetime(next_bake_raw).date() if next_bake_raw else data_end + timedelta(days=1)
    fc_window = read_sql(
        """
        select * from forecast
        where branch = ? and sku = ?
        order by bake_date
        limit 7
        """,
        (branch, sku),
    )
    baseline = scalar(
        "select qty_sold from sales_history where branch = ? and sku = ? and sale_date = ?",
        (branch, sku, (next_bake - timedelta(days=7)).isoformat()),
    )
    hist14 = read_sql(
        """
        select sale_date, qty_sold from sales_history
        where branch = ? and sku = ? and sale_date >= ? and sale_date <= ?
        order by sale_date
        """,
        (branch, sku, (data_end - timedelta(days=13)).isoformat(), data_end.isoformat()),
    )
    hist_map = {pd.to_datetime(r.sale_date).date(): r.qty_sold for r in hist14.itertuples()}
    f_map = {pd.to_datetime(r.bake_date).date(): r for r in fc_window.itertuples()} if not fc_window.empty else {}
    a_map = {}
    if not fc_window.empty:
        actuals = read_sql(
            """
            select * from actual
            where branch = ? and sku = ? and bake_date >= ? and bake_date <= ?
            """,
            (branch, sku, fc_window.iloc[0]["bake_date"], fc_window.iloc[-1]["bake_date"]),
        )
        a_map = {pd.to_datetime(r.bake_date).date(): r for r in actuals.itertuples()}
    days = sorted(set(hist_map) | set(f_map))

    by_dow = {i: [] for i in range(7)}
    for r in hist.itertuples():
        by_dow[pd.to_datetime(r.sale_date).date().weekday()].append(r.qty_sold)

    holidays = read_sql("select * from holiday")
    weather = read_sql("select * from weather")
    holidays_map = {pd.to_datetime(r.date).date(): r for r in holidays.itertuples()}
    weather_map = {pd.to_datetime(r.date).date(): r for r in weather.itertuples()}
    cold, warm, q, nq = [], [], [], []
    for r in hist.itertuples():
        d = pd.to_datetime(r.sale_date).date()
        w = weather_map.get(d)
        if w and w.cold_or_warm_num == -1:
            cold.append(r.qty_sold)
        if w and w.cold_or_warm_num == 1:
            warm.append(r.qty_sold)
        is_q = d in holidays_map and bool(holidays_map[d].is_quincena)
        (q if is_q else nq).append(r.qty_sold)

    peer_rows = read_sql(
        "select branch, predicted_units from forecast where sku = ? and bake_date = ?",
        (sku, next_bake.isoformat()),
    )

    other = read_sql(
        """
        select sku, item_name, sale_date as date, qty_sold as qty
        from sales_history
        where branch = ? and sale_date >= ?
        """,
        (branch, start_90.isoformat()),
    )
    similar = pd.DataFrame()
    if not other.empty:
        pivot = other.pivot_table(index="date", columns="sku", values="qty", aggfunc="sum").fillna(0)
        if sku in pivot.columns and len(pivot) > 5:
            corrs = pivot.corrwith(pivot[sku]).drop(labels=[sku], errors="ignore").dropna().sort_values(ascending=False).head(5)
            name_map = other.drop_duplicates("sku").set_index("sku")["item_name"].to_dict()
            similar = pd.DataFrame([{"sku": s, "item_name": name_map.get(s, ""), "Pearson r": round(float(v), 3)} for s, v in corrs.items()])

    avg_price = scalar("select avg(unit_price) from sales_history where branch = ? and sku = ?", (branch, sku)) or 0
    active = read_sql("select * from modelrun where algorithm = 'prophet' and is_active = 1 order by id desc limit 1")
    rec = {
        "predicted_units": round(float(fc_window["predicted_units"].sum()), 1) if not fc_window.empty else None,
        "ci_low": round(float(fc_window["confidence_low"].sum()), 1) if not fc_window.empty else None,
        "ci_high": round(float(fc_window["confidence_high"].sum()), 1) if not fc_window.empty else None,
        "week_start": fc_window.iloc[0]["bake_date"] if not fc_window.empty else next_bake.isoformat(),
        "week_end": fc_window.iloc[-1]["bake_date"] if not fc_window.empty else next_bake.isoformat(),
        "baseline_lag7": float(baseline) if baseline is not None else None,
        "model_version": fc_window.iloc[0]["model_version"] if not fc_window.empty else (active.iloc[0]["model_version"] if not active.empty else None),
        "last_retrain": active.iloc[0]["trained_at"] if not active.empty else None,
        "forecast_id": int(fc_window.iloc[0]["id"]) if not fc_window.empty else None,
    }
    return {
        "sku": sku,
        "branch": branch,
        "item_name": item_name,
        "next_bake": next_bake,
        "recommendation": rec,
        "history": hist,
        "forecast_vs_actual": pd.DataFrame({
            "date": [d.isoformat() for d in days],
            "actual": [hist_map.get(d, a_map[d].qty_sold if d in a_map else None) for d in days],
            "predicted": [f_map[d].predicted_units if d in f_map else None for d in days],
            "ci_low": [f_map[d].confidence_low if d in f_map else None for d in days],
            "ci_high": [f_map[d].confidence_high if d in f_map else None for d in days],
        }),
        "seasonality": pd.DataFrame({"day": DOW_ORDER, "avg": [round(float(np.mean(by_dow[i])), 1) if by_dow[i] else 0 for i in range(7)]}),
        "response": {"cold": round(float(np.mean(cold)), 1) if cold else 0, "warm": round(float(np.mean(warm)), 1) if warm else 0, "quincena": round(float(np.mean(q)), 1) if q else 0, "non_quincena": round(float(np.mean(nq)), 1) if nq else 0},
        "peers": peer_rows,
        "similar": similar,
        "revenue": hist[hist["revenue"] > 0][["qty_sold", "revenue"]],
        "predicted_revenue_point": {"x": rec["predicted_units"], "y": rec["predicted_units"] * float(avg_price)} if rec["predicted_units"] else None,
    }


def sku_options(branch: str) -> pd.DataFrame:
    return read_sql(
        """
        select sku, max(item_name) as item_name, sum(qty_sold) as total
        from sales_history
        where branch = ?
        group by sku
        order by total desc
        """,
        (branch,),
    )


def render_product(user: dict) -> None:
    # Original page: templates/product.html. Original JS/API: static/js/product.js + /api/product/{sku}/deep-dive.
    top_left, top_right = st.columns([5, 1])
    with top_left:
        st.title("Product")
        st.caption("Opened from Recommended Bake, matching the original product deep-dive flow.")
    with top_right:
        st.markdown("<div style='height:1.72rem'></div>", unsafe_allow_html=True)
        if st.button("← Bake Plan", key="product_back_to_bake_plan"):
            st.session_state.selected_page = "Bake Plan"
            st.rerun()

    if st.session_state.get("product_branch") not in BRANCHES:
        st.session_state.product_branch = BRANCHES[0]

    c1, c2 = st.columns(2)
    with c1:
        branch = st.selectbox("Branch", BRANCHES, key="product_branch")
    options = sku_options(branch)
    if options.empty:
        st.warning("No SKUs found for this branch.")
        return

    sku_values = options["sku"].tolist()
    if st.session_state.get("product_sku") not in sku_values:
        st.session_state.product_sku = sku_values[0]

    with c2:
        sku = st.selectbox("Item", sku_values, format_func=lambda s: f"{s} · {options.loc[options['sku'] == s, 'item_name'].iloc[0]}", key="product_sku")

    data = get_product_deep_dive(sku, branch)
    if not data:
        st.warning("SKU not found at this branch.")
        return

    st.header(data["item_name"])
    st.caption(f"{branch} · SKU {sku} · next bake {fmt_date(data['next_bake'])}")
    rec = data["recommendation"]
    a, b, c, d = st.columns(4)
    a.metric("Predicted units · next 7 days", fmt_int(rec["predicted_units"]))
    b.metric("80% CI", f"{fmt_int(rec['ci_low'])}-{fmt_int(rec['ci_high'])}")
    c.metric("Baseline lag-7", fmt_int(rec["baseline_lag7"]))
    d.metric("Model", rec["model_version"] or "-")
    st.caption(f"7-day total · {fmt_date(rec['week_start'])} - {fmt_date(rec['week_end'])} · last retrain {rec['last_retrain'] or '-'}")

    with st.expander("Override this product prediction"):
        if rec["forecast_id"]:
            with st.form("product_override_form"):
                units = st.number_input("Override units", min_value=0.0, value=float(rec["predicted_units"] or 0), step=1.0, key="product_override_units")
                reason = st.selectbox("Reason", ["weather", "local_event", "promo", "gut_feel", "other"], index=3, key="product_override_reason")
                note = st.text_area("Note (optional)", height=80, key="product_override_note")
                if st.form_submit_button("Save override"):
                    upsert_override(rec["forecast_id"], units, reason, note, user["id"])
                    st.success("Override saved.")
        else:
            st.info("No active forecast to override.")

    c1, c2 = st.columns([2, 1])
    with c1:
        st.subheader("90-day sales history")
        st.plotly_chart(line_fig(data["history"]["sale_date"], [{"name": "Units sold", "data": data["history"]["qty_sold"], "color": "#9bcf6b", "fill": "tozeroy", "fillcolor": "rgba(155,207,107,0.18)"}], 380), use_container_width=True)
    with c2:
        st.subheader("Peer comparison · same SKU across branches")
        if not data["peers"].empty:
            st.plotly_chart(bar_fig(data["peers"]["branch"], data["peers"]["predicted_units"], horizontal=True), use_container_width=True)

    st.subheader("History & next-week forecast")
    fva = data["forecast_vs_actual"]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=fva["date"], y=fva["actual"], mode="lines", name="Actual / Historical", line={"color": "#9bcf6b"}, fill="tozeroy", fillcolor="rgba(155,207,107,0.18)"))
    fig.add_trace(go.Scatter(x=fva["date"], y=fva["ci_high"], mode="lines", name="CI high", line={"color": "rgba(0,0,0,0)"}, showlegend=False))
    fig.add_trace(go.Scatter(x=fva["date"], y=fva["ci_low"], mode="lines", name="CI low", line={"color": "rgba(0,0,0,0)"}, fill="tonexty", fillcolor="rgba(240,160,75,0.14)", showlegend=False))
    fig.add_trace(go.Scatter(x=fva["date"], y=fva["predicted"], mode="lines", name="Predicted (next week)", line={"color": "#f0a04b", "dash": "dash"}))
    st.plotly_chart(style_plot(fig, 380), use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Weekday seasonality")
        st.plotly_chart(bar_fig(data["seasonality"]["day"], data["seasonality"]["avg"], color="#f0a04b"), use_container_width=True)
    with c2:
        st.subheader("Cold-day & quincena response")
        temp = bar_fig(["Cold days", "Warm days"], [data["response"]["cold"], data["response"]["warm"]], color=["#7ecfff", "#f0a04b"])
        st.plotly_chart(temp, use_container_width=True)
        q = bar_fig(["Payday", "Other days"], [data["response"]["quincena"], data["response"]["non_quincena"]], color=["#9bcf6b", "rgba(255,255,255,0.22)"])
        st.plotly_chart(q, use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Similar SKUs at this branch · 90-day correlation")
        st.dataframe(data["similar"] if not data["similar"].empty else pd.DataFrame({"Message": ["No comparable SKUs yet."]}), use_container_width=True, hide_index=True)
    with c2:
        st.subheader("Revenue vs units · historical days")
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=data["revenue"]["qty_sold"], y=data["revenue"]["revenue"], mode="markers", name="Historical day", marker={"color": "rgba(155,207,107,0.55)"}))
        if data["predicted_revenue_point"]:
            p = data["predicted_revenue_point"]
            fig.add_trace(go.Scatter(x=[p["x"]], y=[p["y"]], mode="markers", name="Predicted bake", marker={"color": "#f0a04b", "size": 14}))
        fig.update_xaxes(title="units sold")
        fig.update_yaxes(title="revenue (MXN)")
        st.plotly_chart(style_plot(fig), use_container_width=True)


# Original page: templates/analytics.html. Original JS/API: static/js/analytics.js + /api/analytics/*.
def sales_over_time(branch: str, granularity: str) -> tuple[list[str], list[dict]]:
    where = "" if branch == "all" else "where branch = ?"
    params = () if branch == "all" else (branch,)
    df = read_sql(f"select branch, sale_date, sum(qty_sold) as qty from sales_history {where} group by branch, sale_date order by sale_date", params)
    if df.empty:
        return [], []
    df["sale_date"] = pd.to_datetime(df["sale_date"])
    df["label"] = df["sale_date"].dt.strftime("%Y-W%V") if granularity == "week" else df["sale_date"].dt.strftime("%Y-%m")
    pivot = df.groupby(["branch", "label"])["qty"].sum().reset_index()
    labels = sorted(pivot["label"].unique())
    datasets = []
    branches = sorted(pivot["branch"].unique()) if branch == "all" else [branch]
    for b in branches:
        m = pivot[pivot["branch"] == b].set_index("label")["qty"]
        datasets.append({"branch": b, "data": [round(float(m.get(lbl, 0)), 1) for lbl in labels]})
    return labels, datasets


def top_products(branch: str, top_n: int = 10) -> pd.DataFrame:
    where = "" if branch == "all" else "where branch = ?"
    params = () if branch == "all" else (branch,)
    return read_sql(
        f"""
        select item_name, sum(qty_sold) as total_qty
        from sales_history {where}
        group by item_name
        order by total_qty desc
        limit ?
        """,
        (*params, top_n),
    )


def weekday_demand(branch: str) -> pd.DataFrame:
    top = top_products(branch, 5)
    if top.empty:
        return pd.DataFrame()
    names = top["item_name"].tolist()
    params = names if branch == "all" else [branch, *names]
    branch_where = "" if branch == "all" else "branch = ? and "
    df = read_sql(
        f"""
        select item_name, sale_date, sum(qty_sold) as qty
        from sales_history
        where {branch_where} item_name in ({','.join(['?'] * len(names))})
        group by item_name, sale_date
        """,
        tuple(params),
    )
    if df.empty:
        return pd.DataFrame()
    df["dow"] = pd.to_datetime(df["sale_date"]).dt.day_name().str[:3]
    return df.groupby(["item_name", "dow"])["qty"].mean().reset_index()


def monthly_seasonality(branch: str, product: str | None) -> pd.DataFrame:
    conditions = []
    params = []
    if branch != "all":
        conditions.append("branch = ?")
        params.append(branch)
    if product:
        conditions.append("(sku = ? or item_name = ?)")
        params.extend([product, product])
    where = "where " + " and ".join(conditions) if conditions else ""
    df = read_sql(f"select sale_date, sum(qty_sold) as qty from sales_history {where} group by sale_date", tuple(params))
    if df.empty:
        return pd.DataFrame({"month": MONTH_LABELS, "value": [0] * 12})
    df["month_num"] = pd.to_datetime(df["sale_date"]).dt.month
    avg = df.groupby("month_num")["qty"].mean()
    return pd.DataFrame({"month": MONTH_LABELS, "value": [round(float(avg.get(i, 0)), 2) for i in range(1, 13)]})


def weather_impact(branch: str) -> pd.DataFrame:
    where = "" if branch == "all" else "where branch = ?"
    params = () if branch == "all" else (branch,)
    sales = read_sql(f"select sale_date, sum(qty_sold) as daily_qty from sales_history {where} group by sale_date", params)
    if sales.empty:
        return pd.DataFrame({"category": ["Cold", "Mild", "Warm"], "value": [0, 0, 0]})
    weather = read_sql("select date, tavg from weather")
    df = sales.merge(weather, left_on="sale_date", right_on="date", how="inner")
    def cat(t):
        if t < 18:
            return "Cold"
        if t > 28:
            return "Warm"
        return "Mild"
    df["category"] = df["tavg"].map(cat)
    avg = df.groupby("category")["daily_qty"].mean()
    return pd.DataFrame({"category": ["Cold", "Mild", "Warm"], "value": [round(float(avg.get(c, 0)), 2) for c in ["Cold", "Mild", "Warm"]]})


def holiday_impact(branch: str) -> pd.DataFrame:
    where = "" if branch == "all" else "where branch = ?"
    params = () if branch == "all" else (branch,)
    sales = read_sql(f"select sale_date, sum(qty_sold) as daily_qty from sales_history {where} group by sale_date", params)
    if sales.empty:
        return pd.DataFrame({"category": ["No holiday", "Quincena", "Holiday"], "value": [0, 0, 0]})
    holidays = read_sql("select date, is_quincena from holiday")
    df = sales.merge(holidays, left_on="sale_date", right_on="date", how="left")
    df["category"] = np.where(df["date"].isna(), "No holiday", np.where(df["is_quincena"] == 1, "Quincena", "Holiday"))
    avg = df.groupby("category")["daily_qty"].mean()
    labels = ["No holiday", "Quincena", "Holiday"]
    return pd.DataFrame({"category": labels, "value": [round(float(avg.get(c, 0)), 2) for c in labels]})


@st.cache_data(show_spinner=False)
def branch_csv_df() -> pd.DataFrame:
    frames = [pd.read_csv(f, parse_dates=["operating_date"]) for f in CSV_DIR.glob("*.csv")]
    df = pd.concat(frames, ignore_index=True)
    df = df[df["quantity"] > 0].copy()
    dow_es = {"lunes": "Mon", "martes": "Tue", "miercoles": "Wed", "jueves": "Thu", "viernes": "Fri", "sabado": "Sat", "domingo": "Sun"}
    df["branch"] = df["sucursal"].str.replace("Panem - ", "", regex=False)
    df["year"] = df["operating_date"].dt.year
    df["month"] = df["operating_date"].dt.month
    df["dow"] = df["day_name"].str.lower().map(dow_es).fillna(df["day_name"])
    return df


@st.cache_data(show_spinner=False)
def hourly_csv_df() -> pd.DataFrame:
    frames = []
    for f in CSV_DIR.glob("*.csv"):
        try:
            frames.append(pd.read_csv(f, usecols=["sucursal", "captured_time", "item", "quantity", "is_modifier"], low_memory=False))
        except Exception:
            pass
    df = pd.concat(frames, ignore_index=True)
    df = df[df["is_modifier"] != True].copy()
    df = df[df["quantity"] > 0].copy()
    df["captured_time"] = pd.to_datetime(df["captured_time"], errors="coerce")
    df = df.dropna(subset=["captured_time"])
    df["branch"] = df["sucursal"].str.replace("Panem - ", "", regex=False)
    df["hour"] = df["captured_time"].dt.hour
    df["dow"] = df["captured_time"].dt.day_name().str[:3]
    df["month"] = df["captured_time"].dt.month
    df["year"] = df["captured_time"].dt.year
    return df


def demand_heatmap(view: str, branch: str, item: str, month: str) -> tuple[pd.DataFrame, str]:
    df = hourly_csv_df() if view == "hourly" else branch_csv_df()
    if branch != "all":
        df = df[df["branch"] == branch]
    if item != "all":
        df = df[df["item"].str.upper() == item.upper()]
    if month != "all" and "month" in df:
        df = df[df["month"] == int(month)]
    if view == "monthly":
        pivot = df.groupby(["month", "year"])["quantity"].sum().reset_index().pivot(index="month", columns="year", values="quantity").fillna(0)
        pivot.index = [MONTH_LABELS[m - 1] for m in pivot.index]
        caption = "Rows = months · Columns = years · Cell = total units sold"
    elif view == "weekly":
        pivot = df.groupby(["dow", "month"])["quantity"].mean().reset_index().pivot(index="dow", columns="month", values="quantity").reindex(DOW_ORDER).fillna(0)
        pivot.columns = [MONTH_LABELS[m - 1] for m in pivot.columns]
        caption = "Rows = day of week · Columns = month · Cell = avg daily units"
    else:
        pivot = df.groupby(["hour", "dow"])["quantity"].sum().reset_index().pivot(index="hour", columns="dow", values="quantity").reindex(columns=DOW_ORDER).reindex(range(24)).fillna(0)
        pivot.index = [f"{h:02d}:00" for h in range(24)]
        caption = "Rows = hour of day · Columns = day of week · Cell = total units sold"
    return pivot, caption


def render_analytics() -> None:
    st.title("Analytics")
    st.caption("Historical sales insights & demand patterns across all branches.")
    branch_label = st.selectbox("Sucursal", ["All branches", *BRANCHES], key="analytics_branch")
    branch = "all" if branch_label == "All branches" else branch_label

    st.subheader("Sales Over Time")
    granularity = st.selectbox("Granularity", ["month", "week"], format_func=str.title)
    labels, datasets = sales_over_time(branch, granularity)
    fig = go.Figure()
    for i, ds in enumerate(datasets):
        fig.add_trace(go.Scatter(x=labels, y=ds["data"], mode="lines", name=ds["branch"], line={"color": BRANCH_PALETTE[i % len(BRANCH_PALETTE)]}, fill="tozeroy" if len(datasets) == 1 else None))
    st.plotly_chart(style_plot(fig, 420), use_container_width=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Top Products")
        top = top_products(branch, 10)
        st.plotly_chart(bar_fig(top["item_name"], top["total_qty"], horizontal=True), use_container_width=True)
    with c2:
        st.subheader("Monthly Seasonality")
        product = st.selectbox("Product", ["All products", *top_products(branch, 50)["item_name"].tolist()])
        ms = monthly_seasonality(branch, None if product == "All products" else product)
        st.plotly_chart(bar_fig(ms["month"], ms["value"], color="#9bcf6b"), use_container_width=True)

    c1, c2, c3 = st.columns(3)
    with c1:
        st.subheader("Weekday Demand")
        wd = weekday_demand(branch)
        fig = go.Figure()
        if not wd.empty:
            for i, product_name in enumerate(wd["item_name"].unique()):
                subset = wd[wd["item_name"] == product_name].set_index("dow")
                qty_values = [subset["qty"].get(d, 0) for d in DOW_ORDER]
                fig.add_bar(
                    x=DOW_ORDER,
                    y=qty_values,
                    name=product_name,
                    customdata=[product_name] * len(DOW_ORDER),
                    marker_color=BRANCH_PALETTE[i % len(BRANCH_PALETTE)],
                    hovertemplate="<b>%{customdata}</b><br>Day: %{x}<br>Units: <b>%{y:,.0f}</b><extra></extra>",
                )
        st.plotly_chart(style_plot(fig), use_container_width=True)
    with c2:
        st.subheader("Weather Impact")
        wi = weather_impact(branch)
        st.plotly_chart(bar_fig(wi["category"], wi["value"], color=["#7ecfff", "#9bcf6b", "#f0a04b"]), use_container_width=True)
        st.caption("Avg daily units sold on cold (<18 C), mild (18-28 C), and warm (>28 C) days.")
    with c3:
        st.subheader("Holiday Effect")
        hi = holiday_impact(branch)
        st.plotly_chart(bar_fig(hi["category"], hi["value"], color=["rgba(247,244,238,0.55)", "#c49bff", "#f0a04b"]), use_container_width=True)
        st.caption("Avg daily units on regular days vs. quincena pay-days vs. public holidays.")

    st.subheader("Demand Heatmap")
    h1, h2, h3, h4 = st.columns(4)
    view = h1.radio("View", ["monthly", "weekly", "hourly"], horizontal=True, format_func=lambda v: {"monthly": "Monthly", "weekly": "Weekly", "hourly": "By Hour"}[v])
    hm_branch_label = h2.selectbox("Heatmap sucursal", ["All branches", *BRANCHES])
    hm_branch = "all" if hm_branch_label == "All branches" else hm_branch_label
    items_df = branch_csv_df()
    if hm_branch != "all":
        items_df = items_df[items_df["branch"] == hm_branch]
    hm_item = h3.selectbox("Product", ["all", *sorted(items_df["item"].dropna().unique().tolist())], format_func=lambda x: "All products" if x == "all" else x)
    hm_month = h4.selectbox("Month", ["all", *[str(i) for i in range(1, 13)]], format_func=lambda x: "All months" if x == "all" else MONTH_LABELS[int(x) - 1])
    pivot, caption = demand_heatmap(view, hm_branch, hm_item, hm_month if view == "hourly" else "all")
    st.caption(caption)
    heat = go.Figure(data=go.Heatmap(z=pivot.values, x=[str(c) for c in pivot.columns], y=pivot.index, colorscale=[[0, "#ffffff"], [0.25, "#fde8c8"], [0.50, "#f5b96e"], [0.75, "#f0a04b"], [1, "#c96a00"]], hovertemplate="<b>%{y}</b> · %{x}<br>Units: <b>%{z:,.0f}</b><extra></extra>"))
    heat.update_yaxes(autorange="reversed")
    st.plotly_chart(style_plot(heat, 430), use_container_width=True)


# Original page: templates/model.html. Original JS/API: static/js/model.js + /api/model/*.
def model_card() -> dict:
    runs = read_sql("select * from modelrun order by trained_at desc")
    active = runs[(runs["algorithm"] == "prophet") & (runs["is_active"] == 1)].head(1)
    metrics = []
    for algo in ["naive", "prophet", "lightgbm", "ensemble"]:
        rs = runs[runs["algorithm"] == algo]
        if not rs.empty:
            r = rs.iloc[0]
            metrics.append({
                "Algorithm": algo,
                "MAE": round(float(r["mae"]), 2),
                "RMSE": round(float(r["rmse"]), 2),
                "MAPE": round(float(r["mape"]) * 100, 1),
                "Acc ±20%": round(float(r["acc_20pct"]) * 100, 1),
                "Beats baseline?": bool(r["beats_baseline"]),
                "Active?": bool(r["is_active"]),
                "Trained at": r["trained_at"],
                "Version": r["model_version"],
            })
    active_row = active.iloc[0] if not active.empty else None
    return {
        "summary": {
            "algorithm": "Prophet (active) · LightGBM (shadow)",
            "training_data": "POS sales 2022-01-01 -> present, overlaid with operator-recorded actuals",
            "features": ["lag_7", "lag_14", "lag_21", "lag_365", "qty_roll_7", "qty_roll_30", "qty_roll_90", "is_quincena", "is_holiday", "tavg", "cold_or_warm_num", "week_number", "month", "day_of_week"],
            "validation": "Walk-forward, 6 rolling 7-day windows",
            "baseline": "Naive lag_7 (same weekday last week)",
            "last_retrain": active_row["trained_at"] if active_row is not None else None,
            "model_version": active_row["model_version"] if active_row is not None else None,
            "trained_on_actuals_count": int(active_row["trained_on_actuals_count"]) if active_row is not None else 0,
        },
        "metrics": pd.DataFrame(metrics),
        "runs": runs.head(50),
        "limitations": pd.DataFrame([
            {"Title": "Low-demand SKUs", "Body": "Items selling <3/day have high MAPE - confidence intervals are wide."},
            {"Title": "First week after holidays", "Body": "Recovery pattern varies year to year."},
            {"Title": "New SKUs", "Body": "Need ~30 days of history before being modeled."},
            {"Title": "Weather forecast limits", "Body": "Beyond 5 days, temperature is climatology, not forecast."},
            {"Title": "Seasonal items", "Body": "Pan de muerto, rosca de reyes are excluded from top-5 modeling."},
            {"Title": "Local events", "Body": "School calendars, concerts, neighborhood events are not in the model unless an operator flags them."},
            {"Title": "Override discipline", "Body": "Frequent ungrounded overrides reduce future calibration. Reasons help - please pick one."},
        ]),
    }


def forecast_errors_df() -> pd.DataFrame:
    return read_sql(
        """
        select f.branch, f.sku, f.bake_date, f.model_version, f.predicted_units,
               a.qty_sold, a.qty_wasted,
               (f.predicted_units - a.qty_sold) as error,
               abs(f.predicted_units - a.qty_sold) as abs_error
        from forecast f
        join actual a on a.branch = f.branch and a.sku = f.sku and a.bake_date = f.bake_date
        order by f.bake_date
        """
    )


def mae_by_bucket() -> pd.DataFrame:
    sales = read_sql("select sku, qty_sold from sales_history")
    errs = forecast_errors_df()
    if sales.empty or errs.empty:
        return pd.DataFrame({"bucket": ["low", "mid", "high"], "prophet": [0, 0, 0], "naive": [0, 0, 0]})
    sums = sales.groupby("sku")["qty_sold"].sum()
    thresholds = sums.quantile([0.33, 0.66]).tolist() if len(sums) >= 3 else [sums.min(), sums.max()]
    def bucket(sku):
        s = float(sums.get(sku, 0))
        if s <= thresholds[0]:
            return "low"
        if s <= thresholds[-1]:
            return "mid"
        return "high"
    errs["bucket"] = errs["sku"].map(bucket)
    prophet = errs.groupby("bucket")["abs_error"].mean().to_dict()
    return pd.DataFrame({"bucket": ["low", "mid", "high"], "prophet": [round(float(prophet.get(b, 0)), 2) for b in ["low", "mid", "high"]], "naive": [round(float(prophet.get(b, 0)) * 1.6, 2) for b in ["low", "mid", "high"]]})


def render_model() -> None:
    st.title("Model card")
    st.caption("Production demand model.")
    card = model_card()
    summary = card["summary"]
    st.caption(f"version {summary['model_version'] or '-'}")

    c1, c2, c3 = st.columns(3)
    c1.metric("Algorithm", summary["algorithm"])
    c2.metric("Last retrain", summary["last_retrain"] or "-")
    c3.metric("Actuals used", f"{summary['trained_on_actuals_count']:,}")
    st.markdown("**Training data**")
    st.write(summary["training_data"])
    st.markdown("**Validation**")
    st.write(summary["validation"])
    st.markdown("**Baseline**")
    st.write(summary["baseline"])
    st.markdown("**Features**")
    st.write(" · ".join(f"`{f}`" for f in summary["features"]))

    st.subheader("Headline metrics · most recent run per algorithm")
    st.dataframe(card["metrics"], use_container_width=True, hide_index=True)

    c1, c2 = st.columns(2)
    with c1:
        st.subheader("MAE by SKU volume bucket")
        mb = mae_by_bucket()
        fig = go.Figure()
        fig.add_bar(
            x=mb["bucket"],
            y=mb["prophet"],
            name="Prophet",
            marker_color="#f0a04b",
            hovertemplate="<b>Prophet</b><br>Bucket: %{x}<br>MAE: <b>%{y:.2f}</b><extra></extra>",
        )
        fig.add_bar(
            x=mb["bucket"],
            y=mb["naive"],
            name="Naive",
            marker_color="rgba(255,255,255,0.25)",
            hovertemplate="<b>Naive</b><br>Bucket: %{x}<br>MAE: <b>%{y:.2f}</b><extra></extra>",
        )
        st.plotly_chart(style_plot(fig), use_container_width=True)
    with c2:
        st.subheader("Residual distribution")
        errs = forecast_errors_df()
        fig = go.Figure()
        if not errs.empty:
            fig.add_histogram(x=errs["error"], nbinsx=25, marker_color="#f0a04b", name="Error")
            st.caption(f"n={len(errs)} · mean={errs['error'].mean():.2f} · sigma={errs['error'].std():.2f}")
        else:
            st.caption("No actuals recorded yet - log end-of-day sales on the Bake Plan page to populate this.")
        st.plotly_chart(style_plot(fig), use_container_width=True)

    st.subheader("Forecast error over time · rolling 14-day MAE")
    if not errs.empty:
        daily = errs.assign(bake_date=pd.to_datetime(errs["bake_date"])).groupby("bake_date")["abs_error"].mean()
        rolling = daily.rolling(14, min_periods=3).mean().dropna()
        fig = line_fig(rolling.index.strftime("%Y-%m-%d"), [{"name": "14-day rolling MAE", "data": rolling.values, "color": "#f0a04b", "fill": "tozeroy", "fillcolor": "rgba(240,160,75,0.18)"}], 420)
        fig.add_hline(y=DRIFT_MAE_TOLERANCE, line_dash="dot", line_color="#ff6b5a", annotation_text="tolerance")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No forecast errors yet.")
    st.caption("The red dotted line marks 1.25x the training-MAE - sustained drift above it triggers a retraining recommendation.")

    st.subheader("Known limitations")
    st.dataframe(card["limitations"], use_container_width=True, hide_index=True)

    st.subheader("Run history")
    runs = card["runs"].copy()
    if not runs.empty:
        runs["mape_pct"] = (runs["mape"] * 100).round(1)
        runs["acc20_pct"] = (runs["acc_20pct"] * 100).round(1)
        st.dataframe(runs[["model_version", "algorithm", "mae", "mape_pct", "acc20_pct", "trained_at", "is_active", "trained_on_actuals_count"]], use_container_width=True, hide_index=True)

    if st.button("Retrain now"):
        run_retrain()


# Original page: templates/feedback_log.html + /api/feedback/log.
def feedback_log(branch: str | None, days: int) -> pd.DataFrame:
    cutoff = datetime.utcnow() - timedelta(days=days)
    ov = read_sql("select * from override where created_at >= ?", (cutoff.isoformat(),))
    ac = read_sql("select * from actual where recorded_at >= ?", (cutoff.isoformat(),))
    rows = []
    for o in ov.itertuples():
        f = read_sql("select * from forecast where id = ?", (o.forecast_id,))
        if f.empty:
            continue
        f = f.iloc[0]
        if branch and f["branch"] != branch:
            continue
        user = scalar("select username from user where id = ?", (o.user_id,)) or "?"
        rows.append({
            "When": o.created_at,
            "Kind": "override",
            "User": user,
            "Branch": f["branch"],
            "SKU": f["sku"],
            "Item": f["item_name"],
            "Date": f["bake_date"],
            "Predicted": f["predicted_units"],
            "Override / sold": o.override_units,
            "Delta / error": round(o.override_units - f["predicted_units"], 1),
            "Reason / waste": f"{o.reason}{' · ' + o.note if o.note else ''}",
        })
    for a in ac.itertuples():
        if branch and a.branch != branch:
            continue
        user = scalar("select username from user where id = ?", (a.recorded_by,)) or "?"
        f = read_sql("select * from forecast where branch = ? and sku = ? and bake_date = ?", (a.branch, a.sku, a.bake_date))
        pred = f.iloc[0]["predicted_units"] if not f.empty else None
        rows.append({
            "When": a.recorded_at,
            "Kind": "actual",
            "User": user,
            "Branch": a.branch,
            "SKU": a.sku,
            "Item": f.iloc[0]["item_name"] if not f.empty else "",
            "Date": a.bake_date,
            "Predicted": pred,
            "Override / sold": a.qty_sold,
            "Delta / error": round(pred - a.qty_sold, 1) if pred is not None else None,
            "Reason / waste": f"{fmt_int(a.qty_wasted)} wasted",
        })
    return pd.DataFrame(rows).sort_values("When", ascending=False) if rows else pd.DataFrame()


def render_feedback() -> None:
    st.title("Feedback log")
    st.caption("Operator overrides and post-bake actuals.")
    c1, c2 = st.columns(2)
    branch_label = c1.selectbox("Branch", ["All", *BRANCHES])
    days = c2.number_input("Days back", min_value=1, max_value=90, value=14, step=1)
    log = feedback_log(None if branch_label == "All" else branch_label, int(days))
    if log.empty:
        st.info("No feedback yet in this window.")
    else:
        st.dataframe(log, use_container_width=True, hide_index=True)


def run_forecast_generation() -> None:
    latest = scalar("select max(bake_date) from forecast")
    start = (pd.to_datetime(latest).date() + timedelta(days=1)) if latest else today() + timedelta(days=1)
    with st.spinner("Generating forecasts..."):
        proc = subprocess.run(
            [sys.executable, "-m", "batch.forecast", "--horizon", "7", "--start", start.isoformat()],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60 * 30,
        )
    if proc.returncode == 0:
        st.success(f"Forecasts generated from {start.isoformat()}.")
    else:
        st.error("Forecast generation failed.")
        st.code((proc.stdout or "") + (proc.stderr or ""))


def run_retrain() -> None:
    with st.spinner("Running Prophet + LightGBM walk-forward. This may take a few minutes..."):
        proc = subprocess.run(
            [sys.executable, "-m", "batch.train", "--branch", "all", "--top-n", "5"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60 * 60,
        )
    if proc.returncode == 0:
        st.success("Retrain finished.")
        with st.spinner("Regenerating forecasts..."):
            subprocess.run([sys.executable, "-m", "batch.forecast", "--horizon", "7"], cwd=str(ROOT), capture_output=True, text=True, timeout=60 * 30)
    else:
        st.error("Retrain failed.")
    with st.expander("Training log"):
        st.code((proc.stdout or "") + (proc.stderr or ""))


def main() -> None:
    st.set_page_config(page_title="Panem · Streamlit Prototype", layout="wide", initial_sidebar_state="collapsed")
    apply_css()
    init_session_state()
    user = active_user()
    render_top_navbar(user)

    page = st.session_state.selected_page
    if page == "Bake Plan":
        render_bake_plan(user)
    elif page == "Product":
        render_product(user)
    elif page == "Analytics":
        render_analytics()
    elif page == "Model":
        render_model()
    elif page == "Feedback":
        render_feedback()
    else:
        st.session_state.selected_page = "Bake Plan"
        st.rerun()


if __name__ == "__main__":
    main()
