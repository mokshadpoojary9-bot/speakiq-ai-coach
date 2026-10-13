from typing import Annotated, Literal

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import __version__
from .comparison import ComparisonResult, DeliveryAnalysis, compare_deliveries
from .audio import SUPPORTED_EXTENSIONS, AudioError, AudioFeatures, LoadedAudio, extract_features, load_audio
from .config import Settings, get_settings
from .speech import (
    Alignment,
    FasterWhisperTranscriber,
    SpeechError,
    Transcriber,
    Transcription,
    TranscriptionEngineStatus,
    align_transcript,
)

MAX_TRANSCRIPT_CHARS = 20_000

DESCRIPTION = """
Evidence-first speech delivery analysis. All times are in seconds.

Uploads are processed in memory and are not stored. Errors return
`{"detail": {"code": "...", "message": "..."}}` with a stable `code`.

Transcription runs locally with faster-whisper. The model is downloaded on first use,
so the first request to a transcription route can take a while.
"""

AudioFile = Annotated[UploadFile, File(description="Audio recording: WAV, FLAC, OGG or MP3.")]
OptionalTranscript = Annotated[
    str | None, Form(max_length=MAX_TRANSCRIPT_CHARS, description="The text the speaker was delivering.")
]
Language = Annotated[
    str | None,
    Form(max_length=8, pattern=r"^[A-Za-z]{2,3}(-[A-Za-z]{2})?$", description="Language code such as 'en'. Detected if omitted."),
]


class ErrorDetail(BaseModel):
    code: str
    message: str


class ErrorResponse(BaseModel):
    detail: ErrorDetail


class Limits(BaseModel):
    max_upload_mb: float
    max_audio_seconds: float
    supported_extensions: list[str]


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: str
    version: str
    environment: str
    limits: Limits
    transcription: TranscriptionEngineStatus


class ComponentStatus(BaseModel):
    status: Literal["completed", "unavailable", "failed"]
    code: str | None = None
    message: str | None = None


class Components(BaseModel):
    features: ComponentStatus
    transcription: ComponentStatus
    alignment: ComponentStatus


class AnalyzeResponse(BaseModel):
    is_demo: Literal[False] = False
    components: Components
    features: AudioFeatures
    transcription: Transcription | None = Field(description="Null when transcription could not run; see components.")
    alignment: Alignment | None = Field(description="Null when alignment could not run; see components.")
    limitations: list[str]


class RecordingSummary(BaseModel):
    filename: str
    duration_sec: float
    transcription: ComponentStatus
    alignment: ComponentStatus


class CompareResponse(BaseModel):
    is_demo: Literal[False] = False
    transcript_source: Literal["supplied", "reference_transcription", "none"] = Field(
        description="Which text both recordings were aligned to."
    )
    reference: RecordingSummary
    participant: RecordingSummary
    comparison: ComparisonResult


def _error(status_code: int, code: str, message: str) -> HTTPException:
    return HTTPException(status_code, {"code": code, "message": message})


ERROR_RESPONSES = {
    code: {"model": ErrorResponse} for code in (400, 413, 415, 422, 500, 503)
}


