"""Checks when pitch tracking can be trusted on the demonstration dataset.

Run from backend/ after `python -m app.dataset build`:

    python -m app.audio.evaluate_pitch [--range-from-first SECONDS]

Most of the dataset's transforms leave pitch alone, so every pitch-preserving recording of a source
should measure about the same range; the pitch-monotony samples should measure that range times
their known `keep_fraction`. A reported range that misses this by more than TOLERANCE semitones is
counted as a false reading. Withheld recordings are counted separately. `--range-from-first` tries
choosing the speaker's search range from only the opening seconds instead of the whole recording.
It reports counts only and never changes a threshold.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .loading import load_audio
from .pitch import (
    DEFAULT_PITCH_SETTINGS,
    STABILITY_FLOOR_NUDGE,
    TIME_STEP_SEC,
    PitchSettings,
    PitchTrack,
    _praat_pass,
    _range_semitones,
    pitch,
    speaker_range,
    track_pitch,
)

DATASET = Path(__file__).resolve().parents[3] / "data" / "speakiq-contrastive-v1"
TOLERANCE = 1.5


@dataclass(frozen=True)
class Reading:
    source_id: str
    keep_fraction: float  # 1.0 for every transform that leaves pitch alone
    range_semitones: float | None
    reliable: bool


@dataclass(frozen=True)
class SourceSummary:
    source_id: str
    recordings: int
    withheld: int
    expected_range: float | None  # median reported range of the pitch-preserving recordings
    false_readings: int


def summarize(readings: list[Reading]) -> list[SourceSummary]:
    summaries = []
    for source_id in sorted({r.source_id for r in readings}):
        mine = [r for r in readings if r.source_id == source_id]
        reported = [r for r in mine if r.reliable and r.range_semitones is not None]
        plain = [r.range_semitones for r in reported if r.keep_fraction == 1.0]
        expected = float(np.median(plain)) if plain else None
        false = (
            sum(abs(r.range_semitones - expected * r.keep_fraction) > TOLERANCE for r in reported)
            if expected is not None
            else len([r for r in reported if r.keep_fraction != 1.0])  # nothing to check them against
        )
        summaries.append(SourceSummary(source_id, len(mine), len(mine) - len(reported), expected, false))
    return summaries


def track_from_opening(samples: np.ndarray, sample_rate: int, seconds: float, settings: PitchSettings = DEFAULT_PITCH_SETTINGS) -> PitchTrack:
    """The usual tracker, except that the speaker's search range comes from the opening `seconds` only."""
    head, _ = _praat_pass(samples[: int(seconds * sample_rate)], sample_rate, settings.min_hz, settings.max_hz)
    limits = speaker_range(head, settings)
    if limits is None:
        return track_pitch(samples, sample_rate, settings)
    f0, start = _praat_pass(samples, sample_rate, *limits)
    nudged, _ = _praat_pass(samples, sample_rate, limits[0] * STABILITY_FLOOR_NUDGE, limits[1])
    (base, base_count), (moved, moved_count) = _range_semitones(f0), _range_semitones(nudged)
    return PitchTrack(
        f0=f0,
        start_sec=start,
        hop_sec=TIME_STEP_SEC,
        method=f"range from the first {seconds:g} s",
        floor_hz=limits[0],
        ceiling_hz=limits[1],
        adapted=True,
        settings=settings,
        range_sensitivity_semitones=abs(base - moved) if base is not None and moved is not None else None,
        voiced_change_fraction=abs(base_count - moved_count) / base_count if base_count else None,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--range-from-first", type=float, metavar="SECONDS")
    args = parser.parse_args(argv)
    try:
        manifest = json.loads((DATASET / "manifest.json").read_text(encoding="utf-8"))
        readings = []
        for sample in manifest["samples"]:
            audio = load_audio((DATASET / sample["audio_path"]).read_bytes(), sample["audio_path"], max_duration_sec=600)
            track = (
                track_from_opening(audio.samples, audio.sample_rate, args.range_from_first)
                if args.range_from_first
                else track_pitch(audio.samples, audio.sample_rate)
            )
            measured = pitch(track)
            keep = sample["generation"]["parameters"].get("keep_fraction", 1.0) if sample["flaw_category"] == "pitch_monotony" else 1.0
            readings.append(Reading(sample["source_id"], keep, measured.range_semitones, measured.reliability == "ok"))
    except FileNotFoundError as error:
        print(f"Dataset audio not found ({error.filename}). Run `python -m app.dataset build` first.")
        return 1
    how = f"search range from the first {args.range_from_first:g} s" if args.range_from_first else "search range from the whole recording"
    print(f"Pitch tracking on {manifest['dataset_name']} {manifest['dataset_version']}, {how}; false reading = off by more than {TOLERANCE} semitones")
    for s in summarize(readings):
        expected = f"{s.expected_range:.1f} st" if s.expected_range is not None else "unknown"
        print(f"  {s.source_id}: withheld {s.withheld} of {s.recordings}; expected range {expected}; false readings among reported: {s.false_readings}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
