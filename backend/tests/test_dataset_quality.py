"""Regression tests for transcript review, reproducibility checks, manifest paths and export."""

import hashlib
import json
import zipfile
from datetime import date
from pathlib import Path

import pytest

from app.dataset.__main__ import EXAMPLES_DIR, EXAMPLES_OPTIONS, FULL_DIR, REGISTRY, main, rebuild_differences
from app.dataset.build import build_dataset
from app.dataset.export import ExportError, export_dataset
from app.dataset.review import ReviewError, interactive_review, review_sheet, review_status, verify_transcript
from app.dataset.validate import validate_directory, validate_manifest

from .test_dataset import codes, write_registry

LEVELS = ("severe",)


@pytest.fixture
def workspace(tmp_path):
    """A small synthetic data root laid out like data/: sources, schema, card and a built dataset."""
    registry = write_registry(tmp_path / "sources")
    (tmp_path / "schema").mkdir()
    (tmp_path / "schema" / "dataset.schema.json").write_text("{}", encoding="utf-8")
    (tmp_path / "DATASET_CARD.md").write_text("# Test card\n", encoding="utf-8")
    out = tmp_path / "built"
    build_dataset(registry, out, only_levels=LEVELS)
    return tmp_path, registry, out


def manifest_of(directory: Path) -> dict:
    return json.loads((directory / "manifest.json").read_text(encoding="utf-8"))


# --- Transcript verification -----------------------------------------------------------------


def test_transcripts_start_unverified_and_the_review_sheet_points_at_the_audio(workspace):
    _, registry, _ = workspace

    sources = review_status(registry)
    sheet = review_sheet(registry)

    assert {s.transcript_review.status for s in sources} == {"unverified"}
    assert all(s.transcript_review.reviewer is None for s in sources)
    assert "synthetic-0.wav" in sheet
    assert "[description not verified]" in sheet
    assert "--listened" in sheet


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        (dict(reviewer="", listened=True), "reviewer name is required"),
        (dict(reviewer="   ", listened=True), "reviewer name is required"),
        (dict(reviewer="Asha", listened=False), "listened to the audio"),
        (dict(reviewer="Asha", listened=True, corrected_text="   "), "corrected transcript is empty"),
    ],
)
def test_verification_is_refused_without_a_reviewer_who_listened(workspace, kwargs, message):
    _, registry, _ = workspace
    before = registry.read_bytes()

    with pytest.raises(ReviewError, match=message):
        verify_transcript(registry, "synthetic-0", **kwargs)

    assert registry.read_bytes() == before  # a refused review changes nothing


def test_unknown_source_is_refused(workspace):
    with pytest.raises(ReviewError, match="Unknown source 'nope'"):
        verify_transcript(workspace[1], "nope", reviewer="Asha", listened=True)


def test_confirming_a_transcript_records_who_and_when_without_changing_the_text(workspace):
    _, registry, _ = workspace

    source = verify_transcript(registry, "synthetic-0", reviewer="Asha", listened=True, today=date(2026, 10, 13))

    review = source.transcript_review
    assert source.transcript == "test signal"
    assert source.transcript_provenance == "manual_verified"
    assert (review.status, review.reviewer, review.reviewed_on, review.changed) == ("verified", "Asha", "2026-10-13", False)
    assert review.asr_transcript == "test signal"
    others = [s for s in review_status(registry) if s.source_id != "synthetic-0"]
    assert {s.transcript_review.status for s in others} == {"unverified"}


def test_correcting_a_transcript_keeps_the_original_machine_text(workspace):
    _, registry, _ = workspace

    source = verify_transcript(
        registry, "synthetic-1", reviewer="Asha", listened=True, corrected_text=" corrected signal \n", notes="one word fixed"
    )
    again = verify_transcript(registry, "synthetic-1", reviewer="Ben", listened=True, corrected_text="corrected signal twice")

    assert source.transcript == "corrected signal"
    assert (source.transcript_review.changed, source.transcript_review.asr_transcript) == (True, "test signal")
    assert source.transcript_review.notes == "one word fixed"
    # A second review still remembers the first machine transcript, not the first correction.
    assert again.transcript_review.asr_transcript == "test signal"
    assert again.transcript_review.reviewer == "Ben"


def test_a_built_dataset_goes_stale_after_a_correction_until_it_is_rebuilt(workspace):
    _, registry, out = workspace
    verify_transcript(registry, "synthetic-0", reviewer="Asha", listened=True, corrected_text="corrected signal")

    stale = manifest_of(out)
    stale["sources"] = json.loads(registry.read_text(encoding="utf-8"))["sources"]
    assert codes(validate_manifest(stale)) == ["mismatched_transcript"]

    rebuilt = build_dataset(registry, out, only_levels=LEVELS)
    assert validate_directory(out) == []
    corrected = [s for s in rebuilt.samples if s.source_id == "synthetic-0"]
    assert {s.transcript for s in corrected} == {"corrected signal"}
    assert next(s for s in rebuilt.sources if s.source_id == "synthetic-0").transcript_provenance == "manual_verified"


