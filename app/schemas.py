"""Pydantic request/response shapes."""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel


class OverrideIn(BaseModel):
    forecast_id: int
    override_units: float
    reason: str
    note: str = ""


class ActualIn(BaseModel):
    branch: str
    sku: str
    bake_date: date
    qty_sold: float
    qty_wasted: float = 0.0


class LockIn(BaseModel):
    branch: str
    bake_date: date


class RetrainIn(BaseModel):
    branches: Optional[list[str]] = None
    top_n: int = 5


class ForecastRow(BaseModel):
    id: int
    branch: str
    sku: str
    item_name: str
    bake_date: date
    predicted_units: float
    confidence_low: float
    confidence_high: float
    model_version: str
    last_week_avg: Optional[float] = None
    override: Optional[float] = None
    override_reason: Optional[str] = None
    generated_at: datetime


class ServerTime(BaseModel):
    server_now: str
    today: date
    default_bake_date: date
    plan_lock_hour: int
    actuals_open_hour: int
