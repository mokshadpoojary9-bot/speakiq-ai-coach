"""Fundamental frequency (F0) tracking with Praat, falling back to librosa's pYIN.

Tracking runs twice. A first pass over a wide range finds roughly where this speaker's voice
sits; the second pass searches only around it (De Looze and Hirst, 2008: 0.75 x the first
quartile to 1.5 x the third). A fixed wide range lets the tracker jump an octave up or down,
which is what made low-pitched voices measure wildly different ranges from one take to the next.

A third pass with the lower limit nudged upwards checks stability. A voice the tracker follows
well gives the same answer; a creaky or very low voice near the limit of what can be tracked
does not, and is then reported as low reliability rather than as a confident number.

Choosing the range from only the opening seconds was tried and rejected: on the dataset it withheld
more recordings (39 or 40 of 87 instead of 24) and, with 3 s, gave 3 false readings, because the
opening seconds often miss notes the speaker reaches later. See `python -m app.audio.evaluate_pitch`.
"""

from dataclasses import dataclass

import numpy as np

from .features import to_series
from .schemas import Pitch

TIME_STEP_SEC = 0.010
FLOOR_FACTOR = 0.75
CEILING_FACTOR = 1.5
# Fewer voiced frames than this is too little to place a speaker's range.
MIN_VOICED_FRAMES = 20
# A leap this large between frames 10 ms apart is not something a voice does.
OCTAVE_JUMP_SEMITONES = 8.0
MAX_OCTAVE_JUMP_FRACTION = 0.01
EDGE_MARGIN = 1.1
# Stability check: raise the lower search limit by this factor and see whether the result holds.
STABILITY_FLOOR_NUDGE = 1.15
MAX_RANGE_SENSITIVITY_SEMITONES = 1.0
MAX_VOICED_CHANGE_FRACTION = 0.10


@dataclass(frozen=True)
class PitchSettings:
    """The widest range the tracker may search, in Hz. Lower `min_hz` for exceptionally low voices."""

    min_hz: float = 50.0
    max_hz: float = 600.0

    def __post_init__(self) -> None:
        if not 20 <= self.min_hz < self.max_hz <= 2000:
            raise ValueError("pitch range must satisfy 20 <= min_hz < max_hz <= 2000")


DEFAULT_PITCH_SETTINGS = PitchSettings()


@dataclass(frozen=True)
class PitchTrack:
    """F0 per frame in Hz, NaN where unvoiced. `f0` is None when pitch was not computed."""

    f0: np.ndarray | None
    start_sec: float
    hop_sec: float
    method: str
    floor_hz: float = DEFAULT_PITCH_SETTINGS.min_hz
    ceiling_hz: float = DEFAULT_PITCH_SETTINGS.max_hz
    adapted: bool = False
    settings: PitchSettings = DEFAULT_PITCH_SETTINGS
    # How much the 5th-95th percentile range moves, and what share of voiced frames change, when the
    # lower limit is nudged. None when the check did not run.
    range_sensitivity_semitones: float | None = None
    voiced_change_fraction: float | None = None

    def voiced_at(self, time_sec: float) -> bool | None:
        """Whether the frame nearest `time_sec` is voiced, or None when pitch is unavailable."""
        if self.f0 is None or len(self.f0) == 0:
            return None
        index = int(round((time_sec - self.start_sec) / self.hop_sec))
        if index < 0 or index >= len(self.f0):
            return False
        return not np.isnan(self.f0[index])


def speaker_range(f0: np.ndarray, settings: PitchSettings = DEFAULT_PITCH_SETTINGS) -> tuple[float, float] | None:
    """Search limits for the second pass, or None if the first pass found too little voicing."""
    voiced = f0[~np.isnan(f0)]
    if len(voiced) < MIN_VOICED_FRAMES:
        return None
    q1, q3 = np.percentile(voiced, [25, 75])
    floor = max(settings.min_hz, FLOOR_FACTOR * float(q1))
    ceiling = min(settings.max_hz, CEILING_FACTOR * float(q3))
    return (floor, ceiling) if ceiling > floor else None