def test_validation_rejects_claims_of_verification_without_a_review(workspace):
    data = manifest_of(workspace[2])

    data["sources"][0]["transcript_provenance"] = "manual_verified"
    assert codes(validate_manifest(data)) == ["transcript_review"]

    data["sources"][0]["transcript_provenance"] = "source_text"
    data["sources"][0]["transcript_review"] = {"status": "verified", "reviewer": "Asha", "reviewed_on": "2026-10-13", "method": "x"}
    assert codes(validate_manifest(data)) == ["transcript_review"]

    data["sources"][0]["transcript_review"] = {"status": "verified", "reviewer": "Asha", "reviewed_on": "13 October", "method": "x"}
    assert codes(validate_manifest(data)) == ["invalid_schema"]  # the date must be YYYY-MM-DD


def test_committed_transcripts_and_descriptions_are_still_marked_unverified():
    """Nobody has reviewed the real sources. This fails the day someone records a review, which is the
    moment to update the dataset card too."""
    for source in review_status(REGISTRY):
        assert source.transcript_provenance == "automatic_asr_unverified"
        assert (source.transcript_review.status, source.transcript_review.reviewer) == ("unverified", None)
        assert source.description_verified is False
        assert source.transcript_tool
    for directory in (FULL_DIR, EXAMPLES_DIR):
        assert {s["transcript_review"]["status"] for s in manifest_of(directory)["sources"]} == {"unverified"}


# --- Paths and reproducibility ---------------------------------------------------------------


@pytest.mark.parametrize("path", ["C:/data/a.flac", "/abs/a.flac", "audio\\a.flac", "../outside/a.flac", "audio/../../a.flac"])
def test_manifest_paths_must_be_relative_with_forward_slashes(workspace, path):
    data = manifest_of(workspace[2])
    data["samples"][1]["audio_path"] = path

    assert "invalid_path" in codes(validate_manifest(data))


def test_committed_manifests_use_portable_paths_inside_the_dataset_folder():
    for directory in (FULL_DIR, EXAMPLES_DIR):
        for sample in manifest_of(directory)["samples"]:
            assert sample["audio_path"].startswith("audio/pair-") and sample["audio_path"].endswith(".flac")
            assert "\\" not in sample["audio_path"]


def test_rebuilding_reproduces_a_built_dataset_and_reports_tampering(workspace):
    _, registry, out = workspace
    assert rebuild_differences(out, registry, only_levels=LEVELS) == []

    data = manifest_of(out)
    data["samples"][1]["sha256"] = "0" * 64
    data["samples"][2]["duration_sec"] += 0.5
    del data["samples"][3]
    (out / "manifest.json").write_text(json.dumps(data), encoding="utf-8")

    differences = rebuild_differences(out, registry, only_levels=LEVELS)

    assert len(differences) == 3
    assert any("audio differs" in line for line in differences)
    assert any("metadata differs" in line for line in differences)
    assert any("only one of" in line for line in differences)


def test_committed_example_set_is_reproduced_exactly_by_a_rebuild():
    """Checked on the development machine (Windows, Python 3.14). A failure elsewhere means the audio
    libraries produce different samples there, not necessarily that the data is wrong."""
    assert rebuild_differences(EXAMPLES_DIR, **EXAMPLES_OPTIONS) == []


def test_documented_commands_run_from_the_backend_directory(capsys):
    assert main(["validate", str(EXAMPLES_DIR)]) == 0
    assert main(["validate", str(FULL_DIR), "--metadata-only"]) == 0
    assert main(["transcripts", "status"]) == 0
    output = capsys.readouterr().out
    assert "0 errors, 0 warnings" in output
    assert "unverified [automatic_asr_unverified]" in output


# --- Export ----------------------------------------------------------------------------------


def test_export_packages_everything_with_checksums_and_a_hub_readme(workspace, tmp_path):
    root, _, out = workspace
    folder, archive = export_dataset(out, root, tmp_path / "export")

    manifest = manifest_of(folder)
    assert folder.name == f"{manifest['dataset_name']}-{manifest['dataset_version']}"
    for sample in manifest["samples"]:
        assert (folder / sample["audio_path"]).is_file()
    assert (folder / "sources" / "sources.json").is_file()
    assert (folder / "sources" / "synthetic-0.wav").is_file()
    assert (folder / "schema" / "dataset.schema.json").is_file()
    readme = (folder / "README.md").read_text(encoding="utf-8")
    assert readme.startswith("---\nlicense: cc-by-4.0\n")
    assert readme.endswith("# Test card\n")
    assert validate_directory(folder) == []  # the exported copy is itself a valid dataset

    listed = dict(line.split("  ", 1)[::-1] for line in (folder / "SHA256SUMS.txt").read_text(encoding="utf-8").splitlines())
    on_disk = {p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()} - {"SHA256SUMS.txt"}
    assert set(listed) == on_disk
    for name, digest in listed.items():
        assert hashlib.sha256((folder / name).read_bytes()).hexdigest() == digest

    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        assert bundle.testzip() is None
    assert len(names) == len(on_disk) + 1
    assert all(name.startswith(folder.name + "/") for name in names)


