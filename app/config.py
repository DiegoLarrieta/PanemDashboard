"""App configuration loaded from environment."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


class Settings:
    db_path: str = os.getenv("DB_PATH", str(BASE_DIR / "panem.db"))
    models_dir: Path = Path(os.getenv("MODELS_DIR", str(BASE_DIR / "models")))

    jwt_secret: str = os.getenv("JWT_SECRET", "dev-only-change-me")
    jwt_algorithm: str = os.getenv("JWT_ALGORITHM", "HS256")
    jwt_expire_hours: int = int(os.getenv("JWT_EXPIRE_HOURS", "12"))

    tz_name: str = os.getenv("TZ", "America/Monterrey")

    drift_mae_tolerance: float = float(os.getenv("DRIFT_MAE_TOLERANCE", "1.25"))
    plan_lock_hour: int = int(os.getenv("PLAN_LOCK_HOUR", "16"))
    actuals_open_hour: int = int(os.getenv("ACTUALS_OPEN_HOUR", "21"))

    # Asymmetric production target: 0.50 = median (symmetric), 0.65 = bias
    # toward overproduction to reduce stockouts. For perishable bakery goods
    # where a stockout loses ~3x the margin that waste costs, 0.60-0.70 is
    # the sweet spot. Adjustable per-deployment via env var.
    service_level: float = float(os.getenv("SERVICE_LEVEL", "0.65"))

    branches: list[str] = [
        "Punto Valle",
        "Hotel Kavia",
        "Plaza QIN",
        "Hospital Zambrano",
        "La Carreta",
        "Plaza Nativa",
        "Credi Club",
    ]


settings = Settings()
settings.models_dir.mkdir(parents=True, exist_ok=True)
