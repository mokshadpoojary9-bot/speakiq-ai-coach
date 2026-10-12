from typing import Annotated, Literal

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from . import __version__
from .audio import AudioError, AudioFeatures, analyze_upload
from .config import Settings, get_settings

MAX_TRANSCRIPT_CHARS = 20_000


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    app = FastAPI(title="SpeakIQ AI Coach API", version=__version__)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        return HealthResponse(
            status="ok",
            service=settings.service_name,
            version=__version__,
            environment=settings.environment,
        )

    @app.post("/analysis/features", response_model=AudioFeatures, tags=["analysis"])
    def analysis_features(
        file: Annotated[UploadFile, File(description="Audio recording: WAV, FLAC, OGG or MP3.")],
        transcript: Annotated[str | None, Form(max_length=MAX_TRANSCRIPT_CHARS)] = None,
    ) -> AudioFeatures:
        """Measure acoustic features of one recording. Synchronous; the upload is processed in memory and not stored."""
        data = file.file.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            raise HTTPException(413, f"The file is larger than the {settings.max_upload_mb:g} MB limit.")
        try:
            return analyze_upload(
                data, file.filename or "upload", transcript, max_duration_sec=settings.max_audio_seconds
            )
        except AudioError as error:
            raise HTTPException(error.status_code, error.message) from error

    return app


app = create_app()
