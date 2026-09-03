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
    ocr_language: str = "en"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()
