from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    app_name: str = "LabelGuard API"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://labelguard:labelguard@localhost:5432/labelguard"
    upload_dir: Path = Path("uploads")
    max_upload_bytes: int = 10 * 1024 * 1024
    ocr_languages: str = "en,hi"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_ocr_languages(settings: Settings | None = None) -> tuple[str, ...]:
    """Parse a comma-separated language list while preserving future extensibility."""
    configured = (settings or get_settings()).ocr_languages
    languages = tuple(dict.fromkeys(code.strip().lower() for code in configured.split(",") if code.strip()))
    if not languages:
        raise ValueError("OCR_LANGUAGES must include at least one PaddleOCR language code.")
    return languages
