"""Application settings and path helpers."""

from __future__ import annotations

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "data"
DB_PATH = DATA_DIR / "memories.db"


def ensure_data_dir() -> None:
    """Ensure the local data directory exists."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
