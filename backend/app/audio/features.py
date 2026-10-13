"""Frame-level energy, spectral and cepstral features."""

from dataclasses import dataclass
from math import ceil

import librosa
import numpy as np

from .loading import ClippingStats
from .schemas import Clipping, Energy, FrameSeries, Mfcc, Spectral, Waveform

FRAME_LENGTH_SEC = 0.025
HOP_SEC = 0.010
N_FFT = 512
WINDOW = "hann"
N_MFCC = 13
N_MELS = 40
MAX_SERIES_POINTS = 3000
WAVEFORM_BUCKETS = 1000
# Below this level the whole recording is treated as containing no usable speech signal.
MIN_SIGNAL_DB = -60.0


@dataclass(frozen=True)
class PauseSettings:
    """Tunable silence detection. Defaults were chosen against known inserted pauses in the dataset."""

    # In a quiet recording, frames this far below the speech level count as silence.
    silence_below_speech_db: float = 25.0
    # With background noise, silence is anything within this margin of the noise floor.
    noise_margin_db: float = 3.0
    min_pause_sec: float = 0.25
    # Speech level minus noise floor. Below the first, pauses are not reported at all;
    # below the second they are reported but flagged as unreliable.
    min_dynamic_range_db: float = 6.0
    low_confidence_range_db: float = 15.0


DEFAULT_PAUSE_SETTINGS = PauseSettings()


@dataclass(frozen=True)
class Frames:
    """Shared framing so every feature lines up on the same time grid."""

    sample_rate: int
    frame_length: int
    hop_length: int
    energy_db: np.ndarray
    silence_threshold_db: float | None  # None when speech cannot be separated from silence
    speech_level_db: float = 0.0  # 95th percentile of frame energy
    noise_floor_db: float = 0.0  # 5th percentile of frame energy
    threshold_rule: str = "none"  # "relative_to_speech", "noise_floor", or "none"

    @property
    def dynamic_range_db(self) -> float:
        return self.speech_level_db - self.noise_floor_db

    @property
    def hop_sec(self) -> float:
        return self.hop_length / self.sample_rate

    @property
    def active(self) -> np.ndarray:
        """Frames at or above the silence threshold; every frame if no threshold applies."""
        if self.silence_threshold_db is None:
            return np.ones(len(self.energy_db), dtype=bool)
        return self.energy_db >= self.silence_threshold_db


def to_series(values: np.ndarray, *, unit: str, hop_sec: float, start_sec: float = 0.0, digits: int = 2) -> FrameSeries:
    """Round, turn NaN into null, and thin out long series by keeping every n-th frame."""
    stride = max(1, ceil(len(values) / MAX_SERIES_POINTS))
    thinned = values[::stride]
    return FrameSeries(
        unit=unit,
        start_sec=round(start_sec, 4),
        hop_sec=round(hop_sec * stride, 4),
        values=[None if np.isnan(v) else round(float(v), digits) for v in thinned],
    )


def compute_frames(samples: np.ndarray, sample_rate: int, settings: PauseSettings = DEFAULT_PAUSE_SETTINGS) -> Frames:
    frame_length = int(round(FRAME_LENGTH_SEC * sample_rate))
    hop_length = int(round(HOP_SEC * sample_rate))
    rms = librosa.feature.rms(y=samples, frame_length=frame_length, hop_length=hop_length, center=True)[0]
    energy_db = 20 * np.log10(np.maximum(rms, 1e-10))
    # Percentiles rather than the extremes, so one click or one dropout does not set the levels.
    noise, speech = (float(v) for v in np.percentile(energy_db, [5, 95]))

    threshold: float | None = None
    rule = "none"
    if speech > MIN_SIGNAL_DB and speech - noise >= settings.min_dynamic_range_db:
        relative = speech - settings.silence_below_speech_db
        above_noise = noise + settings.noise_margin_db
        # A quiet background leaves the conventional relative threshold in charge. A noisy one
        # lifts the threshold just above the noise, which would otherwise never count as silence.
        threshold, rule = (above_noise, "noise_floor") if above_noise > relative else (relative, "relative_to_speech")
    return Frames(sample_rate, frame_length, hop_length, energy_db, threshold, speech, noise, rule)


def waveform(samples: np.ndarray, sample_rate: int) -> Waveform:
    buckets = min(WAVEFORM_BUCKETS, len(samples))
    edges = np.linspace(0, len(samples), buckets + 1, dtype=int)
    peaks = np.maximum.reduceat(np.abs(samples), edges[:-1])
    return Waveform(
        status="measured",
        method=f"Largest absolute sample amplitude in each of {buckets} equal time buckets.",
        bucket_sec=round(len(samples) / sample_rate / buckets, 5),
        peaks=[round(float(p), 4) for p in np.clip(peaks, 0, 1)],
    )


MIN_RUNS_FOR_DETECTION = 3
NEAR_FULL_SCALE_PEAK = 0.99


