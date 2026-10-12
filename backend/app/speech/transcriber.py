"""Local speech transcription with faster-whisper. The model is loaded on first use."""

import importlib.util
import threading
from collections.abc import Callable
from typing import Any, Protocol

import numpy as np

from ..config import Settings
from .schemas import RecognizedWord, Segment, Transcription, TranscriptionEngineStatus

ENGINE = "faster-whisper"


class SpeechError(Exception):
    """A speech component could not do its job. `message` is safe to show to the client."""

    def __init__(self, code: str, message: str, status_code: int = 503) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class Transcriber(Protocol):
    def status(self) -> TranscriptionEngineStatus: ...

    def transcribe(self, samples: np.ndarray, sample_rate: int, language: str | None = None) -> Transcription: ...


def _load_whisper_model(settings: Settings) -> Any:
    from faster_whisper import WhisperModel

    return WhisperModel(
        settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
        download_root=settings.whisper_download_root,
        # None lets huggingface_hub work anonymously, which is enough for the public default models.
        use_auth_token=settings.hf_token,
    )


_AUTH_MARKERS = ("401", "403", "gated", "unauthorized", "forbidden", "repository not found", "invalid username or password")
_NETWORK_MARKERS = ("connection", "timed out", "timeout", "offline", "getaddrinfo", "localentrynotfound", "resolve")


def _classify_load_failure(error: Exception, settings: Settings) -> SpeechError:
    # Only the exception type and message class are used; the message itself is never echoed,
    # so nothing from the environment can leak into a response.
    text = f"{type(error).__name__} {error}".lower()
    model = settings.whisper_model
    if any(marker in text for marker in _AUTH_MARKERS):
        if settings.hf_token:
            return SpeechError(
                "hf_auth_rejected",
                f"Hugging Face rejected the configured HF_TOKEN for model '{model}'. "
                "Check that the token is valid and has access to this model.",
            )
        return SpeechError(
            "hf_auth_required",
            f"Model '{model}' could not be downloaded without authentication. Either set HF_TOKEN in backend/.env, "
            "or set WHISPER_MODEL to a public model such as 'base' or 'small', which need no token.",
        )
    if any(marker in text for marker in _NETWORK_MARKERS):
        return SpeechError(
            "model_download_failed",
            f"Model '{model}' is not downloaded yet and could not be fetched ({type(error).__name__}). "
            "Check the internet connection, or run `python -m app.speech.prefetch` once while online.",
        )
    return SpeechError(
        "model_load_failed",
        f"Model '{model}' could not be loaded ({type(error).__name__}). "
        "Check WHISPER_MODEL, WHISPER_DEVICE and WHISPER_COMPUTE_TYPE in backend/.env.",
    )


class FasterWhisperTranscriber:
    def __init__(self, settings: Settings, model_loader: Callable[[Settings], Any] = _load_whisper_model) -> None:
        self._settings = settings
        self._model_loader = model_loader
        self._model: Any = None
        self._lock = threading.Lock()

    def status(self) -> TranscriptionEngineStatus:
        return TranscriptionEngineStatus(
            engine=ENGINE,
            dependency_installed=importlib.util.find_spec("faster_whisper") is not None,
            model=self._settings.whisper_model,
            device=self._settings.whisper_device,
            compute_type=self._settings.whisper_compute_type,
            model_loaded=self._model is not None,
            hf_token_configured=bool(self._settings.hf_token),
        )

    def _get_model(self) -> Any:
        with self._lock:
            if self._model is None:
                try:
                    self._model = self._model_loader(self._settings)
                except ImportError as error:
                    raise SpeechError(
                        "missing_dependency",
                        "Transcription needs the 'faster-whisper' package. "
                        "Install it with `pip install -r requirements.txt` in backend/.",
                    ) from error
                except Exception as error:
                    raise _classify_load_failure(error, self._settings) from None
            return self._model

    def transcribe(self, samples: np.ndarray, sample_rate: int, language: str | None = None) -> Transcription:
        if sample_rate != 16_000:
            raise SpeechError("transcription_failed", "Internal error: audio must be 16 kHz mono.", 500)
        model = self._get_model()
        duration = len(samples) / sample_rate
        try:
            segments_iter, info = model.transcribe(
                samples,
                language=language or self._settings.whisper_language,
                word_timestamps=True,
                beam_size=5,
                condition_on_previous_text=False,
            )
            raw_segments = list(segments_iter)  # decoding happens while iterating
        except Exception as error:
            raise SpeechError(
                "transcription_failed", f"The transcription model failed on this audio ({type(error).__name__}).", 500
            ) from error

        def span(start: float, end: float) -> tuple[float, float]:
            start = min(max(0.0, float(start)), duration)
            return round(start, 3), round(min(max(start, float(end)), duration), 3)

        segments: list[Segment] = []
        words: list[RecognizedWord] = []
        segments_have_words = True
        for raw in raw_segments:
            text = raw.text.strip()
            if not text:
                continue
            start, end = span(raw.start, raw.end)
            segments.append(Segment(start=start, end=end, text=text))
            raw_words = getattr(raw, "words", None)
            if not raw_words:
                segments_have_words = False
                continue
            for raw_word in raw_words:
                token = raw_word.word.strip()
                if not token:
                    continue
                w_start, w_end = span(raw_word.start, raw_word.end)
                probability = getattr(raw_word, "probability", None)
                words.append(
                    RecognizedWord(
                        word=token,
                        start=w_start,
                        end=w_end,
                        probability=None if probability is None else round(float(probability), 3),
                    )
                )

        has_words = bool(words) and segments_have_words
        limitations = [
            "The text is the model's best guess and can contain recognition errors, especially for names, numbers and unclear speech.",
            "Word times come from the model's attention weights and are typically accurate to around a tenth of a second, not to the phoneme.",
            "Word probabilities are the model's own scores, not calibrated accuracy.",
        ]
        if segments and not has_words:
            limitations.insert(0, "The model returned text without word-level timestamps for at least one segment.")
        language_probability = getattr(info, "language_probability", None)
        return Transcription(
            status="completed" if segments else "no_speech",
            text=" ".join(segment.text for segment in segments),
            language=getattr(info, "language", None),
            language_probability=None if language_probability is None else round(float(language_probability), 3),
            duration_sec=round(duration, 3),
            engine=ENGINE,
            model=self._settings.whisper_model,
            segments=segments,
            words=words if has_words else [],
            word_timestamps="available" if has_words else "unavailable",
            limitations=limitations if segments else ["No speech was recognised in this recording."],
        )
