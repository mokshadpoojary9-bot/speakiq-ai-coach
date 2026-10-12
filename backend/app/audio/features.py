"""Frame-level energy, spectral and cepstral features."""

from dataclasses import dataclass
from math import ceil

import librosa
import numpy as np

from .schemas import Energy, FrameSeries, Mfcc, Spectral, Waveform

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
# Frames more than this far below the loudest frame count as silence (Praat's default convention).
SILENCE_BELOW_PEAK_DB = 25.0


@dataclass(frozen=True)
class Frames:
    """Shared framing so every feature lines up on the same time grid."""

    sample_rate: int
    frame_length: int
    hop_length: int
    energy_db: np.ndarray
    silence_threshold_db: float | None  # None when the signal is too quiet to threshold

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


def compute_frames(samples: np.ndarray, sample_rate: int) -> Frames:
    frame_length = int(round(FRAME_LENGTH_SEC * sample_rate))
    hop_length = int(round(HOP_SEC * sample_rate))
    rms = librosa.feature.rms(y=samples, frame_length=frame_length, hop_length=hop_length, center=True)[0]
    energy_db = 20 * np.log10(np.maximum(rms, 1e-10))
    max_db = float(energy_db.max())
    threshold = max_db - SILENCE_BELOW_PEAK_DB if max_db > MIN_SIGNAL_DB else None
    return Frames(sample_rate, frame_length, hop_length, energy_db, threshold)


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
