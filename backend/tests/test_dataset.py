import copy
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from app.dataset.__main__ import DATA_ROOT, EXAMPLES_DIR, FULL_DIR, REGISTRY, SCHEMA_PATH, schema_json
from app.dataset.build import LEVELS, NOT_COVERED, RECIPES, build_dataset
from app.dataset.splits import split_speakers
from app.dataset.validate import validate_directory, validate_manifest

from .audio_samples import SR, silence, syllables

SEED = 7
TEST_LEVELS = ("mild", "severe")


def codes(issues, level="error"):
    return sorted({issue.code for issue in issues if issue.level == level})


def write_registry(directory: Path, speakers: int = 3) -> Path:
    """A registry of generated tone-pulse 'speakers'. Synthetic, and labelled as such."""
    directory.mkdir(parents=True, exist_ok=True)
    sources = []
    for i in range(speakers):
        audio = np.concatenate([syllables(10, f0_hz=120 + 30 * i), silence(0.5), syllables(10, f0_hz=120 + 30 * i)])
        path = directory / f"synthetic-{i}.wav"
        sf.write(path, audio, SR, subtype="PCM_16")
        sources.append(
            {
                "source_id": f"synthetic-{i}",
                "speaker_id": f"synthetic-speaker-{i}",
                "speaker_kind": "synthetic",
                "audio_path": path.name,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "origin": "Generated tone pulses for tests",
                "description": "Test signal, not speech",
                "license": "CC0",
                "attribution": "SpeakIQ tests",
                "transcript": "test signal",
                "transcript_provenance": "source_text",
            }
        )
    registry = directory / "sources.json"
    registry.write_text(json.dumps({"sources": sources}), encoding="utf-8")
    return registry


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root = tmp_path_factory.mktemp("dataset")
    registry = write_registry(root / "sources")
    out = root / "out"
    manifest = build_dataset(registry, out, seed=SEED, only_levels=TEST_LEVELS)
    return registry, out, manifest


@pytest.fixture
def data(built):
    """A fresh, editable copy of a valid manifest."""
    return json.loads((built[1] / "manifest.json").read_text(encoding="utf-8"))


def flawed(data, category="excessive_pauses"):
    return next(s for s in data["samples"] if s["flaw_category"] == category and s["severity"] == "severe")


# --- Building --------------------------------------------------------------------------------


def test_built_dataset_passes_validation_including_audio_files(built):
    _, out, manifest = built

    assert validate_directory(out) == []
    assert len(manifest.samples) == 3 * (1 + len(RECIPES) * len(TEST_LEVELS))
    assert len(manifest.pairs) == 3


def test_build_is_reproducible(built, tmp_path):
    registry, out, _ = built

    build_dataset(registry, tmp_path / "again", seed=SEED, only_levels=TEST_LEVELS)

    assert (tmp_path / "again" / "manifest.json").read_bytes() == (out / "manifest.json").read_bytes()


def test_synthetic_sources_are_never_labelled_as_real_recordings(built):
    assert {s.data_origin for s in built[2].samples} == {"synthetic"}


def test_every_pair_has_one_reference_and_shares_one_transcript(built):
    manifest = built[2]
    for pair in manifest.pairs:
        members = [s for s in manifest.samples if s.pair_id == pair.pair_id]
        assert [s.sample_id for s in members if s.delivery_condition == "reference"] == [pair.reference_sample_id]
        assert {s.transcript for s in members} == {pair.transcript}
        assert {s.reference_audio_path for s in members} == {f"audio/{pair.pair_id}/{pair.reference_sample_id}.flac"}


def test_inserted_pause_intervals_are_exact_and_silent_in_the_audio(built):
    _, out, manifest = built
    reference = next(s for s in manifest.samples if s.sample_id == "synthetic-0__reference")
    sample = next(s for s in manifest.samples if s.sample_id == "synthetic-0__excessive_pauses__severe")
    audio, rate = sf.read(out / sample.audio_path, dtype="float32")

    inserted = sum(i.end - i.start for i in sample.flaw_intervals)
    assert len(sample.flaw_intervals) == 3
    assert inserted == pytest.approx(3 * 1.8, abs=0.001)
    assert sample.duration_sec == pytest.approx(reference.duration_sec + inserted, abs=0.001)
    for interval in sample.flaw_intervals:
        assert np.all(audio[int(interval.start * rate) + 1 : int(interval.end * rate) - 1] == 0)
    assert sample.annotation.label_provenance == "generated_by_construction"
    assert sample.measured.provenance == "automatic_estimate"
    assert sample.measured.support_check.supported is True


def test_severity_gradient_orders_the_strength_of_each_transform(built):
    manifest = built[2]
    by_id = {s.sample_id: s for s in manifest.samples}
    reference = by_id["synthetic-0__reference"]

    def pair(category):
        return by_id[f"synthetic-0__{category}__mild"], by_id[f"synthetic-0__{category}__severe"]

    mild, severe = pair("rushed_delivery")
    assert severe.duration_sec < mild.duration_sec < reference.duration_sec
    assert severe.duration_sec == pytest.approx(reference.duration_sec * 0.65, rel=0.03)
    mild, severe = pair("slow_delivery")
    assert severe.duration_sec > mild.duration_sec > reference.duration_sec
    mild, severe = pair("excessive_pauses")
    assert severe.measured.total_silence_sec > mild.measured.total_silence_sec > reference.measured.total_silence_sec
    assert (mild.severity_rank, severe.severity_rank, reference.severity_rank) == (2, 4, 0)


