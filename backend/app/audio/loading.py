"""Decoding and validation of uploaded audio. Audio is handled in memory and never written to disk."""

import io
from dataclasses import dataclass
from math import gcd
from pathlib import PurePath

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

SUPPORTED_EXTENSIONS = (".wav", ".flac", ".ogg", ".mp3")
LOSSY_EXTENSIONS = (".ogg", ".mp3")
ANALYSIS_SAMPLE_RATE = 16_000
MIN_DURATION_SEC = 0.3


class AudioError(Exception):
    """A problem with the uploaded audio that the client can fix."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


MIN_FLAT_RUN_SAMPLES = 3
FULL_SCALE_FRACTION = 0.999
PCM16_STEP = 1 / 32768


@dataclass(frozen=True)
class ClippingStats:
    """Evidence of clipping, measured on the decoded samples before any mixing or resampling."""

    peak: float = 0.0
    flat_top_runs: int = 0
    longest_flat_run: int = 0
    flat_top_fraction: float = 0.0
    near_full_scale_fraction: float = 0.0
    lossy_source: bool = False


def measure_clipping(samples: np.ndarray, *, lossy_source: bool = False) -> ClippingStats:
    """Count flat-topped peaks in `samples` (frames x channels).

    A clipped waveform rises steeply and is then held at one value. A clean waveform, even one
    that touches full scale, curves over its peak. So a run only counts when several samples sit
    at the peak level and the step into or out of the run is abrupt.
    """
    peak = float(np.abs(samples).max()) if samples.size else 0.0
    if peak < 1e-4:
        return ClippingStats(lossy_source=lossy_source)
    tolerance = max(PCM16_STEP, peak * 1e-4)
    runs = longest = flat_samples = 0
    for channel in samples.T:
        at_peak = np.abs(channel) >= peak - tolerance
        edges = np.flatnonzero(np.diff(np.concatenate(([False], at_peak, [False])).astype(np.int8)))
        for start, end in zip(edges[0::2], edges[1::2]):
            length = int(end - start)
            if length < MIN_FLAT_RUN_SAMPLES:
                continue
            step_in = abs(channel[start] - channel[start - 1]) if start > 0 else 0.0
            step_out = abs(channel[end - 1] - channel[end]) if end < len(channel) else 0.0
            if max(step_in, step_out) > 8 * tolerance:
                runs += 1
                flat_samples += length
                longest = max(longest, length)
    return ClippingStats(
        peak=peak,
        flat_top_runs=runs,
        longest_flat_run=longest,
        flat_top_fraction=flat_samples / samples.size,
        near_full_scale_fraction=float(np.mean(np.abs(samples) >= FULL_SCALE_FRACTION)),
        lossy_source=lossy_source,
    )


@dataclass(frozen=True)
class LoadedAudio:
    filename: str
    samples: np.ndarray  # mono float32 at `sample_rate`
    sample_rate: int
    original_sample_rate: int
    channels: int
    clipping: ClippingStats = ClippingStats()

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

    clipping = measure_clipping(samples, lossy_source=extension in LOSSY_EXTENSIONS)

    if sample_rate != ANALYSIS_SAMPLE_RATE:
        divisor = gcd(ANALYSIS_SAMPLE_RATE, sample_rate)
        mono = resample_poly(mono, ANALYSIS_SAMPLE_RATE // divisor, sample_rate // divisor)

    return LoadedAudio(
        filename=name,
        samples=np.ascontiguousarray(mono, dtype=np.float32),
        sample_rate=ANALYSIS_SAMPLE_RATE,
        original_sample_rate=int(sample_rate),
        channels=channels,
        clipping=clipping,
    )
