"""SQLModel tables."""
from __future__ import annotations

import datetime as _dt
from datetime import date, datetime
from typing import Optional

from sqlmodel import Field, SQLModel


class User(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True, index=True)
    password_hash: str
    role: str  # 'operator' | 'analyst'


class Forecast(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    branch: str = Field(index=True)
    sku: str = Field(index=True)
    item_name: str = ""
    bake_date: date = Field(index=True)
    predicted_units: float
    confidence_low: float
    confidence_high: float
    model_version: str
    algorithm: str = "prophet"
    generated_at: datetime = Field(default_factory=datetime.utcnow)


class Override(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    forecast_id: int = Field(foreign_key="forecast.id", index=True)
    user_id: int = Field(foreign_key="user.id")
    override_units: float
    reason: str  # weather | local_event | promo | gut_feel | other
    note: str = ""
    created_at: datetime = Field(default_factory=datetime.utcnow)


class Actual(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    branch: str = Field(index=True)
    sku: str = Field(index=True)
    bake_date: date = Field(index=True)
    qty_sold: float
    qty_wasted: float = 0.0
    recorded_by: int = Field(foreign_key="user.id")
    recorded_at: datetime = Field(default_factory=datetime.utcnow)


class ModelRun(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    model_version: str = Field(index=True)
    algorithm: str  # prophet | lightgbm | ensemble | naive
    trained_at: datetime = Field(default_factory=datetime.utcnow)
    training_window_start: Optional[date] = None
    training_window_end: Optional[date] = None
    mae: float
    rmse: float
    mape: float
    acc_20pct: float
    beats_baseline: bool = False
    is_active: bool = False
    promoted_at: Optional[datetime] = None
    trained_on_actuals_count: int = 0
    notes: str = ""


class SalesHistory(SQLModel, table=True):
    __tablename__ = "sales_history"
    id: Optional[int] = Field(default=None, primary_key=True)
    branch: str = Field(index=True)
    sku: str = Field(index=True)
    item_name: str = ""
    sale_date: date = Field(index=True)
    qty_sold: float
    unit_price: float = 0.0
    revenue: float = 0.0


class Holiday(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    date: _dt.date = Field(unique=True)
    name: str
    is_quincena: bool = False


class Weather(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    date: _dt.date = Field(unique=True)
    tavg: float
    cold_or_warm_num: int = 0  # -1 cold, 0 mild, 1 warm


class PlanLock(SQLModel, table=True):
    """Records when a branch's bake plan was locked for a given date."""
    __tablename__ = "plan_lock"
    id: Optional[int] = Field(default=None, primary_key=True)
    branch: str = Field(index=True)
    bake_date: date = Field(index=True)
    locked_at: datetime = Field(default_factory=datetime.utcnow)
    locked_by: int = Field(foreign_key="user.id")