def test_export_is_byte_for_byte_repeatable(workspace, tmp_path):
    root, _, out = workspace

    first = export_dataset(out, root, tmp_path / "a")[1].read_bytes()
    second = export_dataset(out, root, tmp_path / "b")[1].read_bytes()

    assert first == second


def test_export_refuses_a_dataset_that_does_not_validate(workspace, tmp_path):
    root, _, out = workspace
    sample = manifest_of(out)["samples"][1]
    (out / sample["audio_path"]).unlink()

    with pytest.raises(ExportError, match="validation error"):
        export_dataset(out, root, tmp_path / "export")

    assert not (tmp_path / "export").exists()


def test_exports_and_generated_audio_are_ignored_by_git():
    ignore = (REGISTRY.parents[2] / ".gitignore").read_text(encoding="utf-8")

    assert "data/export/" in ignore
    assert "data/speakiq-contrastive-v1/audio/" in ignore


# --- Interactive transcript review -----------------------------------------------------------


class Session:
    """Scripted answers for the reviewer, and a record of what was shown and played."""

    def __init__(self, answers):
        self.answers = list(answers)
        self.shown: list[str] = []
        self.played: list[Path] = []

    def ask(self, prompt):
        self.shown.append(prompt)
        return self.answers.pop(0)

    def say(self, text):
        self.shown.append(text)

    def play(self, path):
        self.played.append(path)


def run_review(registry, answers, **kwargs):
    session = Session(answers)
    counts = interactive_review(
        registry, reviewer="Asha", ask=session.ask, say=session.say, play=session.play, today=date(2026, 10, 14), **kwargs
    )
    return counts, session


def test_review_plays_each_clip_and_shows_its_transcript(workspace):
    _, registry, _ = workspace

    counts, session = run_review(registry, ["s", "s", "s"])

    assert counts == {"confirmed": 0, "corrected": 0, "skipped": 3}
    assert [p.name for p in session.played] == ["synthetic-0.wav", "synthetic-1.wav", "synthetic-2.wav"]
    text = "\n".join(session.shown)
    assert "[1/3] synthetic-0" in text and "test signal" in text
    assert {s.transcript_review.status for s in review_status(registry)} == {"unverified"}


def test_confirming_requires_saying_you_listened(workspace):
    _, registry, _ = workspace

    counts, session = run_review(registry, ["c", "no", "p", "c", "yes", "q"])

    sources = {s.source_id: s for s in review_status(registry)}
    assert counts == {"confirmed": 1, "corrected": 0, "skipped": 2}
    assert "Not recorded. Play the clip and listen to all of it first." in session.shown
    assert len([p for p in session.played if p.name == "synthetic-0.wav"]) == 2  # played, then played again
    first = sources["synthetic-0"].transcript_review
    assert (first.status, first.reviewer, first.reviewed_on, first.changed) == ("verified", "Asha", "2026-10-14", False)
    assert sources["synthetic-1"].transcript_review.status == "unverified"


def test_editing_records_the_correction_and_keeps_the_machine_text(workspace):
    _, registry, _ = workspace

    counts, _ = run_review(registry, ["e", "", "e", "corrected signal", "yes", "q"])

    source = next(s for s in review_status(registry) if s.source_id == "synthetic-0")
    assert counts["corrected"] == 1
    assert source.transcript == "corrected signal"
    assert source.transcript_provenance == "manual_verified"
    assert (source.transcript_review.changed, source.transcript_review.asr_transcript) == (True, "test signal")


def test_review_skips_what_is_already_verified_and_needs_a_reviewer(workspace):
    _, registry, _ = workspace
    run_review(registry, ["c", "yes", "q"])

    counts, session = run_review(registry, ["q"])

    assert "[1/2] synthetic-1" in "\n".join(session.shown)
    with pytest.raises(ReviewError, match="reviewer name"):
        interactive_review(registry, reviewer=" ", ask=lambda _: "q", say=lambda _: None, play=None)


def test_unknown_answers_are_asked_again_and_nothing_is_recorded(workspace):
    _, registry, _ = workspace

    counts, session = run_review(registry, ["x", "yes", "q"])

    assert "Please type c, e, p, s or q." in session.shown
    assert counts["confirmed"] == 0
    assert {s.transcript_review.status for s in review_status(registry)} == {"unverified"}
