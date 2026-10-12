"""Decoding and validation of uploaded audio. Audio is handled in memory and never written to disk."""

import io
from dataclasses import dataclass
from math import gcd
from pathlib import PurePath

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

SUPPORTED_EXTENSIONS = (".wav", ".flac", ".ogg", ".mp3")
ANALYSIS_SAMPLE_RATE = 16_000
MIN_DURATION_SEC = 0.3


class AudioError(Exception):
    """A problem with the uploaded audio that the client can fix."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


@dataclass(frozen=True)
class LoadedAudio:
    filename: str
    samples: np.ndarray  # mono float32 at `sample_rate`
    sample_rate: int
    original_sample_rate: int
    channels: int

    @property
    def duration_sec(self) -> float:
        return len(self.samples) / self.sample_rate


def load_audio(data: bytes, filename: str, *, max_duration_sec: float) -> LoadedAudio:
    """Decode to mono at the analysis sample rate, or raise AudioError."""
    name = PurePath(filename or "upload").name
    extension = PurePath(name).suffix.lower()
    supported = ", ".join(SUPPORTED_EXTENSIONS)
    if extension not in SUPPORTED_EXTENSIONS:
        raise AudioError(415, "unsupported_audio", f"Unsupported file type '{extension or 'none'}'. Supported: {supported}.")
    if not data:
        raise AudioError(400, "empty_upload", "The uploaded file is empty.")

    try:
        samples, sample_rate = sf.read(io.BytesIO(data), dtype="float32", always_2d=True)
    except Exception as error:  # libsndfile raises several types for malformed input
        raise AudioError(415, "undecodable_audio", f"The file could not be decoded as audio. Supported: {supported}.") from error

    channels = samples.shape[1]
    mono = samples.mean(axis=1)
    duration = len(mono) / sample_rate
    if duration < MIN_DURATION_SEC:
        raise AudioError(400, "audio_too_short", f"The recording is {duration:.2f} s long; at least {MIN_DURATION_SEC} s is needed.")
    if duration > max_duration_sec:
        raise AudioError(413, "audio_too_long", f"The recording is {duration:.0f} s long; the limit is {max_duration_sec:.0f} s.")
    if not np.all(np.isfinite(mono)):
        raise AudioError(400, "invalid_samples", "The file contains invalid sample values.")

    if sample_rate != ANALYSIS_SAMPLE_RATE:
        divisor = gcd(ANALYSIS_SAMPLE_RATE, sample_rate)
        mono = resample_poly(mono, ANALYSIS_SAMPLE_RATE // divisor, sample_rate // divisor)

    return LoadedAudio(
        filename=name,
        samples=np.ascontiguousarray(mono, dtype=np.float32),
        sample_rate=ANALYSIS_SAMPLE_RATE,
        original_sample_rate=int(sample_rate),
        channels=channels,
    )
