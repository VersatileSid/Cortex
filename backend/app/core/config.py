from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# Resolve this from the source tree, not the process working directory, so
# local Uvicorn invocations from either the repository or backend directory
# load the repository's single environment file consistently.
ROOT_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"


# These are the India-relevant language identifiers documented for the
# PP-OCRv3 models used by PaddleOCR 3.x.  They are deliberately separate from
# the UI locale list: a UI locale must never imply OCR support.
SUPPORTED_PADDLE_OCR_LANGUAGES = frozenset({
    "en", "hi", "gom", "mai", "mr", "ne", "sa", "ta", "te", "ur", "ka",
})


class Settings(BaseSettings):
    """Runtime configuration loaded from environment variables."""

    app_name: str = "LabelGuard API"
    environment: str = "development"
    database_url: str = "postgresql+psycopg://labelguard:labelguard@localhost:5432/labelguard"
    upload_dir: Path = Path("uploads")
    max_upload_bytes: int = 10 * 1024 * 1024
    ocr_languages: str = "en,hi,gom,mai,mr,ne,sa,ta,te,ur,ka"

    model_config = SettingsConfigDict(env_file=ROOT_ENV_FILE, env_file_encoding="utf-8", extra="ignore")


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_ocr_languages(settings: Settings | None = None) -> tuple[str, ...]:
    """Parse a comma-separated language list while preserving future extensibility."""
    configured = (settings or get_settings()).ocr_languages
    languages = tuple(dict.fromkeys(code.strip().lower() for code in configured.split(",") if code.strip()))
    if not languages:
        raise ValueError("OCR_LANGUAGES must include at least one PaddleOCR language code.")
    unsupported = sorted(set(languages) - SUPPORTED_PADDLE_OCR_LANGUAGES)
    if unsupported:
        raise ValueError(
            "OCR_LANGUAGES includes unsupported PaddleOCR 3.x language code(s): "
            f"{', '.join(unsupported)}. Supported codes: "
            f"{', '.join(sorted(SUPPORTED_PADDLE_OCR_LANGUAGES))}."
        )
    return languages