def test_uneven_pacing_labels_alternating_segments_that_cover_the_sample(built):
    sample = next(s for s in built[2].samples if s.sample_id == "synthetic-0__uneven_pacing__severe")

    assert [i.label for i in sample.flaw_intervals] == ["fast_segment", "slow_segment", "fast_segment", "slow_segment"]
    assert sample.flaw_intervals[0].start == 0
    assert sample.flaw_intervals[-1].end == pytest.approx(sample.duration_sec, abs=0.01)
    for before, after in zip(sample.flaw_intervals, sample.flaw_intervals[1:]):
        assert after.start == pytest.approx(before.end, abs=0.001)
    assert sample.measured.support_check.supported is None  # no independent check exists; not claimed


def test_proxy_labels_are_marked(built):
    support = {s.flaw_category: s.annotation.label_support for s in built[2].samples if s.flaw_category}

    assert support["unclear_articulation"] == "proxy"
    assert support["excessive_pauses"] == "by_construction"
    assert "PROXY" in next(s.annotation.notes for s in built[2].samples if s.flaw_category == "unclear_articulation")


def test_build_refuses_a_source_whose_checksum_changed(built, tmp_path):
    registry = write_registry(tmp_path / "sources", speakers=1)
    data = json.loads(registry.read_text(encoding="utf-8"))
    data["sources"][0]["sha256"] = "0" * 64
    registry.write_text(json.dumps(data), encoding="utf-8")

    with pytest.raises(ValueError, match="checksum mismatch"):
        build_dataset(registry, tmp_path / "out")


# --- Splits ----------------------------------------------------------------------------------


def test_splits_keep_each_speaker_and_pair_in_one_split(built):
    manifest = built[2]
    splits = manifest.splits

    assert sorted(splits.train + splits.validation + splits.test) == sorted({s.speaker_id for s in manifest.samples})
    assert len(splits.train) == len(splits.validation) == len(splits.test) == 1
    for speaker in {s.speaker_id for s in manifest.samples}:
        assert len({s.split for s in manifest.samples if s.speaker_id == speaker}) == 1


def test_split_assignment_is_deterministic_and_seed_dependent():
    speakers = [f"s{i}" for i in range(10)]

    assert split_speakers(speakers, 1) == split_speakers(list(reversed(speakers)), 1)
    assert any(split_speakers(speakers, 1) != split_speakers(speakers, seed) for seed in range(2, 8))
    result = split_speakers(speakers, 1)
    assert (len(result["train"]), len(result["validation"]), len(result["test"])) == (8, 1, 1)


def test_too_few_speakers_are_not_split(tmp_path):
    assert split_speakers(["a", "b"], 1) == {"train": ["a", "b"], "validation": [], "test": []}

    manifest = build_dataset(write_registry(tmp_path / "sources", speakers=1), tmp_path / "out", only_levels=("severe",))

    assert {s.split for s in manifest.samples} == {"train"}
    assert "Fewer than three speakers" in manifest.splits.notes


# --- Validation ------------------------------------------------------------------------------


def test_reports_missing_and_altered_audio_files(built, tmp_path):
    _, out, _ = built
    data = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    data["samples"][1]["audio_path"] = "audio/nowhere.flac"
    data["samples"][2]["sha256"] = "f" * 64
    data["samples"][3]["duration_sec"] += 1.0

    issues = validate_manifest(data, out)

    assert codes(issues) == ["audio_mismatch", "checksum_mismatch", "missing_file"]
    assert validate_manifest(data) == []  # nothing wrong with the metadata alone
    assert codes(validate_directory(tmp_path)) == ["missing_file"]


def test_reports_invalid_timestamps(data):
    sample = flawed(data)
    sample["flaw_intervals"][0]["start"] = -0.5
    sample["flaw_intervals"][1]["end"] = sample["flaw_intervals"][1]["start"]
    sample["flaw_intervals"][2]["end"] = sample["duration_sec"] + 5
    flawed(data, "rushed_delivery")["flaw_intervals"] = []

    issues = validate_manifest(data)

    assert codes(issues) == ["invalid_timestamp"]
    assert len(issues) == 4


def test_reports_duplicate_ids(data):
    data["samples"].append(copy.deepcopy(data["samples"][1]))
    data["pairs"].append(copy.deepcopy(data["pairs"][0]))

    messages = [str(i) for i in validate_manifest(data) if i.code == "duplicate_id"]

    assert any("sample_id" in m for m in messages)
    assert any("audio_path" in m for m in messages)
    assert any("pair_id" in m for m in messages)


