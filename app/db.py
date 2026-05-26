"""SQLite engine + session."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime
from typing import Generator

from sqlmodel import Session, SQLModel, create_engine

from .config import settings

engine = create_engine(
    f"sqlite:///{settings.db_path}",
    echo=False,
    connect_args={"check_same_thread": False},
)


def init_db() -> None:
    # Import so SQLModel sees the table definitions.
    from . import models  # noqa: F401
    SQLModel.metadata.create_all(engine)
    _ensure_views()


def _ensure_views() -> None:
    """Create the forecast_errors VIEW joining forecasts to actuals."""
    from sqlalchemy import text
    with engine.begin() as conn:
        conn.execute(text("""
            CREATE VIEW IF NOT EXISTS forecast_errors AS
            SELECT
              f.id           AS forecast_id,
              a.id           AS actual_id,
              f.branch       AS branch,
              f.sku          AS sku,
              f.bake_date    AS bake_date,
              f.model_version AS model_version,
              f.predicted_units AS predicted_units,
              a.qty_sold     AS qty_sold,
              a.qty_wasted   AS qty_wasted,
              (f.predicted_units - a.qty_sold) AS error,
              ABS(f.predicted_units - a.qty_sold) AS abs_error,
              CASE WHEN a.qty_sold > 0
                   THEN ABS(f.predicted_units - a.qty_sold) / a.qty_sold
                   ELSE NULL END AS pct_error
            FROM forecast f
            JOIN actual a
              ON a.branch = f.branch
             AND a.sku = f.sku
             AND a.bake_date = f.bake_date
        """))


@contextmanager
def session_scope() -> Generator[Session, None, None]:
    s = Session(engine)
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()


def get_session() -> Generator[Session, None, None]:
    """FastAPI dependency."""
    with Session(engine) as s:
        yield s
