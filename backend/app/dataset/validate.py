"""Validates a dataset manifest and, optionally, the audio files it refers to."""

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

import soundfile as sf
from pydantic import ValidationError

from .schema import SEVERITY_RANK, DatasetManifest

TIME_TOLERANCE_SEC = 0.01
DURATION_TOLERANCE_SEC = 0.05
LABEL_FIELDS = {"flaw_category", "severity", "delivery_condition", "data_origin", "label_provenance", "label_support", "split"}


@dataclass(frozen=True)
class Issue:
    level: Literal["error", "warning"]
    code: str
    where: str
    message: str

    def __str__(self) -> str:
        return f"{self.level.upper():7} {self.code:24} {self.where}: {self.message}"


def _schema_issues(error: ValidationError) -> list[Issue]:
    issues = []
    for item in error.errors():
        location = ".".join(str(part) for part in item["loc"])
        field = str(item["loc"][-1]) if item["loc"] else ""
        if item["type"] == "missing" or item["type"].startswith("string_too_short"):
            code = "missing_metadata"
        elif field in LABEL_FIELDS:
            code = "invalid_label"
        else:
            code = "invalid_schema"
        issues.append(Issue("error", code, location, item["msg"]))
    return issues


def validate_manifest(data: dict, root: Path | None = None) -> list[Issue]:
    """Return every problem found. With `root`, audio files are checked too."""
    try:
        manifest = DatasetManifest.model_validate(data)
    except ValidationError as error:
        return _schema_issues(error)

    issues: list[Issue] = []

    def error(code: str, where: str, message: str) -> None:
        issues.append(Issue("error", code, where, message))

    def warn(code: str, where: str, message: str) -> None:
        issues.append(Issue("warning", code, where, message))

    for kind, ids in (
        ("sample_id", [s.sample_id for s in manifest.samples]),
        ("pair_id", [p.pair_id for p in manifest.pairs]),
        ("source_id", [s.source_id for s in manifest.sources]),
        ("audio_path", [s.audio_path for s in manifest.samples]),
    ):
        for value, count in Counter(ids).items():
            if count > 1:
                error("duplicate_id", value, f"{kind} appears {count} times")

    sources = {s.source_id: s for s in manifest.sources}
    pairs = {p.pair_id: p for p in manifest.pairs}
    by_id = {s.sample_id: s for s in manifest.samples}
    paths = {s.audio_path for s in manifest.samples}

    for sample in manifest.samples:
        where = sample.sample_id
        source = sources.get(sample.source_id)
        pair = pairs.get(sample.pair_id)
        if source is None:
            error("unknown_reference", where, f"source_id '{sample.source_id}' is not in sources")
        elif source.speaker_id != sample.speaker_id:
            error("speaker_mismatch", where, f"speaker_id '{sample.speaker_id}' differs from its source's '{source.speaker_id}'")
        if pair is None:
            error("unknown_reference", where, f"pair_id '{sample.pair_id}' is not in pairs")
        elif pair.source_id != sample.source_id:
            error("unknown_reference", where, "sample and its pair name different sources")
        if sample.reference_audio_path not in paths:
            error("unknown_reference", where, f"reference_audio_path '{sample.reference_audio_path}' is not a sample in this dataset")

        # Labels
        if sample.severity_rank != SEVERITY_RANK[sample.severity]:
            error("invalid_label", where, f"severity_rank {sample.severity_rank} does not match severity '{sample.severity}'")
        if sample.delivery_condition == "reference":
            if sample.flaw_category is not None or sample.severity != "none":
                error("invalid_label", where, "a reference sample must have no flaw_category and severity 'none'")
            if sample.flaw_intervals:
                error("invalid_label", where, "a reference sample must have no flaw intervals")
        else:
            if sample.flaw_category is None or sample.severity == "none":
                error("invalid_label", where, "a flawed sample needs a flaw_category and a severity other than 'none'")
            if not sample.flaw_intervals:
                error("invalid_timestamp", where, "a flawed sample needs at least one flaw interval")
            if sample.annotation.label_support is None:
                error("missing_metadata", where, "a flawed sample must state label_support")
        if sample.flaw_category and sample.flaw_category not in manifest.flaw_categories_covered:
            error("invalid_label", where, f"flaw_category '{sample.flaw_category}' is not listed in flaw_categories_covered")
        if sample.annotation.label_provenance == "manual" and not sample.annotation.annotator:
            error("missing_metadata", where, "a manual label must name its annotator")
        if source and source.speaker_kind == "synthetic" and sample.data_origin != "synthetic":
            error("invalid_label", where, "audio from a synthetic speaker must have data_origin 'synthetic'")
        if source and source.speaker_kind == "human" and sample.data_origin == "synthetic":
            error("invalid_label", where, "audio from a human speaker cannot have data_origin 'synthetic'")
        if sample.delivery_condition == "flawed" and sample.data_origin == "real_recording":
            error("invalid_label", where, "a flawed sample made by transformation cannot be labelled 'real_recording'")

        # Timestamps
        for i, interval in enumerate(sample.flaw_intervals):
            at = f"{where}.flaw_intervals[{i}]"
            if interval.start < 0:
                error("invalid_timestamp", at, f"start {interval.start} is negative")
            if interval.end <= interval.start:
                error("invalid_timestamp", at, f"end {interval.end} is not after start {interval.start}")
            if interval.end > sample.duration_sec + TIME_TOLERANCE_SEC:
                error("invalid_timestamp", at, f"end {interval.end} is past the audio duration {sample.duration_sec}")

        # Transcripts
        if pair is not None:
            same = sample.transcript.strip() == pair.transcript.strip()
            if not same and not sample.transcript_differs_from_reference:
                error("mismatched_transcript", where, "transcript differs from the pair's transcript without transcript_differs_from_reference")
            if not same and not sample.transcript_difference_note.strip():
                error("mismatched_transcript", where, "a differing transcript needs a transcript_difference_note")
            if same and sample.transcript_differs_from_reference:
                warn("mismatched_transcript", where, "transcript_differs_from_reference is set but the transcripts are identical")

    for pair in manifest.pairs:
        members = [s for s in manifest.samples if s.pair_id == pair.pair_id]
        references = [s for s in members if s.delivery_condition == "reference"]
        if len(references) != 1:
            error("pair_integrity", pair.pair_id, f"expected exactly one reference sample, found {len(references)}")
        elif references[0].sample_id != pair.reference_sample_id:
            error("pair_integrity", pair.pair_id, "reference_sample_id does not name the pair's reference sample")
        if pair.reference_sample_id not in by_id:
            error("unknown_reference", pair.pair_id, f"reference_sample_id '{pair.reference_sample_id}' is not a sample")
        if pair.source_id not in sources:
            error("unknown_reference", pair.pair_id, f"source_id '{pair.source_id}' is not in sources")
        if len({s.split for s in members}) > 1:
            error("split_leakage", pair.pair_id, "samples of one pair are in different splits")

    # Splits: every speaker in exactly one split, and samples agree with it.
    assigned = Counter(speaker for name in ("train", "validation", "test") for speaker in getattr(manifest.splits, name))
    for speaker, count in assigned.items():
        if count > 1:
            error("split_leakage", speaker, f"speaker is assigned to {count} splits")
    split_of = {speaker: name for name in ("train", "validation", "test") for speaker in getattr(manifest.splits, name)}
    for speaker in {s.speaker_id for s in manifest.samples}:
        used = {s.split for s in manifest.samples if s.speaker_id == speaker}
        if len(used) > 1:
            error("split_leakage", speaker, f"speaker's samples are spread over splits {sorted(used)}")
        if speaker not in split_of:
            error("split_leakage", speaker, "speaker has samples but is not assigned to a split")
        elif used and used != {split_of[speaker]}:
            error("split_leakage", speaker, f"samples are in {sorted(used)} but the speaker is assigned to '{split_of[speaker]}'")
    for source_id in sources:
        if len({s.split for s in manifest.samples if s.source_id == source_id}) > 1:
            error("split_leakage", source_id, "one source recording appears in more than one split")

    if root is not None:
        for sample in manifest.samples:
            path = root / sample.audio_path
            if not path.is_file():
                error("missing_file", sample.sample_id, f"audio file not found: {sample.audio_path}")
                continue
            if hashlib.sha256(path.read_bytes()).hexdigest() != sample.sha256:
                error("checksum_mismatch", sample.sample_id, "audio file does not match the recorded sha256")
            try:
                info = sf.info(path)
            except Exception:
                error("unreadable_audio", sample.sample_id, f"audio file could not be decoded: {sample.audio_path}")
                continue
            if info.samplerate != sample.sample_rate_hz:
                error("audio_mismatch", sample.sample_id, f"file is {info.samplerate} Hz, manifest says {sample.sample_rate_hz}")
            if abs(info.duration - sample.duration_sec) > DURATION_TOLERANCE_SEC:
                error("audio_mismatch", sample.sample_id, f"file lasts {info.duration:.3f} s, manifest says {sample.duration_sec}")

    return issues


def validate_directory(root: Path, *, check_files: bool = True) -> list[Issue]:
    manifest_path = root / "manifest.json"
    if not manifest_path.is_file():
        return [Issue("error", "missing_file", str(manifest_path), "manifest.json not found")]
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [Issue("error", "invalid_schema", str(manifest_path), f"not valid JSON: {error.msg}")]
    return validate_manifest(data, root if check_files else None)
