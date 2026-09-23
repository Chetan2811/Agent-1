"""Environment-driven application settings."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

try:
    from dotenv import load_dotenv as _load_dotenv
except ModuleNotFoundError:  # Optional convenience; exported environment variables still work.
    _load_dotenv = None


ROOT = Path(__file__).resolve().parent
DEFAULT_GEMINI_MODEL = "gemini-3.6-flash"
if _load_dotenv is not None:
    _load_dotenv(ROOT / ".env")


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str | None = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    gemini_model: str = os.getenv("GEMINI_MODEL", DEFAULT_GEMINI_MODEL)
    database_url: str = os.getenv("DATABASE_URL", f"sqlite:///{ROOT / 'data' / 'montage.db'}")
    upload_dir: Path = Path(os.getenv("UPLOAD_DIR", ROOT / "uploads"))
    output_dir: Path = Path(os.getenv("OUTPUT_DIR", ROOT / "output"))
    temp_dir: Path = Path(os.getenv("TEMP_DIR", ROOT / "temp"))
    max_upload_mb: int = int(os.getenv("MAX_UPLOAD_MB", "300"))


def get_settings() -> Settings:
    return Settings()