def clipping(stats: ClippingStats) -> Clipping:
    limitations = [
        "Only hard clipping is looked for. Soft clipping, limiting and distortion that rounds the peaks are not detected.",
        "Clipping that happened before the file was resampled, filtered or lossily encoded no longer has flat tops and can be missed.",
    ]
    at_full_scale = stats.peak >= NEAR_FULL_SCALE_PEAK
    if stats.flat_top_runs >= MIN_RUNS_FOR_DETECTION:
        verdict = "detected"
    elif stats.flat_top_runs > 0:
        verdict = "uncertain"
        limitations.insert(0, f"Uncertain: only {stats.flat_top_runs} flat-topped peak(s) were found, too few to be sure.")
    elif at_full_scale:
        verdict = "uncertain"
        limitations.insert(
            0,
            "Uncertain: the signal reaches full scale but its peaks are not flat. It may simply be normalised, "
            "or it may have been clipped before conversion.",
        )
    elif stats.lossy_source and stats.peak >= 0.9:
        verdict = "uncertain"
        limitations.insert(0, "Uncertain: this is a lossy format, which reshapes clipped peaks, and the level is high.")
    else:
        verdict = "not_detected"
    return Clipping(
        status="measured",
        method=(
            "Counts runs of 3 or more consecutive samples held at the peak level with an abrupt edge, per channel, "
            "on the decoded samples before mixing to mono or resampling. 3 or more such runs count as detected."
        ),
        verdict=verdict,
        peak_amplitude=round(stats.peak, 4),
        flat_top_runs=stats.flat_top_runs,
        longest_flat_run_samples=stats.longest_flat_run,
        flat_top_sample_fraction=round(stats.flat_top_fraction, 6),
        near_full_scale_fraction=round(stats.near_full_scale_fraction, 6),
        limitations=limitations,
    )


def energy(frames: Frames) -> Energy:
    db = frames.energy_db
    return Energy(
        status="measured",
        method=f"RMS amplitude over {FRAME_LENGTH_SEC * 1000:.0f} ms frames every {HOP_SEC * 1000:.0f} ms, in dB relative to full scale.",
        series=to_series(db, unit="dBFS", hop_sec=frames.hop_sec),
        mean_db=round(float(db.mean()), 2),
        max_db=round(float(db.max()), 2),
        noise_floor_db=round(float(np.percentile(db, 10)), 2),
        limitations=[
            "Levels depend on microphone distance and recording gain; they are not calibrated sound pressure levels."
        ],
    )


def spectral(samples: np.ndarray, frames: Frames) -> Spectral:
    magnitude = np.abs(
        librosa.stft(samples, n_fft=N_FFT, hop_length=frames.hop_length, win_length=frames.frame_length, window=WINDOW)
    )
    sr = frames.sample_rate
    centroid = librosa.feature.spectral_centroid(S=magnitude, sr=sr)[0]
    bandwidth = librosa.feature.spectral_bandwidth(S=magnitude, sr=sr)[0]
    rolloff = librosa.feature.spectral_rolloff(S=magnitude, sr=sr, roll_percent=0.85)[0]
    flatness = librosa.feature.spectral_flatness(S=magnitude)[0]
    zcr = librosa.feature.zero_crossing_rate(samples, frame_length=frames.frame_length, hop_length=frames.hop_length)[0]

    active = frames.active
    centroid_series = np.where(active, centroid, np.nan)
    return Spectral(
        status="measured",
        method=(
            f"Short-time Fourier transform ({N_FFT}-point FFT, {FRAME_LENGTH_SEC * 1000:.0f} ms {WINDOW} window, "
            f"{HOP_SEC * 1000:.0f} ms hop). Means are taken over non-silent frames."
        ),
        centroid=to_series(centroid_series, unit="Hz", hop_sec=frames.hop_sec, digits=1),
        mean_centroid_hz=round(float(centroid[active].mean()), 1),
        mean_bandwidth_hz=round(float(bandwidth[active].mean()), 1),
        mean_rolloff_hz=round(float(rolloff[active].mean()), 1),
        mean_flatness=round(float(flatness[active].mean()), 5),
        mean_zero_crossing_rate=round(float(zcr[active].mean()), 5),
        limitations=[
            f"Analysis is band-limited to {sr // 2} Hz because audio is resampled to {sr} Hz.",
            "Spectral measures describe the recording as a whole, including the microphone and room, not only the voice.",
        ],
    )


def mfcc(samples: np.ndarray, frames: Frames) -> Mfcc:
    coefficients = librosa.feature.mfcc(
        y=samples,
        sr=frames.sample_rate,
        n_mfcc=N_MFCC,
        n_fft=N_FFT,
        hop_length=frames.hop_length,
        win_length=frames.frame_length,
        window=WINDOW,
        n_mels=N_MELS,
    )
    active = coefficients[:, frames.active]
    return Mfcc(
        status="measured",
        method=(
            f"{N_MFCC} MFCCs from a {N_MELS}-band mel spectrogram on the same frames as the STFT. "
            "Reported as the mean and standard deviation of each coefficient over non-silent frames."
        ),
        n_mfcc=N_MFCC,
        mean=[round(float(v), 3) for v in active.mean(axis=1)],
        std=[round(float(v), 3) for v in active.std(axis=1)],
        limitations=["Per-frame coefficients are computed but only summary statistics are returned."],
    )
