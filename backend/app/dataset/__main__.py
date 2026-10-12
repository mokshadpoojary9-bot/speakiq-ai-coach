"""Dataset commands. Run from backend/:

    python -m app.dataset build              build the full dataset into data/speakiq-contrastive-v1
    python -m app.dataset build-examples     build the compact example set committed to Git
    python -m app.dataset validate DIR       validate a built dataset (add --metadata-only to skip audio files)
    python -m app.dataset export-schema      write the JSON Schema to data/schema
"""

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from .build import DEFAULT_SEED, build_dataset
from .schema import DatasetManifest
from .validate import validate_directory

DATA_ROOT = Path(__file__).resolve().parents[3] / "data"
REGISTRY = DATA_ROOT / "sources" / "sources.json"
FULL_DIR = DATA_ROOT / "speakiq-contrastive-v1"
EXAMPLES_DIR = DATA_ROOT / "examples"
SCHEMA_PATH = DATA_ROOT / "schema" / "dataset.schema.json"
EXAMPLE_SOURCE = "librispeech-5703-47212-0000"


def schema_json() -> str:
    return json.dumps(DatasetManifest.model_json_schema(), indent=2) + "\n"


def summarize(manifest: DatasetManifest) -> None:
    samples = manifest.samples
    print(f"{manifest.dataset_name} {manifest.dataset_version}: {len(samples)} samples, {len(manifest.pairs)} pairs, {len(manifest.sources)} sources")
    print("  by origin:   ", dict(Counter(s.data_origin for s in samples)))
    print("  by category: ", dict(Counter(s.flaw_category or "reference" for s in samples)))
    print("  by split:    ", dict(Counter(s.split for s in samples)))
    print(f"  total audio:  {sum(s.duration_sec for s in samples):.1f} s")
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
    commands.add_parser("export-schema")
    args = parser.parse_args(argv)

    if args.command == "export-schema":
        SCHEMA_PATH.parent.mkdir(parents=True, exist_ok=True)
        SCHEMA_PATH.write_text(schema_json(), encoding="utf-8")
        print(f"Wrote {SCHEMA_PATH}")
        return 0
    if args.command == "validate":
        return report(args.directory, check_files=not args.metadata_only)

    if args.command == "build":
        manifest = build_dataset(REGISTRY, args.out, seed=args.seed)
    else:
        manifest = build_dataset(
            REGISTRY,
            args.out,
            seed=args.seed,
            only_sources=[EXAMPLE_SOURCE],
            only_levels=("severe",),
            dataset_name="speakiq-contrastive-examples",
            description="Compact example subset of the SpeakIQ contrastive dataset: one speaker, the reference and the most strongly altered sample of each covered flaw category. For inspection and tests, not for training or evaluation.",
        )
    summarize(manifest)
    return report(args.out, check_files=True)


if __name__ == "__main__":
    sys.exit(main())