def create_app(settings: Settings | None = None, transcriber: Transcriber | None = None) -> FastAPI:
    settings = settings or get_settings()
    transcriber = transcriber or FasterWhisperTranscriber(settings)
    app = FastAPI(title="SpeakIQ AI Coach API", version=__version__, description=DESCRIPTION)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, error: RequestValidationError) -> JSONResponse:
        # Same shape as every other error, so clients handle one format.
        first = error.errors()[0]
        field = ".".join(str(part) for part in first["loc"] if part != "body") or "request"
        detail = ErrorDetail(code="invalid_request", message=f"{field}: {first['msg']}")
        return JSONResponse(status_code=422, content={"detail": detail.model_dump()})

    api = APIRouter(prefix="/api")

    def read_audio(file: UploadFile) -> LoadedAudio:
        data = file.file.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            raise _error(413, "upload_too_large", f"The file is larger than the {settings.max_upload_mb:g} MB limit.")
        try:
            return load_audio(data, file.filename or "upload", max_duration_sec=settings.max_audio_seconds)
        except AudioError as error:
            raise _error(error.status_code, error.code, error.message) from error

    def run_transcription(audio: LoadedAudio, language: str | None) -> Transcription:
        try:
            return transcriber.transcribe(audio.samples, audio.sample_rate, language)
        except SpeechError as error:
            raise _error(error.status_code, error.code, error.message) from error

    def run_alignment(transcript: str | None, transcription: Transcription) -> Alignment:
        supplied = bool(transcript and transcript.strip())
        return align_transcript(
            transcript if supplied else transcription.text,
            transcription.words,
            source="supplied" if supplied else "transcribed",
        )

    @api.get("/health", response_model=HealthResponse, tags=["system"])
    def health() -> HealthResponse:
        """Backend status and non-secret configuration. Never includes token values."""
        return HealthResponse(
            status="ok",
            service=settings.service_name,
            version=__version__,
            environment=settings.environment,
            limits=Limits(
                max_upload_mb=settings.max_upload_mb,
                max_audio_seconds=settings.max_audio_seconds,
                supported_extensions=list(SUPPORTED_EXTENSIONS),
            ),
            transcription=transcriber.status(),
        )

    @api.post("/features", response_model=AudioFeatures, responses=ERROR_RESPONSES, tags=["analysis"])
    def features(file: AudioFile, transcript: OptionalTranscript = None) -> AudioFeatures:
        """Measure acoustic features of one recording: energy, spectrum, MFCCs, pitch, pauses and a speaking-rate estimate."""
        return extract_features(read_audio(file), transcript, settings.pause_settings)

    @api.post("/transcribe", response_model=Transcription, responses=ERROR_RESPONSES, tags=["speech"])
    def transcribe(file: AudioFile, language: Language = None) -> Transcription:
        """Transcribe a recording locally, with word-level timestamps where the model provides them."""
        return run_transcription(read_audio(file), language)

    @api.post("/align", response_model=Alignment, responses=ERROR_RESPONSES, tags=["speech"])
    def align(file: AudioFile, transcript: OptionalTranscript = None, language: Language = None) -> Alignment:
        """
        Give each transcript word a start and end time. If no transcript is supplied, the recognised text is used.
        Words that cannot be matched are returned as `unaligned` with null times.
        """
        transcription = run_transcription(read_audio(file), language)
        try:
            return run_alignment(transcript, transcription)
        except SpeechError as error:
            raise _error(error.status_code, error.code, error.message) from error

    @api.post("/analyze", response_model=AnalyzeResponse, responses=ERROR_RESPONSES, tags=["analysis"])
    def analyze(file: AudioFile, transcript: OptionalTranscript = None, language: Language = None) -> AnalyzeResponse:
        """
        Main workflow: acoustic features, transcription and word alignment in one call.
        Acoustic features are always returned for valid audio. If transcription or alignment
        cannot run, that part is null and `components` says why.
        """
        audio = read_audio(file)
        feature_result = extract_features(audio, transcript, settings.pause_settings)

        transcription: Transcription | None = None
        alignment: Alignment | None = None
        try:
            transcription = transcriber.transcribe(audio.samples, audio.sample_rate, language)
            transcription_status = ComponentStatus(status="completed")
        except SpeechError as error:
            failed = error.status_code == 500
            transcription_status = ComponentStatus(
                status="failed" if failed else "unavailable", code=error.code, message=error.message
            )

        if transcription is None:
            alignment_status = ComponentStatus(
                status="unavailable",
                code="transcription_required",
                message="Alignment needs word timestamps from transcription, which did not run.",
            )
        else:
            try:
                alignment = run_alignment(transcript, transcription)
                alignment_status = ComponentStatus(status="completed")
            except SpeechError as error:
                alignment_status = ComponentStatus(status="unavailable", code=error.code, message=error.message)

        return AnalyzeResponse(
            components=Components(
                features=ComponentStatus(status="completed"),
                transcription=transcription_status,
                alignment=alignment_status,
            ),
            features=feature_result,
            transcription=transcription,
            alignment=alignment,
            limitations=[
                "No comparison with a baseline delivery and no flaw detection is performed yet.",
                "Acoustic features, transcription and alignment are reported separately; they are not yet combined into findings.",
            ],
        )

    def analyse_for_comparison(audio: LoadedAudio, transcript: str | None, language: str | None):
        """Features always; transcription and alignment when they can run. Never raises for speech problems."""
        features = extract_features(audio, transcript, settings.pause_settings)
        transcription: Transcription | None = None
        alignment: Alignment | None = None
        try:
            transcription = transcriber.transcribe(audio.samples, audio.sample_rate, language)
            transcription_status = ComponentStatus(status="completed")
        except SpeechError as error:
            transcription_status = ComponentStatus(
                status="failed" if error.status_code == 500 else "unavailable", code=error.code, message=error.message
            )
        if transcription is None:
            alignment_status = ComponentStatus(
                status="unavailable", code="transcription_required", message="Alignment needs transcription, which did not run."
            )
        elif not (transcript and transcript.strip()):
            alignment_status = ComponentStatus(
                status="unavailable", code="no_shared_transcript", message="There is no transcript to align this recording to."
            )
        else:
            try:
                alignment = align_transcript(transcript, transcription.words, source="supplied")
                alignment_status = ComponentStatus(status="completed")
            except SpeechError as error:
                alignment_status = ComponentStatus(status="unavailable", code=error.code, message=error.message)
        analysis = DeliveryAnalysis(features=features, transcription=transcription, alignment=alignment)
        summary = RecordingSummary(
            filename=features.audio.filename,
            duration_sec=features.audio.duration_sec,
            transcription=transcription_status,
            alignment=alignment_status,
        )
        return analysis, summary

    @api.post("/compare", response_model=CompareResponse, responses=ERROR_RESPONSES, tags=["analysis"])
    def compare(
        reference: Annotated[UploadFile, File(description="The delivery to compare against: WAV, FLAC, OGG or MP3.")],
        participant: Annotated[UploadFile, File(description="The delivery being examined: WAV, FLAC, OGG or MP3.")],
        transcript: OptionalTranscript = None,
        language: Language = None,
    ) -> CompareResponse:
        """
        Compare a participant recording with a reference recording of the same text.

        Returns measured differences only: overall measures, and gaps between words that are clearly longer or
        shorter than in the reference. It does not label anything a flaw or assign severity. Without a supplied
        transcript, both recordings are aligned to the text recognised in the reference.
        """
        reference_audio = read_audio(reference)
        participant_audio = read_audio(participant)

        supplied = bool(transcript and transcript.strip())
        source = "supplied"
        shared = transcript
        if not supplied:
            # Recognise the reference first so both recordings can be aligned to the same words.
            try:
                recognised = transcriber.transcribe(reference_audio.samples, reference_audio.sample_rate, language)
                shared, source = (recognised.text, "reference_transcription") if recognised.text.strip() else (None, "none")
            except SpeechError:
                shared, source = None, "none"

        reference_analysis, reference_summary = analyse_for_comparison(reference_audio, shared, language)
        participant_analysis, participant_summary = analyse_for_comparison(participant_audio, shared, language)
        return CompareResponse(
            transcript_source=source,
            reference=reference_summary,
            participant=participant_summary,
            comparison=compare_deliveries(reference_analysis, participant_analysis),
        )

    app.include_router(api)
    return app


app = create_app()
