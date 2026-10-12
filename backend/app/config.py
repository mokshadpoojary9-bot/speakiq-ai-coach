import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]

# Optional local configuration; a missing .env is fine.
load_dotenv(REPO_ROOT / ".env")

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Settings:
    service_name: str = "speakiq-ai-coach-backend"
    environment: str = field(default_factory=lambda: os.getenv("APP_ENV", "development"))
    cors_origins: list[str] = field(
        default_factory=lambda: _split_csv(os.getenv("BACKEND_CORS_ORIGINS", DEFAULT_CORS_ORIGINS))
    )
    max_upload_mb: float = field(default_factory=lambda: float(os.getenv("MAX_UPLOAD_MB", "25")))
    max_audio_seconds: float = field(default_factory=lambda: float(os.getenv("MAX_AUDIO_SECONDS", "300")))

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)


def get_settings() -> Settings:
    return Settings()
