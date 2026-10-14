"""Dataset commands. Run from backend/ with the virtual environment active:

    python -m app.dataset build                 build the full dataset into data/speakiq-contrastive-v1
    python -m app.dataset build-examples        build the compact example set committed to Git
    python -m app.dataset validate DIR          validate a built dataset (--metadata-only skips audio files)
    python -m app.dataset check                 validate committed files and confirm a rebuild reproduces them
    python -m app.dataset export                package the built dataset for upload (uploads nothing)
    python -m app.dataset export-schema         write the JSON Schema to data/schema
    python -m app.dataset transcripts status    show which transcripts have been verified
    python -m app.dataset transcripts sheet     print a review checklist
    python -m app.dataset transcripts verify SOURCE_ID --reviewer NAME --listened [--text-file FILE]
    python -m app.dataset transcripts review [--reviewer NAME]   play each clip and confirm or fix its transcript
"""

import argparse
import json
import sys
import tempfile
from collections import Counter
from pathlib import Path

from .build import DEFAULT_SEED, build_dataset
from .export import ExportError, export_dataset
from .review import play_audio as interactive_play
from .review import ReviewError, interactive_review, review_sheet, review_status, verify_transcript
from .schema import DatasetManifest
from .validate import validate_directory

DATA_ROOT = Path(__file__).resolve().parents[3] / "data"
REGISTRY = DATA_ROOT / "sources" / "sources.json"
FULL_DIR = DATA_ROOT / "speakiq-contrastive-v1"
EXAMPLES_DIR = DATA_ROOT / "examples"
EXPORT_DIR = DATA_ROOT / "export"
SCHEMA_PATH = DATA_ROOT / "schema" / "dataset.schema.json"
EXAMPLE_SOURCE = "librispeech-5703-47212-0000"
EXAMPLES_OPTIONS = dict(
    only_sources=[EXAMPLE_SOURCE],
    only_levels=("severe",),
    dataset_name="speakiq-contrastive-examples",
    description="Compact example subset of the SpeakIQ contrastive dataset: one speaker, the reference and the most strongly altered sample of each covered flaw category. For inspection and tests, not for training or evaluation.",
)


def schema_json() -> str:
    return json.dumps(DatasetManifest.model_json_schema(), indent=2) + "\n"


def summarize(manifest: DatasetManifest) -> None:
    samples = manifest.samples
    print(f"{manifest.dataset_name} {manifest.dataset_version}: {len(samples)} samples, {len(manifest.pairs)} pairs, {len(manifest.sources)} sources")
    print("  by origin:   ", dict(Counter(s.data_origin for s in samples)))
    print("  by category: ", dict(Counter(s.flaw_category or "reference" for s in samples)))
    print("  by split:    ", dict(Counter(s.split for s in samples)))
    print(f"  total audio:  {sum(s.duration_sec for s in samples):.1f} s")
    print("  transcripts: ", dict(Counter(s.transcript_provenance for s in manifest.sources)))
    checks = [s.measured.support_check for s in samples if s.measured and s.measured.support_check]
    print("  automatic support checks:", dict(Counter(str(c.supported) for c in checks)))
    for sample in samples:
        check = sample.measured.support_check if sample.measured else None
        if check and check.supported is False:
            print(f"    not supported: {sample.sample_id} ({check.metric}: reference {check.reference_value}, sample {check.sample_value})")


def report(root: Path, check_files: bool) -> int:
    issues = validate_directory(root, check_files=check_files)
    for issue in issues:
        print(issue)
    errors = sum(issue.level == "error" for issue in issues)
    mode = "manifest and audio files" if check_files else "manifest only"
    print(f"Validated {root} ({mode}): {errors} errors, {len(issues) - errors} warnings")
    return 1 if errors else 0


