"""Deterministic signal-processing transforms that turn a reference recording into flawed variants.

Every transform returns the new samples and the exact intervals it altered, so the temporal
labels are known by construction rather than estimated. Praat's overlap-add resynthesis draws
random numbers for unvoiced sound, so its generator is re-seeded before every call; with that,
the same input always gives the same output.
"""

from dataclasses import dataclass, field

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import butter, sosfiltfilt

from ..audio.features import compute_frames
from ..audio.pitch import PITCH_CEILING_HZ, PITCH_FLOOR_HZ

FADE_SEC = 0.01
EDGE_MARGIN_SEC = 1.0
MIN_SPACING_SEC = 1.5
PRAAT_SEED = 20261013


@dataclass(frozen=True)
class Altered:
    start: float
    end: float
    label: str
    detail: str = ""


@dataclass(frozen=True)
class Transformed:
    samples: np.ndarray
    intervals: list[Altered]
    method: str
    tool: str
    parameters: dict = field(default_factory=dict)


def quiet_points(samples: np.ndarray, sample_rate: int, count: int) -> list[float]:
    """Up to `count` times, in order, at the quietest moments of the recording.

    These are the safest places to cut: the lowest points of the smoothed energy contour, kept
    away from the edges and from each other. Fewer are returned when the clip is too short.
    """
    frames = compute_frames(samples, sample_rate)
    smooth = uniform_filter1d(frames.energy_db, size=max(1, int(round(0.15 / frames.hop_sec))), mode="nearest")
    duration = len(samples) / sample_rate
    chosen: list[float] = []
    for index in np.argsort(smooth, kind="stable"):
        t = float(index * frames.hop_sec)
        if t < EDGE_MARGIN_SEC or t > duration - EDGE_MARGIN_SEC:
            continue
        if all(abs(t - other) >= MIN_SPACING_SEC for other in chosen):
            chosen.append(t)
        if len(chosen) == count:
            break
    return sorted(chosen)


def _fade(samples: np.ndarray, sample_rate: int, *, at_end: bool) -> np.ndarray:
    n = min(len(samples), int(FADE_SEC * sample_rate))
    out = samples.copy()
    if n:
        ramp = np.linspace(1.0, 0.0, n) if at_end else np.linspace(0.0, 1.0, n)
        if at_end:
            out[-n:] *= ramp
        else:
            out[:n] *= ramp
    return out


def insert_pauses(samples: np.ndarray, sample_rate: int, pause_sec: float, count: int) -> Transformed:
    """Insert `count` stretches of digital silence at the quietest moments."""
    points = quiet_points(samples, sample_rate, count)
    pieces: list[np.ndarray] = []
    intervals: list[Altered] = []
    previous = 0
    written = 0
    gap = np.zeros(int(round(pause_sec * sample_rate)), dtype=np.float32)
    for point in points:
        cut = int(round(point * sample_rate))
        pieces.append(_fade(samples[previous:cut], sample_rate, at_end=True))
        written += cut - previous
        intervals.append(
            Altered(
                start=written / sample_rate,
                end=(written + len(gap)) / sample_rate,
                label="inserted_pause",
                detail=f"{pause_sec:.2f} s of digital silence inserted at {point:.2f} s of the reference",
            )
        )
        pieces.append(gap)
        written += len(gap)
        previous = cut
    pieces.append(_fade(samples[previous:], sample_rate, at_end=False) if points else samples[previous:])
    return Transformed(
        samples=np.concatenate(pieces).astype(np.float32),
        intervals=intervals,
        method="insert_silence",
        tool="numpy",
        parameters={"pause_sec": pause_sec, "requested_count": count, "inserted_count": len(points)},
    )


def _psola_stretch(samples: np.ndarray, sample_rate: int, factor: float) -> np.ndarray:
    """Change duration by `factor` without changing pitch (Praat overlap-add)."""
    import parselmouth
    from parselmouth.praat import call

    parselmouth.praat.run(f"random_initializeWithSeedUnsafelyButPredictably ({PRAAT_SEED})")
    sound = parselmouth.Sound(samples.astype(np.float64), sampling_frequency=sample_rate)
    stretched = call(sound, "Lengthen (overlap-add)", PITCH_FLOOR_HZ, PITCH_CEILING_HZ, factor)
    return np.clip(stretched.values[0], -1.0, 1.0).astype(np.float32)


