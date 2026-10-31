"""Runtime settings from environment variables (all optional; demo defaults)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent


def _read_env_file(path: Path) -> None:
    """Load KEY=VALUE lines from backend/.env without overriding real environment variables."""
    if not path.is_file():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return int(raw) if raw not in (None, "") else default


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return float(raw) if raw not in (None, "") else default


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    timetable: str  # folder under data/: "tag2026" (real, default) or "simulated" (demo/tests)
    availability_provider: str  # "auto" | "simulated" | "none" | "railradar" | "live"
    demo_date: date | None  # anchor for scripted demo scenarios; default today + 7
    cors_origins: tuple[str, ...]
    max_advance_days: int
    search_timeout_seconds: float
    stale_after_minutes: int
    live_provider_url: str | None
    live_provider_key: str | None
    railradar_key: str | None = None  # your own RailRadar key; enables live checks of single tickets
    railradar_url: str = "https://api.railradar.in/v1"
    live_monthly_limit: int = 90  # hard cap on live requests per calendar month (free tier: 100)
    live_cache_minutes: int = 30
    state_dir: Path | None = None  # where the monthly request count is kept


def load_settings(env_file: Path | None = BACKEND_DIR / ".env") -> Settings:
    if env_file is not None:
        _read_env_file(env_file)
    demo = os.getenv("WIMS_DEMO_DATE")
    railradar_key = os.getenv("WIMS_RAILRADAR_KEY") or None
    origins = os.getenv("WIMS_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000")
    return Settings(
        data_dir=Path(os.getenv("WIMS_DATA_DIR", str(BACKEND_DIR / "data"))),
        timetable=os.getenv("WIMS_TIMETABLE", "tag2026"),
        availability_provider=os.getenv("WIMS_AVAILABILITY_PROVIDER", "railradar" if railradar_key else "auto").lower(),
        demo_date=date.fromisoformat(demo) if demo else None,
        cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip()),
        max_advance_days=_int("WIMS_MAX_ADVANCE_DAYS", 60),
        search_timeout_seconds=_float("WIMS_SEARCH_TIMEOUT_SECONDS", 8.0),
        stale_after_minutes=_int("WIMS_STALE_AFTER_MINUTES", 360),
        live_provider_url=os.getenv("WIMS_LIVE_PROVIDER_URL") or None,
        live_provider_key=os.getenv("WIMS_LIVE_PROVIDER_KEY") or None,
        railradar_key=railradar_key,
        railradar_url=os.getenv("WIMS_RAILRADAR_URL") or "https://api.railradar.in/v1",
        live_monthly_limit=_int("WIMS_LIVE_MONTHLY_LIMIT", 90),
        live_cache_minutes=_int("WIMS_LIVE_CACHE_MINUTES", 30),
        state_dir=Path(os.getenv("WIMS_STATE_DIR", str(BACKEND_DIR / ".state"))),
    )
