import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

from .audio.features import PauseSettings
from .audio.pitch import PitchSettings

BACKEND_ROOT = Path(__file__).resolve().parents[1]

# Optional local configuration and secrets; a missing file is fine. Real environment variables win.
load_dotenv(BACKEND_ROOT / ".env")

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _env(name: str, default: str | None = None) -> str | None:
    """Environment value, treating empty strings (such as `HF_TOKEN=`) as unset."""
    return os.getenv(name, "").strip() or default


@dataclass(frozen=True)
class Settings:
    service_name: str = "speakiq-ai-coach-backend"
    environment: str = field(default_factory=lambda: _env("APP_ENV", "development"))
    cors_origins: list[str] = field(
        default_factory=lambda: _split_csv(_env("BACKEND_CORS_ORIGINS", DEFAULT_CORS_ORIGINS))
    )
    max_upload_mb: float = field(default_factory=lambda: float(_env("MAX_UPLOAD_MB", "25")))
    max_audio_seconds: float = field(default_factory=lambda: float(_env("MAX_AUDIO_SECONDS", "300")))

    pause_settings: PauseSettings = field(
        default_factory=lambda: PauseSettings(
            silence_below_speech_db=float(_env("PAUSE_SILENCE_BELOW_SPEECH_DB", "25")),
            noise_margin_db=float(_env("PAUSE_NOISE_MARGIN_DB", "3")),
            min_pause_sec=float(_env("PAUSE_MIN_SEC", "0.25")),
        )
    )

    pitch_settings: PitchSettings = field(
        default_factory=lambda: PitchSettings(min_hz=float(_env("PITCH_MIN_HZ", "50")), max_hz=float(_env("PITCH_MAX_HZ", "600")))
    )

    whisper_model: str = field(default_factory=lambda: _env("WHISPER_MODEL", "base"))
    whisper_device: str = field(default_factory=lambda: _env("WHISPER_DEVICE", "cpu"))
    whisper_compute_type: str = field(default_factory=lambda: _env("WHISPER_COMPUTE_TYPE", "int8"))
    whisper_language: str | None = field(default_factory=lambda: _env("WHISPER_LANGUAGE"))
    whisper_download_root: str | None = field(default_factory=lambda: _env("WHISPER_DOWNLOAD_ROOT"))
    # Optional storage of analysis results. The service-role key is a secret with full database access:
    # backend only, excluded from repr, never returned by the API, never in a VITE_ variable.
    supabase_url: str | None = field(default_factory=lambda: _env("SUPABASE_URL"))
    supabase_service_role_key: str | None = field(default_factory=lambda: _env("SUPABASE_SERVICE_ROLE_KEY"), repr=False)
    supabase_table: str = field(default_factory=lambda: _env("SUPABASE_TABLE", "analyses"))
    max_saved_result_mb: float = field(default_factory=lambda: float(_env("MAX_SAVED_RESULT_MB", "5")))

    # Secret. Excluded from repr so it cannot end up in logs or tracebacks. Never return it from the API.
    hf_token: str | None = field(default_factory=lambda: _env("HF_TOKEN"), repr=False)

    @property
    def max_upload_bytes(self) -> int:
        return int(self.max_upload_mb * 1024 * 1024)


def get_settings() -> Settings:
    return Settings()
