"""Pause detection and speaking-rate estimation from the energy contour."""

import re

import numpy as np
from scipy.ndimage import uniform_filter1d
from scipy.signal import find_peaks

from .features import DEFAULT_PAUSE_SETTINGS, MIN_SIGNAL_DB, Frames, PauseSettings
from .pitch import PitchTrack
from .schemas import PauseInterval, Pauses, SpeakingRate, TranscriptRate

# Syllable nuclei: energy peaks with at least this dip on either side, no closer than this.
NUCLEUS_PROMINENCE_DB = 2.0
NUCLEUS_MIN_SPACING_SEC = 0.10
ENVELOPE_SMOOTHING_SEC = 0.05

TOO_QUIET = "The recording is too quiet to separate speech from silence."
TOO_FLAT = (
    "The level barely changes over the recording (for example steady noise or a steady tone), "
    "so speech cannot be separated from silence."
)


def _unusable_reason(frames: Frames) -> str:
    return TOO_QUIET if frames.speech_level_db <= MIN_SIGNAL_DB else TOO_FLAT


def pauses(frames: Frames, duration_sec: float, settings: PauseSettings = DEFAULT_PAUSE_SETTINGS) -> Pauses:
    levels = {
        "noise_floor_db": round(frames.noise_floor_db, 2),
        "speech_level_db": round(frames.speech_level_db, 2),
        "dynamic_range_db": round(frames.dynamic_range_db, 2),
    }
    if frames.silence_threshold_db is None:
        return Pauses(
            status="unavailable",
            method="Energy thresholding was not applied.",
            min_pause_sec=settings.min_pause_sec,
            limitations=[_unusable_reason(frames)],
            **levels,
        )

    silent = ~frames.active
    # Find runs of silent frames: pad so every run has a start and an end edge.
    edges = np.flatnonzero(np.diff(np.concatenate(([False], silent, [False])).astype(np.int8)))
    intervals: list[PauseInterval] = []
    for first, after_last in zip(edges[0::2], edges[1::2]):
        start = float(first * frames.hop_sec)
        end = min(float(after_last * frames.hop_sec), duration_sec)
        if end - start < settings.min_pause_sec:
            continue
        position = "leading" if first == 0 else "trailing" if after_last == len(silent) else "internal"
        intervals.append(PauseInterval(start=round(start, 3), end=round(end, 3), position=position))

    noisy = frames.threshold_rule == "noise_floor"
    low_confidence = frames.dynamic_range_db < settings.low_confidence_range_db
    limitations = [
        "Quiet speech such as unvoiced consonants or trailing words can be counted as silence.",
        "Detects silence only; it cannot tell a hesitation from a deliberate pause.",
    ]
    if low_confidence:
        limitations.insert(
            0,
            f"Low confidence: speech is only {frames.dynamic_range_db:.0f} dB above the background, so quiet speech is "
            "easily mistaken for silence and extra pauses are likely.",
        )
    elif noisy:
        limitations.insert(
            0, "Background noise was detected; the threshold was set just above it, so quiet speech may be counted as silence."
        )

    internal = [i for i in intervals if i.position == "internal"]
    silence_sec = sum(i.end - i.start for i in intervals)
    if noisy:
        rule = (
            f"Background noise detected: runs of frames within {settings.noise_margin_db:g} dB of the noise floor "
            "(5th percentile of frame energy)"
        )
    else:
        rule = (
            f"Runs of frames more than {settings.silence_below_speech_db:g} dB below the speech level "
            "(95th percentile of frame energy)"
        )
    return Pauses(
        status="measured",
        method=f"{rule}, lasting at least {settings.min_pause_sec:.2f} s.",
        threshold_db=round(frames.silence_threshold_db, 2),
        threshold_rule=frames.threshold_rule,
        reliability="low" if low_confidence else "ok",
        min_pause_sec=settings.min_pause_sec,
        intervals=intervals,
        internal_pause_count=len(internal),
        total_internal_pause_sec=round(sum(i.end - i.start for i in internal), 3),
        speech_sec=round(max(0.0, duration_sec - silence_sec), 3),
        limitations=limitations,
        **levels,
    )


def speaking_rate(frames: Frames, track: PitchTrack, pause_result: Pauses, duration_sec: float) -> SpeakingRate:
    if frames.silence_threshold_db is None:
        return SpeakingRate(
            status="unavailable", method="Syllable nuclei were not detected.", limitations=[_unusable_reason(frames)]
        )

    smoothing = max(1, int(round(ENVELOPE_SMOOTHING_SEC / frames.hop_sec)))
    envelope = uniform_filter1d(frames.energy_db, size=smoothing, mode="nearest")
    peaks, _ = find_peaks(
        envelope,
        height=frames.silence_threshold_db,
        prominence=NUCLEUS_PROMINENCE_DB,
        distance=max(1, int(round(NUCLEUS_MIN_SPACING_SEC / frames.hop_sec))),
    )
    times = peaks * frames.hop_sec

    limitations = [
        "An estimate, not a count: syllable nuclei are inferred from energy peaks, with no speech recognition.",
        "Tends to undercount in fast or mumbled speech and to overcount with background noise or music.",
        "Not validated against hand-counted syllables for this recording.",
    ]
    voicing = [track.voiced_at(float(t)) for t in times]
    if track.f0 is None:
        method_voicing = "Voicing could not be checked because pitch is unavailable."
        limitations.append("Without pitch, unvoiced noise bursts may be counted as syllables.")
    else:
        times = times[[bool(v) for v in voicing]]
        method_voicing = "Peaks in unvoiced frames are discarded."

    count = int(len(times))
    speech_sec = pause_result.speech_sec or 0.0
    return SpeakingRate(
        status="estimated",
        method=(
            f"Peaks in the {ENVELOPE_SMOOTHING_SEC * 1000:.0f} ms-smoothed energy contour above the silence threshold, "
            f"with at least {NUCLEUS_PROMINENCE_DB:.0f} dB prominence and {NUCLEUS_MIN_SPACING_SEC * 1000:.0f} ms spacing "
            f"(after de Jong and Wempe, 2009). {method_voicing}"
        ),
        syllable_nuclei=count,
        syllable_times_sec=[round(float(t), 3) for t in times],
        speech_rate_syll_per_sec=round(count / duration_sec, 2),
        articulation_rate_syll_per_sec=round(count / speech_sec, 2) if speech_sec > 0 else None,
        limitations=limitations,
    )


def transcript_rate(transcript: str | None, duration_sec: float) -> TranscriptRate:
    words = re.findall(r"[^\W_]+(?:['’-][^\W_]+)*", transcript or "")
    if not words:
        return TranscriptRate(
            status="unavailable",
            method="Transcript word count divided by audio duration.",
            limitations=["No transcript was supplied."],
        )
    return TranscriptRate(
        status="estimated",
        method="Number of words in the supplied transcript divided by the full audio duration, including pauses.",
        word_count=len(words),
        words_per_minute=round(len(words) / duration_sec * 60, 1),
        limitations=[
            "Assumes the transcript matches what was said; this is not checked here. Use the alignment result to see which words were actually recognised.",
        ],
    )
