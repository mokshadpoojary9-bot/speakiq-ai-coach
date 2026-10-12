"""Fundamental frequency (F0) tracking with Praat, falling back to librosa's pYIN."""

from dataclasses import dataclass

import numpy as np

from .features import to_series
from .schemas import Pitch

PITCH_FLOOR_HZ = 75.0
PITCH_CEILING_HZ = 500.0
TIME_STEP_SEC = 0.010


@dataclass(frozen=True)
class PitchTrack:
    """F0 per frame in Hz, NaN where unvoiced. `None` track fields mean pitch was not computed."""

    f0: np.ndarray | None
    start_sec: float
    hop_sec: float
    method: str

    def voiced_at(self, time_sec: float) -> bool | None:
        """Whether the frame nearest `time_sec` is voiced, or None when pitch is unavailable."""
        if self.f0 is None or len(self.f0) == 0:
            return None
        index = int(round((time_sec - self.start_sec) / self.hop_sec))
        if index < 0 or index >= len(self.f0):
            return False
        return not np.isnan(self.f0[index])


def _praat_track(samples: np.ndarray, sample_rate: int) -> PitchTrack:
    import parselmouth

    sound = parselmouth.Sound(samples.astype(np.float64), sampling_frequency=sample_rate)
    pitch = sound.to_pitch_ac(time_step=TIME_STEP_SEC, pitch_floor=PITCH_FLOOR_HZ, pitch_ceiling=PITCH_CEILING_HZ)
    f0 = pitch.selected_array["frequency"].astype(np.float64)
    f0[f0 == 0] = np.nan
    times = pitch.xs()
    return PitchTrack(
        f0=f0,
        start_sec=float(times[0]) if len(times) else 0.0,
        hop_sec=TIME_STEP_SEC,
        method=(
            f"Praat autocorrelation pitch tracking via Parselmouth, {PITCH_FLOOR_HZ:.0f}-{PITCH_CEILING_HZ:.0f} Hz, "
            f"{TIME_STEP_SEC * 1000:.0f} ms step."
        ),
    )


def _pyin_track(samples: np.ndarray, sample_rate: int) -> PitchTrack:
    import librosa

    hop_length = int(round(TIME_STEP_SEC * sample_rate))
    f0, _, _ = librosa.pyin(
        samples, fmin=PITCH_FLOOR_HZ, fmax=PITCH_CEILING_HZ, sr=sample_rate, frame_length=1024, hop_length=hop_length
    )
    return PitchTrack(
        f0=np.asarray(f0, dtype=np.float64),
        start_sec=0.0,
        hop_sec=hop_length / sample_rate,
        method=f"librosa pYIN pitch tracking, {PITCH_FLOOR_HZ:.0f}-{PITCH_CEILING_HZ:.0f} Hz (Praat was not available).",
    )


def track_pitch(samples: np.ndarray, sample_rate: int) -> PitchTrack:
    """Try each tracker in turn; return an empty track rather than raising if none works."""
    errors: list[str] = []
    for tracker in (_praat_track, _pyin_track):
        try:
            return tracker(samples, sample_rate)
        except Exception as error:  # a missing or failing optional library must not fail the analysis
            errors.append(f"{tracker.__name__}: {type(error).__name__}")
    return PitchTrack(f0=None, start_sec=0.0, hop_sec=TIME_STEP_SEC, method="; ".join(errors))


def pitch(track: PitchTrack) -> Pitch:
    if track.f0 is None:
        return Pitch(
            status="unavailable",
            method="No pitch tracker could be run.",
            limitations=[f"Pitch was not computed ({track.method})."],
        )

    voiced = track.f0[~np.isnan(track.f0)]
    limitations = [
        f"F0 outside {PITCH_FLOOR_HZ:.0f}-{PITCH_CEILING_HZ:.0f} Hz is not tracked.",
        "Octave errors are possible in creaky or noisy speech.",
        "Values are in Hz and are not normalised to the speaker.",
    ]
    result = Pitch(
        status="measured",
        method=track.method,
        series=to_series(track.f0, unit="Hz", hop_sec=track.hop_sec, start_sec=track.start_sec, digits=1),
        voiced_fraction=round(len(voiced) / len(track.f0), 3) if len(track.f0) else 0.0,
        limitations=limitations,
    )
    if len(voiced) == 0:
        result.limitations.insert(0, "No voiced frames were found, so no pitch statistics are reported.")
        return result

    low, high = np.percentile(voiced, [5, 95])
    result.median_hz = round(float(np.median(voiced)), 1)
    result.mean_hz = round(float(voiced.mean()), 1)
    result.min_hz = round(float(voiced.min()), 1)
    result.max_hz = round(float(voiced.max()), 1)
    result.range_semitones = round(float(12 * np.log2(high / low)), 2)
    return result
