"""Runs the detection rules over the demonstration dataset and tabulates what they report.

Run from backend/ after `python -m app.dataset build`:

    python -m app.detection.evaluate [--cache FILE]

It needs the real transcription model, takes several minutes, and is not part of the test suite.
`--cache` stores the per-recording analyses so the rules can be re-run instantly while the audio
and model are unchanged; samples missing from the cache are analysed and added. It reports counts only and never changes a threshold.

Each flawed sample is analysed against its own reference recording, as `POST /api/analyze` does
with a `reference` file and no transcripts. The table shows, for every flaw category and
parameter tier in the dataset, how many of the samples produced each finding category. Samples
whose labelled flaw matches a rule should trigger it; everything else in a row is a false alarm.
The dataset's flaws are signal-processing transforms, so this shows how the rules behave, not
how accurate they are on natural speech.
"""

import argparse
import json
import pickle
import sys
from collections import Counter, defaultdict
from pathlib import Path

from ..audio import extract_features, load_audio
from ..comparison.schemas import DeliveryAnalysis
from ..config import get_settings
from ..speech import FasterWhisperTranscriber, SpeechError, align_transcript
from .rules import run_detection
from .schemas import DetectionSettings

DATASET = Path(__file__).resolve().parents[3] / "data" / "speakiq-contrastive-v1"
LEVELS = ("near_reference", "mild", "moderate", "severe")
EXPECTED = {
    "excessive_pauses": {"excessive_pause"},
    "rushed_delivery": {"rushed_delivery"},
    "slow_delivery": {"slow_delivery"},
    "uneven_pacing": {"uneven_pacing"},
    "pitch_monotony": {"pitch_monotony"},
    "filler_words": {"filler_word"},
    "unclear_articulation": set(),  # no rule exists for it, by design
}


def analyse_dataset(manifest: dict, done: frozenset[str] = frozenset()) -> dict[str, tuple[DeliveryAnalysis, DeliveryAnalysis]]:
    settings = get_settings()
    transcriber = FasterWhisperTranscriber(settings)
    samples = {s["sample_id"]: s for s in manifest["samples"]}

    def analyse(sample: dict, transcript: str | None = None) -> tuple[DeliveryAnalysis, str]:
        path = DATASET / sample["audio_path"]
        audio = load_audio(path.read_bytes(), path.name, max_duration_sec=600)
        transcription = transcriber.transcribe(audio.samples, audio.sample_rate, "en")
        text = transcript or transcription.text
        features = extract_features(audio, None, settings.pause_settings, settings.pitch_settings)
        return DeliveryAnalysis(features=features, transcription=transcription, alignment=align_transcript(text, transcription.words)), text

    analyses = {}
    for source in manifest["sources"]:
        if all(s["sample_id"] in done for s in manifest["samples"] if s["source_id"] == source["source_id"]):
            continue
        reference, text = analyse(samples[f"{source['source_id']}__reference"])
        for sample in manifest["samples"]:
            if sample["source_id"] == source["source_id"] and sample["sample_id"] not in done:
                analyses[sample["sample_id"]] = (reference, reference if sample["severity"] == "none" else analyse(sample, text)[0])
    return analyses


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--cache", type=Path)
    args = parser.parse_args(argv)

    manifest = json.loads((DATASET / "manifest.json").read_text(encoding="utf-8"))
    samples = {s["sample_id"]: s for s in manifest["samples"]}
    cached = pickle.loads(args.cache.read_bytes()) if args.cache and args.cache.exists() else {}
    analyses = {k: v for k, v in cached.items() if k in samples}
    if analyses.keys() != samples.keys():
        try:
            analyses |= analyse_dataset(manifest, frozenset(analyses))
        except FileNotFoundError as error:
            print(f"Dataset audio not found ({error.filename}). Run `python -m app.dataset build` first.")
            return 1
        except SpeechError as error:
            print(f"Transcription is not available [{error.code}]: {error.message}")
            return 1
        if args.cache:
            args.cache.write_bytes(pickle.dumps(analyses))

    settings = DetectionSettings()
    rows: dict[tuple[str, str], Counter] = defaultdict(Counter)
    severities: dict[tuple[str, str], Counter] = defaultdict(Counter)
    withheld: Counter = Counter()
    hits = expected_total = false_alarms = 0
    fillers_inserted = 0
    fillers_found: Counter = Counter()  # inserted fillers overlapped by a finding, per rule
    fillers_elsewhere: Counter = Counter()  # filler findings away from any inserted filler, per rule
    for sample_id, (reference, participant) in analyses.items():
        sample = samples[sample_id]
        label, level = sample["flaw_category"] or "reference", sample["severity"]
        result = run_detection(participant, reference, transcript_source="machine_generated", settings=settings)
        found = {f.category for f in result.findings}
        key = (label, level)
        rows[key]["samples"] += 1
        rows[key]["not_aligned"] += result.alignment_status.status != "aligned"
        for category in found:
            rows[key][category] += 1
        for finding in result.findings:
            if finding.category in EXPECTED.get(label, set()) and finding.severity:
                severities[key][finding.severity] += 1
        for rule in result.rules:
            if rule.status == "withheld":
                withheld[f"{rule.category}: {rule.reason.split('.')[0]}"] += 1
        wanted = EXPECTED.get(label, set())
        if wanted and level != "near_reference":
            expected_total += 1
            hits += bool(found & wanted)
        false_alarms += len(found - wanted)
        inserted = [i for i in sample["flaw_intervals"] if i["label"].startswith("synthetic_filler")]
        fillers_inserted += len(inserted)
        filler_findings = [f for f in result.findings if f.category == "filler_word"]
        near = lambda f, i: f.end > i["start"] - 0.1 and f.start < i["end"] + 0.1  # noqa: E731
        for interval in inserted:
            rules = {f.rule.rule_id for f in filler_findings if near(f, interval)}
            fillers_found.update(rules)
            fillers_found["either rule"] += bool(rules)
        fillers_elsewhere.update(f.rule.rule_id for f in filler_findings if not any(near(f, i) for i in inserted))

    categories = ["rushed_delivery", "slow_delivery", "excessive_pause", "uneven_pacing", "pitch_monotony", "filler_word"]
    print(f"Dataset {manifest['dataset_name']} {manifest['dataset_version']}; each flawed sample analysed against its reference")
    print(f"{'labelled flaw':22}{'tier':16}{'n':>3}" + "".join(f"{c[:14]:>16}" for c in categories) + "  severity of the expected finding")
    order = [("reference", "none")] + [(c, level) for c in EXPECTED for level in LEVELS]
    for key in order:
        row = rows.get(key)
        if not row:
            continue
        severity = ", ".join(f"{name} x{count}" for name, count in severities[key].items())
        print(f"{key[0]:22}{key[1]:16}{row['samples']:>3}" + "".join(f"{row[c]:>16}" for c in categories) + f"  {severity}")
    print(f"Mild, moderate and severe samples whose labelled flaw was reported: {hits} of {expected_total}")
    print(f"Findings of a category other than the sample's label (false alarms), all {len(analyses)} samples: {false_alarms}")
    if fillers_inserted:
        print(f"Inserted synthetic fillers found, of {fillers_inserted}: " + ", ".join(f"{rule} {n}" for rule, n in sorted(fillers_found.items())))
        print("Filler findings away from any inserted filler: " + (", ".join(f"{rule} {n}" for rule, n in sorted(fillers_elsewhere.items())) or "none"))
    print("Rules withheld (count across samples):")
    for reason, count in withheld.most_common():
        print(f"  {count:>3}  {reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
