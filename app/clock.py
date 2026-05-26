"""Monterrey-aware wall clock helpers. All UI defaults flow through here."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytz

from .config import settings

TZ = pytz.timezone(settings.tz_name)


def now() -> datetime:
    """Current wall time in the configured timezone (aware)."""
    return datetime.now(TZ)


def today() -> date:
    return now().date()


def default_bake_date() -> date:
    """The bake date a fresh operator should plan for, given the wall clock.

    Before plan_lock_hour: plan for tomorrow.
    After plan_lock_hour: plan for day-after-tomorrow (tomorrow is locked).
    """
    n = now()
    if n.hour < settings.plan_lock_hour:
        return n.date() + timedelta(days=1)
    return n.date() + timedelta(days=2)


def plan_mode_for(bake_date: date) -> str:
    """Return 'plan' | 'locked' | 'actuals' for a given bake date.

    - bake_date in the future and now < plan_lock_hour → plan
    - bake_date in the future and now >= plan_lock_hour → locked
    - bake_date == today and now < actuals_open_hour   → locked
    - bake_date == today and now >= actuals_open_hour  → actuals
    - bake_date in the past                            → actuals
    """
    n = now()
    today_ = n.date()
    if bake_date > today_:
        if bake_date == today_ + timedelta(days=1) and n.hour >= settings.plan_lock_hour:
            return "locked"
        return "plan"
    if bake_date == today_:
        return "actuals" if n.hour >= settings.actuals_open_hour else "locked"
    return "actuals"


def server_now_iso() -> str:
    return now().isoformat()