def change_rate(samples: np.ndarray, sample_rate: int, duration_factor: float, label: str) -> Transformed:
    """Uniformly speed up (`duration_factor` < 1) or slow down (> 1) the whole recording."""
    out = _psola_stretch(samples, sample_rate, duration_factor)
    return Transformed(
        samples=out,
        intervals=[
            Altered(0.0, len(out) / sample_rate, label, f"whole recording at {duration_factor:.2f}x the reference duration")
        ],
        method="time_stretch_psola",
        tool="praat-parselmouth",
        parameters={"duration_factor": duration_factor},
    )


def uneven_pacing(samples: np.ndarray, sample_rate: int, contrast: float) -> Transformed:
    """Alternate fast and slow stretches, switching at the quietest moments."""
    points = quiet_points(samples, sample_rate, 3)
    edges = [0, *[int(round(p * sample_rate)) for p in points], len(samples)]
    pieces: list[np.ndarray] = []
    intervals: list[Altered] = []
    written = 0
    for i, (start, end) in enumerate(zip(edges[:-1], edges[1:])):
        fast = i % 2 == 0
        factor = 1 / contrast if fast else contrast
        piece = _psola_stretch(samples[start:end], sample_rate, factor)
        intervals.append(
            Altered(
                start=written / sample_rate,
                end=(written + len(piece)) / sample_rate,
                label="fast_segment" if fast else "slow_segment",
                detail=f"{factor:.2f}x the reference duration for this stretch",
            )
        )
        pieces.append(piece)
        written += len(piece)
    return Transformed(
        samples=np.concatenate(pieces).astype(np.float32),
        intervals=intervals,
        method="alternating_time_stretch_psola",
        tool="praat-parselmouth",
        parameters={"contrast": contrast, "segments": len(intervals)},
    )


def flatten_pitch(samples: np.ndarray, sample_rate: int, keep: float) -> Transformed:
    """Scale pitch movement around the speaker's median by `keep` (1 = unchanged, 0 = flat)."""
    import parselmouth
    from parselmouth.praat import call

    parselmouth.praat.run(f"random_initializeWithSeedUnsafelyButPredictably ({PRAAT_SEED})")
    sound = parselmouth.Sound(samples.astype(np.float64), sampling_frequency=sample_rate)
    manipulation = call(sound, "To Manipulation", 0.01, PITCH_FLOOR_HZ, PITCH_CEILING_HZ)
    tier = call(manipulation, "Extract pitch tier")
    pitch = sound.to_pitch_ac(time_step=0.01, pitch_floor=PITCH_FLOOR_HZ, pitch_ceiling=PITCH_CEILING_HZ)
    voiced = pitch.selected_array["frequency"]
    voiced = voiced[voiced > 0]
    if len(voiced) == 0:
        raise ValueError("no voiced speech to flatten")
    median = float(np.median(voiced))
    call(tier, "Formula", f"{median} + (self - {median}) * {keep}")
    call([tier, manipulation], "Replace pitch tier")
    out = call(manipulation, "Get resynthesis (overlap-add)")
    result = np.clip(out.values[0], -1.0, 1.0).astype(np.float32)
    return Transformed(
        samples=result,
        intervals=[
            Altered(0.0, len(result) / sample_rate, "reduced_pitch_variation", f"pitch movement scaled to {keep:.2f} of the reference around {median:.0f} Hz")
        ],
        method="pitch_range_compression_psola",
        tool="praat-parselmouth",
        parameters={"keep_fraction": keep, "median_hz": round(median, 1)},
    )


def muffle(samples: np.ndarray, sample_rate: int, cutoff_hz: float) -> Transformed:
    """Low-pass filter the recording. This removes consonant detail; it is a proxy for unclear articulation."""
    sos = butter(6, cutoff_hz, btype="lowpass", fs=sample_rate, output="sos")
    out = sosfiltfilt(sos, samples).astype(np.float32)
    return Transformed(
        samples=np.clip(out, -1.0, 1.0),
        intervals=[
            Altered(0.0, len(out) / sample_rate, "reduced_high_frequency_detail", f"low-pass filtered at {cutoff_hz:.0f} Hz")
        ],
        method="lowpass_filter",
        tool="scipy",
        parameters={"cutoff_hz": cutoff_hz, "order": 6},
    )
