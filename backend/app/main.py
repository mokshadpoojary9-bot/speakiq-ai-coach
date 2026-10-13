from typing import Annotated, Literal

from fastapi import APIRouter, FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from . import __version__
from .audio import SUPPORTED_EXTENSIONS, AudioError, AudioFeatures, LoadedAudio, extract_features, load_audio
from .comparison import ComparisonResult, DeliveryAnalysis, compare_deliveries
from .config import Settings, get_settings
from .detection.coaching import CoachingTip, build_coaching
from .detection import AlignmentStatus, DetectionSettings, Finding, RuleReport, SignalQuality, run_detection
from .speech import (
    Alignment,
    FasterWhisperTranscriber,
    SpeechError,
    Transcriber,
    Transcription,
    TranscriptionEngineStatus,
    align_transcript,
)
from .speech.alignment import normalize

MAX_TRANSCRIPT_CHARS = 20_000

DESCRIPTION = """
Evidence-first speech delivery analysis. All times are in seconds.

Uploads are processed in memory and are not stored. Errors return
`{"detail": {"code": "...", "message": "..."}}` with a stable `code`.

Transcription runs locally with faster-whisper. The model is downloaded on first use,
so the first request to a transcription route can take a while.

`POST /api/analyze` is the main route. Send a participant recording, and optionally a reference
recording of the same text, to get measurements, signal-quality checks and temporal findings.
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


class TranscriptInfo(BaseModel):
    """Where a transcript came from and what is known about its review.

    The API cannot check that anyone compared a transcript with the audio, so `human_verified` is always
    false. `review_status` records only what the sender stated about a transcript they supplied.
    """

    # user_provided: sent with the request. machine_generated: recognised from this recording. none: no text available.
    source: Literal["user_provided", "machine_generated", "none"]
    # user_attested: the sender stated they checked their transcript against the recording. Not verified by the API.
    review_status: Literal["not_reviewed", "user_attested"] = "not_reviewed"
    human_verified: Literal[False] = False
    text: str | None = None


class SharedTranscript(TranscriptInfo):
    # Which text both recordings were aligned to.
    origin: Literal["participant_transcript", "reference_transcript", "reference_recognition"]


class Transcripts(BaseModel):
    participant: TranscriptInfo
    reference: TranscriptInfo | None = None
    shared_for_comparison: SharedTranscript | None = Field(
        default=None, description="The text both recordings were aligned to, when a comparison was made."
    )


class ReferenceSummary(BaseModel):
    filename: str
    duration_sec: float
    transcription: ComponentStatus
    alignment: ComponentStatus
    signal_quality: SignalQuality


class AnalyzeResponse(BaseModel):
    is_demo: Literal[False] = False
    # completed: checked, with findings. completed_no_findings: checked, nothing crossed a threshold.
    # partial: part of the analysis could not run or the audio is unusable; see limitations and rules.
    status: Literal["completed", "completed_no_findings", "partial"]
    components: Components
    signal_quality: SignalQuality
    features: AudioFeatures
    transcription: Transcription | None = Field(description="Null when transcription could not run; see components.")
    alignment: Alignment | None = Field(description="Null when alignment could not run; see components.")
    transcripts: Transcripts
    reference: ReferenceSummary | None = Field(description="Null when no reference recording was sent.")
    alignment_status: AlignmentStatus
    comparison: ComparisonResult | None = Field(description="Measured differences from the reference, when one could be used.")
    findings: list[Finding]
    rules: list[RuleReport]
    coaching: list[CoachingTip] = Field(description="Rule-based tips, one per kind of finding. Empty when there are no findings.")
    settings: DetectionSettings
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

COMPLETED = ComponentStatus(status="completed")


def _same_words(a: str, b: str) -> bool:
    def words(text: str) -> list[str]:
        return [key for key in (normalize(token) for token in text.split()) if key]

    return words(a) == words(b)


def create_app(settings: Settings | None = None, transcriber: Transcriber | None = None) -> FastAPI:
    settings = settings or get_settings()
    transcriber = transcriber or FasterWhisperTranscriber(settings)
    detection_settings = DetectionSettings()
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

    @app.exception_handler(Exception)
    async def processing_failure(_: Request, error: Exception) -> JSONResponse:
        # Never send exception text, paths or a stack trace to the client. The type alone goes to the server log.
        print(f"Unhandled {type(error).__name__} while processing a request")
        detail = ErrorDetail(code="processing_failed", message="The analysis failed unexpectedly. Nothing was stored. Please try again.")
        return JSONResponse(status_code=500, content={"detail": detail.model_dump()})

    api = APIRouter(prefix="/api")

    def read_audio(file: UploadFile) -> LoadedAudio:
        data = file.file.read(settings.max_upload_bytes + 1)
        if len(data) > settings.max_upload_bytes:
            raise _error(413, "upload_too_large", f"The file is larger than the {settings.max_upload_mb:g} MB limit.")
        try:
            return load_audio(data, file.filename or "upload", max_duration_sec=settings.max_audio_seconds)
        except AudioError as error:
            raise _error(error.status_code, error.code, error.message) from error

    def measure(audio: LoadedAudio, transcript: str | None = None) -> AudioFeatures:
        return extract_features(audio, transcript, settings.pause_settings, settings.pitch_settings)

    def run_transcription(audio: LoadedAudio, language: str | None) -> Transcription:
        try:
            return transcriber.transcribe(audio.samples, audio.sample_rate, language)
        except SpeechError as error:
            raise _error(error.status_code, error.code, error.message) from error

    def try_transcription(audio: LoadedAudio, language: str | None) -> tuple[Transcription | None, ComponentStatus]:
        """Transcription that reports a problem instead of failing the request."""
        try:
            return transcriber.transcribe(audio.samples, audio.sample_rate, language), COMPLETED
        except SpeechError as error:
            status = "failed" if error.status_code == 500 else "unavailable"
            return None, ComponentStatus(status=status, code=error.code, message=error.message)

    def try_alignment(text: str | None, transcription: Transcription | None, source: str) -> tuple[Alignment | None, ComponentStatus]:
        if transcription is None:
            return None, ComponentStatus(
                status="unavailable", code="transcription_required", message="Alignment needs word timestamps from transcription, which did not run."
            )
        if not (text and text.strip()):
            return None, ComponentStatus(status="unavailable", code="no_transcript", message="There is no transcript to align this recording to.")
        try:
            return align_transcript(text, transcription.words, source=source), COMPLETED
        except SpeechError as error:
            return None, ComponentStatus(status="unavailable", code=error.code, message=error.message)

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
        return measure(read_audio(file), transcript)

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
    def analyze(
        file: Annotated[UploadFile, File(description="The participant recording: WAV, FLAC, OGG or MP3.")],
        reference: Annotated[
            UploadFile | None, File(description="Optional reference recording of the same text, to compare against.")
        ] = None,
        transcript: Annotated[
            str | None, Form(max_length=MAX_TRANSCRIPT_CHARS, description="Optional text the participant was delivering.")
        ] = None,
        reference_transcript: Annotated[
            str | None, Form(max_length=MAX_TRANSCRIPT_CHARS, description="Optional text of the reference recording.")
        ] = None,
        transcript_reviewed: Annotated[
            bool, Form(description="Set if you have checked `transcript` against the participant recording. Recorded as your statement, not verified.")
        ] = False,
        reference_transcript_reviewed: Annotated[
            bool, Form(description="Set if you have checked `reference_transcript` against the reference recording.")
        ] = False,
        language: Language = None,
    ) -> AnalyzeResponse:
        """
        Main workflow. Measures the participant recording, transcribes and aligns it, checks signal quality, and
        applies the delivery rules. With a reference recording of the same text, rules compare the two over the
        words recognised in both; without one, only the rules that need no reference run.

        `findings` lists what crossed a threshold, each with its interval in the participant audio and the measured
        evidence. `rules` says for every rule whether it triggered, did not trigger, or was withheld and why, so an
        empty `findings` list is never ambiguous. Invalid uploads return an error; everything else returns 200 with
        `status` set to `completed`, `completed_no_findings` or `partial`.
        """
        audio = read_audio(file)
        reference_audio = read_audio(reference) if reference is not None and reference.filename else None
        own_text = transcript.strip() if transcript and transcript.strip() else None
        reference_text = reference_transcript.strip() if reference_transcript and reference_transcript.strip() else None

        feature_result = measure(audio, own_text)
        transcription, transcription_status = try_transcription(audio, language)

        def attested(flag: bool) -> str:
            return "user_attested" if flag else "not_reviewed"

        withheld: str | None = None
        shared: SharedTranscript | None = None
        reference_analysis: DeliveryAnalysis | None = None
        reference_summary: ReferenceSummary | None = None
        reference_info: TranscriptInfo | None = None
        # What this recording's own transcript is: the supplied text, or else what was recognised in it.
        recognised_here = transcription.text.strip() if transcription else ""
        participant_info = (
            TranscriptInfo(source="user_provided", review_status=attested(transcript_reviewed), text=own_text)
            if own_text
            else TranscriptInfo(source="machine_generated", text=recognised_here)
            if recognised_here
            else TranscriptInfo(source="none")
        )
        # The text this recording is aligned to. With a reference it is the shared text, which may come from the reference.
        alignment_text, alignment_source = participant_info.text, "supplied" if own_text else "transcribed"

        if reference_audio is not None:
            reference_features = measure(reference_audio, reference_text)
            reference_transcription, reference_transcription_status = try_transcription(reference_audio, language)
            recognised = reference_transcription.text.strip() if reference_transcription else ""
            reference_info = (
                TranscriptInfo(source="user_provided", review_status=attested(reference_transcript_reviewed), text=reference_text)
                if reference_text
                else TranscriptInfo(source="machine_generated", text=recognised)
                if recognised
                else TranscriptInfo(source="none")
            )
            if own_text and reference_text and not _same_words(own_text, reference_text):
                withheld = "The participant and reference transcripts contain different words, so the recordings are not compared word for word."
            elif own_text:
                shared = SharedTranscript(source="user_provided", review_status=attested(transcript_reviewed), text=own_text, origin="participant_transcript")
            elif reference_text:
                shared = SharedTranscript(
                    source="user_provided", review_status=attested(reference_transcript_reviewed), text=reference_text, origin="reference_transcript"
                )
            elif recognised:
                shared = SharedTranscript(source="machine_generated", text=recognised, origin="reference_recognition")
            else:
                withheld = "No transcript was supplied and none could be recognised in the reference recording."
            if shared:
                alignment_text, alignment_source = shared.text, "supplied"
            reference_alignment, reference_alignment_status = try_alignment(
                shared.text if shared else reference_text or recognised or None, reference_transcription, "supplied"
            )
            reference_analysis = DeliveryAnalysis(
                features=reference_features, transcription=reference_transcription, alignment=reference_alignment
            )

        alignment, alignment_component = try_alignment(alignment_text, transcription, alignment_source)
        participant_analysis = DeliveryAnalysis(features=feature_result, transcription=transcription, alignment=alignment)

        detection = run_detection(
            participant_analysis,
            reference_analysis,
            transcript_source=shared.source if shared else participant_info.source,
            comparison_withheld_reason=withheld,
            settings=detection_settings,
        )
        comparison = (
            compare_deliveries(reference_analysis, participant_analysis)
            if reference_analysis is not None and detection.alignment_status.status == "aligned"
            else None
        )
        if reference_analysis is not None:
            reference_summary = ReferenceSummary(
                filename=reference_analysis.features.audio.filename,
                duration_sec=reference_analysis.features.audio.duration_sec,
                transcription=reference_transcription_status,
                alignment=reference_alignment_status,
                signal_quality=run_detection(reference_analysis, settings=detection_settings).signal_quality,
            )

        incomplete = (
            not detection.signal_quality.usable
            or transcription_status.status != "completed"
            or alignment_component.status != "completed"
            or (reference_analysis is not None and detection.alignment_status.status != "aligned")
        )
        status = "partial" if incomplete else "completed" if detection.findings else "completed_no_findings"
        limitations = list(detection.limitations)
        if transcription_status.status != "completed":
            limitations.insert(0, f"Transcription did not run ({transcription_status.message}) Rules that need recognised words were withheld.")
        return AnalyzeResponse(
            status=status,
            components=Components(features=COMPLETED, transcription=transcription_status, alignment=alignment_component),
            signal_quality=detection.signal_quality,
            features=feature_result,
            transcription=transcription,
            alignment=alignment,
            transcripts=Transcripts(
                participant=participant_info,
                reference=reference_info,
                shared_for_comparison=shared if detection.alignment_status.status == "aligned" else None,
            ),
            reference=reference_summary,
            alignment_status=detection.alignment_status,
            comparison=comparison,
            findings=detection.findings,
            rules=detection.rules,
            coaching=build_coaching(detection.findings),
            settings=detection_settings,
            limitations=limitations,
        )

    def analyse_for_comparison(audio: LoadedAudio, transcript: str | None, language: str | None):
        """Features always; transcription and alignment when they can run. Never raises for speech problems."""
        transcription, transcription_status = try_transcription(audio, language)
        alignment, alignment_status = try_alignment(transcript, transcription, "supplied")
        if alignment_status.code == "no_transcript":
            alignment_status = ComponentStatus(
                status="unavailable", code="no_shared_transcript", message="There is no transcript to align this recording to."
            )
        analysis = DeliveryAnalysis(features=measure(audio, transcript), transcription=transcription, alignment=alignment)
        summary = RecordingSummary(
            filename=analysis.features.audio.filename,
            duration_sec=analysis.features.audio.duration_sec,
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
        Raw measured differences between two recordings of the same text, without rules or findings.
        `POST /api/analyze` with a `reference` file returns these too, plus signal quality and findings.
        Without a supplied transcript, both recordings are aligned to the text recognised in the reference.
        """
        reference_audio = read_audio(reference)
        participant_audio = read_audio(participant)

        supplied = bool(transcript and transcript.strip())
        source = "supplied"
        shared = transcript
        if not supplied:
            # Recognise the reference first so both recordings can be aligned to the same words.
            recognised, _ = try_transcription(reference_audio, language)
            shared, source = (
                (recognised.text, "reference_transcription") if recognised and recognised.text.strip() else (None, "none")
            )

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