def test_reports_mismatched_transcripts_unless_documented(data):
    sample = flawed(data)
    sample["transcript"] = "test um signal"
    assert codes(validate_manifest(data)) == ["mismatched_transcript"]

    sample["transcript_differs_from_reference"] = True
    assert codes(validate_manifest(data)) == ["mismatched_transcript"]  # still needs a note

    sample["transcript_difference_note"] = "The filler 'um' was added after 'test'."
    assert validate_manifest(data) == []


def test_reports_invalid_labels(data):
    unknown = copy.deepcopy(data)
    flawed(unknown)["flaw_category"] = "mumbling"
    flawed(unknown, "slow_delivery")["severity"] = "catastrophic"
    assert codes(validate_manifest(unknown)) == ["invalid_label"]

    reference = next(s for s in data["samples"] if s["delivery_condition"] == "reference")
    reference["flaw_category"] = "slow_delivery"
    flawed(data)["severity_rank"] = 1
    flawed(data, "pitch_monotony")["flaw_category"] = "filler_words"  # defined, but not covered by this dataset
    flawed(data, "uneven_pacing")["data_origin"] = "real_recording"
    issues = validate_manifest(data)
    assert codes(issues) == ["invalid_label"]
    assert len(issues) == 5


def test_reports_missing_metadata(data):
    removed = copy.deepcopy(data)
    del removed["samples"][0]["annotation"]
    del removed["dataset_version"]
    removed["sources"][0]["license"] = ""
    assert codes(validate_manifest(removed)) == ["missing_metadata"]
    assert len(validate_manifest(removed)) == 3

    flawed(data)["annotation"]["label_support"] = None
    flawed(data, "slow_delivery")["annotation"]["label_provenance"] = "manual"
    assert codes(validate_manifest(data)) == ["missing_metadata"]


def test_reports_unknown_fields_and_bad_json(data, tmp_path):
    data["samples"][0]["surprise"] = 1
    assert codes(validate_manifest(data)) == ["invalid_schema"]

    (tmp_path / "manifest.json").write_text("{not json", encoding="utf-8")
    assert codes(validate_directory(tmp_path)) == ["invalid_schema"]


def test_reports_speaker_and_pair_leakage_across_splits(data):
    moved = copy.deepcopy(data)
    flawed(moved)["split"] = "test" if flawed(moved)["split"] != "test" else "train"
    assert codes(validate_manifest(moved)) == ["split_leakage"]

    data["splits"]["test"].append(data["splits"]["train"][0])
    assert codes(validate_manifest(data)) == ["split_leakage"]


def test_reports_broken_references_between_records(data):
    flawed(data)["source_id"] = "missing-source"
    flawed(data, "slow_delivery")["speaker_id"] = "someone-else"
    data["pairs"][1]["reference_sample_id"] = "missing-sample"

    assert {"unknown_reference", "speaker_mismatch", "pair_integrity"} <= set(codes(validate_manifest(data)))


# --- Committed dataset files -----------------------------------------------------------------


def committed(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_committed_example_set_is_valid_and_its_audio_is_present():
    assert validate_directory(EXAMPLES_DIR) == []


def test_committed_full_manifest_is_valid():
    # The full audio is not in Git, so only the metadata is checked here.
    assert validate_directory(FULL_DIR, check_files=False) == []


def test_committed_manifest_matches_the_build_recipe():
    manifest = committed(FULL_DIR / "manifest.json")
    samples = manifest["samples"]

    assert len(samples) == len(manifest["pairs"]) * (1 + len(RECIPES) * len(LEVELS))
    assert manifest["flaw_categories_covered"] == list(RECIPES)
    assert manifest["flaw_categories_not_covered"] == NOT_COVERED
    assert not any(s["flaw_category"] == "filler_words" for s in samples)
    assert {s["data_origin"] for s in samples if s["delivery_condition"] == "flawed"} == {"transformed_real"}
    assert {s["annotation"]["label_provenance"] for s in samples} == {"generated_by_construction"}  # no manual labels exist


def test_example_audio_is_the_same_audio_as_the_full_build():
    full = {s["sample_id"]: s["sha256"] for s in committed(FULL_DIR / "manifest.json")["samples"]}

    for sample in committed(EXAMPLES_DIR / "manifest.json")["samples"]:
        assert full[sample["sample_id"]] == sample["sha256"]


def test_committed_sources_match_their_checksums_and_state_their_licence():
    for source in committed(REGISTRY)["sources"]:
        path = REGISTRY.parent / source["audio_path"]
        assert hashlib.sha256(path.read_bytes()).hexdigest() == source["sha256"]
        assert source["speaker_kind"] == "human"
        assert "Public domain" in source["license"]
        assert source["transcript_provenance"] == "automatic_asr_unverified"


def test_committed_schema_file_is_current():
    assert SCHEMA_PATH.read_text(encoding="utf-8") == schema_json()


def test_dataset_card_exists_and_generated_audio_is_ignored_by_git():
    card = (DATA_ROOT / "DATASET_CARD.md").read_text(encoding="utf-8")
    for heading in ("Provenance", "Licensing", "Generation", "Annotation", "Limitations", "Biases", "Intended use"):
        assert heading in card
    assert "data/speakiq-contrastive-v1/audio/" in (DATA_ROOT.parent / ".gitignore").read_text(encoding="utf-8")