def rebuild_differences(committed_dir: Path, registry: Path = REGISTRY, **build_options) -> list[str]:
    """Rebuild into a temporary folder and list every way the result differs from the committed manifest."""
    committed = DatasetManifest.model_validate_json((committed_dir / "manifest.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory() as scratch:
        rebuilt = build_dataset(registry, Path(scratch), seed=committed.seed, **build_options)
    differences: list[str] = []
    before = {s.sample_id: s for s in committed.samples}
    after = {s.sample_id: s for s in rebuilt.samples}
    for sample_id in sorted(before.keys() ^ after.keys()):
        differences.append(f"{sample_id}: present in only one of the committed and rebuilt manifests")
    for sample_id in sorted(before.keys() & after.keys()):
        if before[sample_id].sha256 != after[sample_id].sha256:
            differences.append(f"{sample_id}: audio differs (sha256)")
        elif before[sample_id] != after[sample_id]:
            differences.append(f"{sample_id}: audio identical but metadata differs")
    if not differences and committed != rebuilt:
        differences.append("dataset-level metadata differs")
    return differences


def check() -> int:
    """Everything a fresh checkout can verify without the ignored audio folder."""
    failed = 0
    print("1. Example set, manifest and audio files")
    failed += report(EXAMPLES_DIR, check_files=True)
    print("2. Full manifest (its audio is not in Git)")
    failed += report(FULL_DIR, check_files=False)
    print("3. JSON Schema file is current")
    current = SCHEMA_PATH.read_text(encoding="utf-8") == schema_json()
    print("   yes" if current else "   NO: run `python -m app.dataset export-schema`")
    failed += 0 if current else 1
    for label, directory, options in (("example set", EXAMPLES_DIR, EXAMPLES_OPTIONS), ("full dataset", FULL_DIR, {})):
        print(f"4. Rebuilding the {label} and comparing with the committed manifest")
        differences = rebuild_differences(directory, **options)
        for line in differences[:20]:
            print("   " + line)
        print(f"   {len(differences)} difference(s)" if differences else "   identical: every sample's audio checksum and metadata match")
        failed += 1 if differences else 0
    print("CHECK PASSED" if not failed else "CHECK FAILED")
    return 1 if failed else 0


def transcripts(args: argparse.Namespace) -> int:
    if args.action == "status":
        for source in review_status(REGISTRY):
            review = source.transcript_review
            who = f" by {review.reviewer} on {review.reviewed_on}" if review.reviewer else ""
            print(f"{source.source_id}: {review.status}{who} [{source.transcript_provenance}]")
        return 0
    if args.action == "sheet":
        print(review_sheet(REGISTRY))
        return 0
    if args.action == "review":
        reviewer = args.reviewer or input("Your name, recorded with each review: ").strip()
        try:
            counts = interactive_review(REGISTRY, reviewer=reviewer, play=None if args.no_play else interactive_play)
        except ReviewError as error:
            print(f"Not recorded: {error}")
            return 1
        print(f"Done: {counts['confirmed']} confirmed, {counts['corrected']} corrected, {counts['skipped']} skipped.")
        if counts["confirmed"] or counts["corrected"]:
            print("Now run `python -m app.dataset build` and `build-examples` so the manifests carry the reviewed transcripts.")
        return 0
    text = args.text_file.read_text(encoding="utf-8") if args.text_file else None
    try:
        source = verify_transcript(
            REGISTRY, args.source_id, reviewer=args.reviewer or "", listened=args.listened, corrected_text=text, notes=args.notes
        )
    except ReviewError as error:
        print(f"Not recorded: {error}")
        return 1
    change = "corrected" if source.transcript_review.changed else "confirmed unchanged"
    print(f"Recorded: {source.source_id} {change} by {source.transcript_review.reviewer}.")
    print("Now run `python -m app.dataset build` and `build-examples` so the manifests carry the reviewed transcript.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m app.dataset", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", required=True)
    for name in ("build", "build-examples"):
        sub = commands.add_parser(name)
        sub.add_argument("--out", type=Path, default=FULL_DIR if name == "build" else EXAMPLES_DIR)
        sub.add_argument("--seed", type=int, default=DEFAULT_SEED)
    validate = commands.add_parser("validate")
    validate.add_argument("directory", type=Path)
    validate.add_argument("--metadata-only", action="store_true")
    commands.add_parser("check")
    commands.add_parser("export-schema")
    export = commands.add_parser("export")
    export.add_argument("--out", type=Path, default=EXPORT_DIR)
    review = commands.add_parser("transcripts")
    review.add_argument("action", choices=("status", "sheet", "verify", "review"))
    review.add_argument("source_id", nargs="?")
    review.add_argument("--reviewer")
    review.add_argument("--listened", action="store_true", help="Confirms the reviewer listened to the audio.")
    review.add_argument("--text-file", type=Path, help="Corrected transcript. Omit to confirm the current text.")
    review.add_argument("--notes", default="")
    review.add_argument("--no-play", action="store_true", help="Do not open clips automatically (review only).")
    args = parser.parse_args(argv)

    if args.command == "export-schema":
        SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
        SCHEMA_PATH.write_text(schema_json(), encoding="utf-8", newline="\n")
        print(f"Wrote {SCHEMA_PATH}")
        return 0
    if args.command == "validate":
        return report(args.directory, check_files=not args.metadata_only)
    if args.command == "check":
        return check()
    if args.command == "transcripts":
        if args.action == "verify" and not args.source_id:
            parser.error("transcripts verify needs a SOURCE_ID")
        return transcripts(args)
    if args.command == "export":
        try:
            folder, archive = export_dataset(FULL_DIR, DATA_ROOT, args.out)
        except ExportError as error:
            print(f"Export refused: {error}")
            return 1
        files = sum(1 for p in folder.rglob("*") if p.is_file())
        print(f"Exported {files} files to {folder}")
        print(f"Archive: {archive} ({archive.stat().st_size / 1e6:.1f} MB)")
        print("Nothing was uploaded. See data/HOSTING.md for the upload steps.")
        return 0

    if args.command == "build":
        manifest = build_dataset(REGISTRY, args.out, seed=args.seed)
    else:
        manifest = build_dataset(REGISTRY, args.out, seed=args.seed, **EXAMPLES_OPTIONS)
    summarize(manifest)
    return report(args.out, check_files=True)


if __name__ == "__main__":
    sys.exit(main())
