"""Packages a built, validated dataset for upload to a public host. Does not upload anything."""

import hashlib
import shutil
import zipfile
from pathlib import Path

from .schema import DatasetManifest
from .validate import validate_directory

# Every archive entry gets this timestamp so that two exports of the same data are byte-identical.
FIXED_ZIP_TIME = (2026, 1, 1, 0, 0, 0)

HUB_FRONT_MATTER = """---
license: cc-by-4.0
language:
- en
pretty_name: SpeakIQ Contrastive Speech Dataset
size_categories:
- n<1K
task_categories:
- audio-classification
tags:
- speech
- prosody
- speech-delivery
- transformed-audio
- librispeech
---

"""


class ExportError(RuntimeError):
    pass


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def export_dataset(dataset_dir: Path, data_root: Path, out_dir: Path) -> tuple[Path, Path]:
    """Create `<out_dir>/<name>-<version>/` and a matching .zip. Returns (folder, zip).

    Refuses to export a dataset that does not pass validation with its audio files present.
    """
    issues = [issue for issue in validate_directory(dataset_dir, check_files=True) if issue.level == "error"]
    if issues:
        listing = "\n".join(str(issue) for issue in issues[:10])
        raise ExportError(
            f"{dataset_dir} has {len(issues)} validation error(s); build it first with `python -m app.dataset build`.\n{listing}"
        )
    manifest = DatasetManifest.model_validate_json((dataset_dir / "manifest.json").read_text(encoding="utf-8"))
    name = f"{manifest.dataset_name}-{manifest.dataset_version}"
    folder = out_dir / name
    if folder.exists():
        shutil.rmtree(folder)
    folder.mkdir(parents=True)

    shutil.copy2(dataset_dir / "manifest.json", folder / "manifest.json")
    for sample in manifest.samples:
        target = folder / sample.audio_path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(dataset_dir / sample.audio_path, target)
    (folder / "sources").mkdir()
    shutil.copy2(data_root / "sources" / "sources.json", folder / "sources" / "sources.json")
    for source in manifest.sources:
        shutil.copy2(data_root / "sources" / source.audio_path, folder / "sources" / source.audio_path)
    (folder / "schema").mkdir()
    shutil.copy2(data_root / "schema" / "dataset.schema.json", folder / "schema" / "dataset.schema.json")
    card = (data_root / "DATASET_CARD.md").read_text(encoding="utf-8")
    # Hugging Face reads README.md as the dataset card and needs the metadata block at the top.
    (folder / "README.md").write_text(HUB_FRONT_MATTER + card, encoding="utf-8", newline="\n")

    files = sorted(p for p in folder.rglob("*") if p.is_file())
    sums = "".join(f"{_sha256(p)}  {p.relative_to(folder).as_posix()}\n" for p in files)
    (folder / "SHA256SUMS.txt").write_text(sums, encoding="utf-8", newline="\n")

    archive = out_dir / f"{name}.zip"
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for path in sorted(p for p in folder.rglob("*") if p.is_file()):
            info = zipfile.ZipInfo(f"{name}/{path.relative_to(folder).as_posix()}", date_time=FIXED_ZIP_TIME)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            bundle.writestr(info, path.read_bytes())
    return folder, archive
