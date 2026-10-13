"""Measures how well the comparison recovers changes the dataset is known to contain.

Run from backend/ after `python -m app.dataset build`:

    python -m app.comparison.evaluate

It needs the real transcription model, takes several minutes, and is not part of the test suite.
It reports counts only; it does not tune or change anything.

Two questions are asked of the demonstration dataset:

1. Inserted pauses. Each `excessive_pauses` sample has silences inserted at known times. How many
   are reported as a `longer_gap` whose interval covers more than half of the inserted silence?
2. Controls. `pitch_monotony` and `unclear_articulation` samples have exactly the reference's
   timing, so any timing difference reported for them is a false alarm.
"""

import json
import sys
from pathlib import Path

from ..audio import extract_features, load_audio
from ..config import get_settings
from ..speech import FasterWhisperTranscriber, SpeechError, align_transcript
from .compare import compare_deliveries
from .schemas import DeliveryAnalysis

DATASET = Path(__file__).resolve().parents[3] / "data" / "speakiq-contrastive-v1"
LEVELS = ("near_reference", "mild", "moderate", "severe")
CONTROL_CATEGORIES = ("pitch_monotony", "unclear_articulation")


def main() -> int:
    manifest = json.loads((DATASET / "manifest.json").read_text(encoding="utf-8"))
    samples = {s["sample_id"]: s for s in manifest["samples"]}
    settings = get_settings()
    transcriber = FasterWhisperTranscriber(settings)

    def analyse(sample: dict, transcript: str | None = None) -> tuple[DeliveryAnalysis, str]:
        path = DATASET / sample["audio_path"]
        audio = load_audio(path.read_bytes(), path.name, max_duration_sec=600)
        transcription = transcriber.transcribe(audio.samples, audio.sample_rate, "en")
        text = transcript or transcription.text
        analysis = DeliveryAnalysis(
            features=extract_features(audio, pause_settings=settings.pause_settings),
            transcription=transcription,
            alignment=align_transcript(text, transcription.words),
        )
        return analysis, text

    inserted = recovered = unmatched_longer = shorter = 0
    control_samples = control_false_alarms = 0
    try:
        for source in manifest["sources"]:
            source_id = source["source_id"]
            # Both recordings are aligned to the text recognised in the reference, as /api/compare does.
            reference, text = analyse(samples[f"{source_id}__reference"])
            for level in LEVELS:
                sample = samples[f"{source_id}__excessive_pauses__{level}"]
                result = compare_deliveries(reference, analyse(sample, text)[0])
                longer = [d for d in result.word_level.timing_differences if d.kind == "longer_gap"]
                shorter += sum(d.kind == "shorter_gap" for d in result.word_level.timing_differences)
                matched: set[int] = set()
                for interval in sample["flaw_intervals"]:
                    inserted += 1
                    for index, difference in enumerate(longer):
                        span = difference.participant_interval
                        overlap = min(span.end, interval["end"]) - max(span.start, interval["start"])
                        if overlap > 0.5 * (interval["end"] - interval["start"]):
                            recovered += 1
                            matched.add(index)
                            break
                unmatched_longer += len(longer) - len(matched)
                for category in CONTROL_CATEGORIES:
                    control = samples[f"{source_id}__{category}__{level}"]
                    control_result = compare_deliveries(reference, analyse(control, text)[0])
                    control_samples += 1
                    control_false_alarms += len(control_result.word_level.timing_differences)
    except FileNotFoundError as error:
        print(f"Dataset audio not found ({error.filename}). Run `python -m app.dataset build` first.")
        return 1
    except SpeechError as error:
        print(f"Transcription is not available [{error.code}]: {error.message}")
        return 1

    print(f"Dataset {manifest['dataset_name']} {manifest['dataset_version']}, transcription model '{settings.whisper_model}'")
    print(f"Inserted pauses reported as a longer gap: {recovered} of {inserted}")
    print(f"Longer gaps reported that match no inserted pause: {unmatched_longer}")
    print(f"Shorter gaps reported on pause samples (none were made shorter): {shorter}")
    print(f"Timing differences reported on {control_samples} timing-unchanged control samples: {control_false_alarms}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