def _range_semitones(f0: np.ndarray) -> tuple[float | None, int]:
    voiced = f0[~np.isnan(f0)]
    if len(voiced) < MIN_VOICED_FRAMES:
        return None, len(voiced)
    low, high = np.percentile(voiced, [5, 95])
    return float(12 * np.log2(high / low)), len(voiced)


def _praat_pass(samples: np.ndarray, sample_rate: int, floor: float, ceiling: float) -> tuple[np.ndarray, float]:
    import parselmouth

    sound = parselmouth.Sound(samples.astype(np.float64), sampling_frequency=sample_rate)
    pitch = sound.to_pitch_ac(time_step=TIME_STEP_SEC, pitch_floor=floor, pitch_ceiling=ceiling)
    f0 = pitch.selected_array["frequency"].astype(np.float64)
    f0[f0 == 0] = np.nan
    times = pitch.xs()
    return f0, float(times[0]) if len(times) else 0.0


def _pyin_pass(samples: np.ndarray, sample_rate: int, floor: float, ceiling: float) -> tuple[np.ndarray, float]:
    import librosa

    hop_length = int(round(TIME_STEP_SEC * sample_rate))
    f0, _, _ = librosa.pyin(samples, fmin=floor, fmax=ceiling, sr=sample_rate, frame_length=2048, hop_length=hop_length)
    return np.asarray(f0, dtype=np.float64), 0.0


def _two_pass(run_pass, samples: np.ndarray, sample_rate: int, name: str, settings: PitchSettings) -> PitchTrack:
    f0, start = run_pass(samples, sample_rate, settings.min_hz, settings.max_hz)
    limits = speaker_range(f0, settings)
    sensitivity = voiced_change = None
    if limits is not None:
        f0, start = run_pass(samples, sample_rate, *limits)
        nudged_floor = limits[0] * STABILITY_FLOOR_NUDGE
        if nudged_floor < limits[1]:
            nudged, _ = run_pass(samples, sample_rate, nudged_floor, limits[1])
            (base_range, base_count), (nudged_range, nudged_count) = _range_semitones(f0), _range_semitones(nudged)
            if base_range is not None and nudged_range is not None:
                sensitivity = abs(base_range - nudged_range)
            if base_count:
                voiced_change = abs(base_count - nudged_count) / base_count
    floor, ceiling = limits or (settings.min_hz, settings.max_hz)
    how = (
        f"second pass limited to this speaker's range, {floor:.0f}-{ceiling:.0f} Hz"
        if limits
        else "single pass; too little voicing to adapt the range to the speaker"
    )
    return PitchTrack(
        f0=f0,
        start_sec=start,
        hop_sec=TIME_STEP_SEC,
        method=f"{name}, {TIME_STEP_SEC * 1000:.0f} ms step. First pass {settings.min_hz:.0f}-{settings.max_hz:.0f} Hz; {how}.",
        floor_hz=floor,
        ceiling_hz=ceiling,
        adapted=limits is not None,
        settings=settings,
        range_sensitivity_semitones=sensitivity,
        voiced_change_fraction=voiced_change,
    )


def _praat_track(samples: np.ndarray, sample_rate: int, settings: PitchSettings) -> PitchTrack:
    return _two_pass(_praat_pass, samples, sample_rate, "Praat autocorrelation pitch tracking via Parselmouth", settings)


def _pyin_track(samples: np.ndarray, sample_rate: int, settings: PitchSettings) -> PitchTrack:
    return _two_pass(_pyin_pass, samples, sample_rate, "librosa pYIN pitch tracking (Praat was not available)", settings)


def track_pitch(samples: np.ndarray, sample_rate: int, settings: PitchSettings = DEFAULT_PITCH_SETTINGS) -> PitchTrack:
    """Try each tracker in turn; return an empty track rather than raising if none works."""
    errors: list[str] = []
    for tracker in (_praat_track, _pyin_track):
        try:
            return tracker(samples, sample_rate, settings)
        except Exception as error:  # a missing or failing optional library must not fail the analysis
            errors.append(f"{tracker.__name__}: {type(error).__name__}")
    return PitchTrack(f0=None, start_sec=0.0, hop_sec=TIME_STEP_SEC, method="; ".join(errors), settings=settings)


def octave_jump_fraction(f0: np.ndarray) -> float:
    """Share of consecutive voiced frame pairs whose pitch leaps by more than OCTAVE_JUMP_SEMITONES."""
    both = ~np.isnan(f0[:-1]) & ~np.isnan(f0[1:])
    if not both.any():
        return 0.0
    leaps = np.abs(12 * np.log2(f0[1:][both] / f0[:-1][both]))
    return float(np.mean(leaps > OCTAVE_JUMP_SEMITONES))


def pitch(track: PitchTrack) -> Pitch:
    if track.f0 is None:
        return Pitch(
            status="unavailable",
            method="No pitch tracker could be run.",
            limitations=[f"Pitch was not computed ({track.method})."],
        )

    voiced = track.f0[~np.isnan(track.f0)]
    limitations = [
        f"F0 outside {track.floor_hz:.0f}-{track.ceiling_hz:.0f} Hz is not tracked for this recording, so unusually "
        "wide pitch excursions are cut off.",
        "Octave errors are still possible in creaky or noisy speech.",
        "Statistics in Hz are not comparable between speakers; the semitone measures are relative to this speaker.",
    ]
    result = Pitch(
        status="measured",
        method=track.method,
        series=to_series(track.f0, unit="Hz", hop_sec=track.hop_sec, start_sec=track.start_sec, digits=1),
        voiced_fraction=round(len(voiced) / len(track.f0), 3) if len(track.f0) else 0.0,
        tracking_floor_hz=round(track.floor_hz, 1),
        tracking_ceiling_hz=round(track.ceiling_hz, 1),
        limitations=limitations,
    )
    if len(voiced) == 0:
        result.limitations.insert(0, "No voiced frames were found, so no pitch statistics are reported.")
        return result

    p5, q1, q3, p95 = np.percentile(voiced, [5, 25, 75, 95])
    median = float(np.median(voiced))
    jumps = octave_jump_fraction(track.f0)
    result.median_hz = round(median, 1)
    result.mean_hz = round(float(voiced.mean()), 1)
    result.min_hz = round(float(voiced.min()), 1)
    result.max_hz = round(float(voiced.max()), 1)
    result.range_semitones = round(float(12 * np.log2(p95 / p5)), 2)
    result.iqr_semitones = round(float(12 * np.log2(q3 / q1)), 2)
    result.octave_jump_fraction = round(jumps, 4)
    if track.range_sensitivity_semitones is not None:
        result.range_sensitivity_semitones = round(track.range_sensitivity_semitones, 2)

    reasons = []
    if jumps > MAX_OCTAVE_JUMP_FRACTION:
        reasons.append(f"{jumps:.1%} of frame-to-frame steps leap more than {OCTAVE_JUMP_SEMITONES:.0f} semitones")
    if not track.adapted:
        reasons.append("there was too little voiced speech to adapt the search range to the speaker")
    if median < track.settings.min_hz * EDGE_MARGIN or median > track.settings.max_hz / EDGE_MARGIN:
        reasons.append("the median sits at the edge of the range the tracker can search")
    unstable_range = (track.range_sensitivity_semitones or 0.0) > MAX_RANGE_SENSITIVITY_SEMITONES
    unstable_voicing = (track.voiced_change_fraction or 0.0) > MAX_VOICED_CHANGE_FRACTION
    if unstable_range or unstable_voicing:
        reasons.append(
            "the result changes when the tracker's lower limit is nudged ("
            f"range by {track.range_sensitivity_semitones or 0:.1f} semitones, voiced frames by {track.voiced_change_fraction or 0:.0%}), "
            "which is typical of creaky or very low-pitched stretches"
        )
    result.reliability = "low" if reasons else "ok"
    if reasons:
        result.limitations.insert(0, "Low reliability: " + "; ".join(reasons) + ".")
    return result
