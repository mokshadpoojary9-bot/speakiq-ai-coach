"""Builds the contrastive dataset from registered source recordings. Fully deterministic."""

import hashlib
import json
from collections.abc import Callable
from pathlib import Path

import numpy as np
import soundfile as sf

from .. import __version__
from ..audio import LoadedAudio, extract_features, load_audio
from ..audio.loading import ANALYSIS_SAMPLE_RATE
from . import transforms
from .schema import (
    SCHEMA_VERSION,
    SEVERITY_RANK,
    Annotation,
    DatasetManifest,
    FlawInterval,
    Generation,
    Measured,
    Pair,
    Sample,
    SourceRecording,
    SplitInfo,
    SupportCheck,
)
from .splits import split_speakers
from .transforms import Transformed

DATASET_NAME = "speakiq-contrastive"
DATASET_VERSION = "1.0.0"
DEFAULT_SEED = 20261013
AUDIO_FORMAT = "FLAC, 16-bit PCM, mono, 16000 Hz"
TOOL = f"speakiq-ai-coach backend {__version__}"
LEVELS = ("near_reference", "mild", "moderate", "severe")

Transform = Callable[[np.ndarray, int], Transformed]

# Severity is the tier of the generation parameter, from barely altered to strongly altered.
# It is not a perceptual rating: nobody has listened to and graded these samples.
RECIPES: dict[str, dict[str, Transform]] = {
    "excessive_pauses": {
        "near_reference": lambda y, sr: transforms.insert_pauses(y, sr, 0.35, 1),
        "mild": lambda y, sr: transforms.insert_pauses(y, sr, 0.7, 1),
        "moderate": lambda y, sr: transforms.insert_pauses(y, sr, 1.1, 2),
        "severe": lambda y, sr: transforms.insert_pauses(y, sr, 1.8, 3),
    },
    "rushed_delivery": {
        level: (lambda y, sr, f=factor: transforms.change_rate(y, sr, f, "sped_up"))
        for level, factor in zip(LEVELS, (0.95, 0.87, 0.77, 0.65))
    },
    "slow_delivery": {
        level: (lambda y, sr, f=factor: transforms.change_rate(y, sr, f, "slowed_down"))
        for level, factor in zip(LEVELS, (1.05, 1.15, 1.3, 1.5))
    },
    "uneven_pacing": {
        level: (lambda y, sr, c=contrast: transforms.uneven_pacing(y, sr, c))
        for level, contrast in zip(LEVELS, (1.08, 1.2, 1.35, 1.5))
    },
    "pitch_monotony": {
        level: (lambda y, sr, k=keep: transforms.flatten_pitch(y, sr, k))
        for level, keep in zip(LEVELS, (0.85, 0.6, 0.35, 0.1))
    },
    "unclear_articulation": {
        level: (lambda y, sr, c=cutoff: transforms.muffle(y, sr, c))
        for level, cutoff in zip(LEVELS, (5000.0, 3000.0, 1800.0, 1000.0))
    },
}

LABEL_SUPPORT = {category: "by_construction" for category in RECIPES} | {"unclear_articulation": "proxy"}

NOT_COVERED = {
    "filler_words": (
        "No samples. Fillers such as 'um' cannot be created by transforming a recording that does not contain "
        "them, and no licensed recordings with fillers or licensed speech synthesis were available."
    )
}

ANNOTATION_NOTES = {
    "excessive_pauses": "Silence was inserted by the build, so the pause intervals are exact.",
    "rushed_delivery": "The whole recording was time-compressed. Natural rushed speech also changes articulation and pausing, which this does not reproduce.",
    "slow_delivery": "The whole recording was time-stretched. Natural slow speech also changes pausing, which this does not reproduce.",
    "uneven_pacing": "Alternating stretches were sped up and slowed down; the segment boundaries are exact.",
    "pitch_monotony": "Pitch movement around the speaker's median was scaled down; timing and words are unchanged.",
    "unclear_articulation": "PROXY LABEL. Low-pass filtering removes high-frequency consonant detail but is not real mumbled or slurred speech.",
}


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_sources(registry_path: Path) -> list[SourceRecording]:
    data = json.loads(registry_path.read_text(encoding="utf-8"))
    return [SourceRecording.model_validate(item) for item in data["sources"]]


def _write_flac(path: Path, samples: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, samples, ANALYSIS_SAMPLE_RATE, format="FLAC", subtype="PCM_16")


def _read_back(path: Path) -> LoadedAudio:
    return load_audio(path.read_bytes(), path.name, max_duration_sec=3600)


def _measure(audio: LoadedAudio) -> Measured:
    features = extract_features(audio)
    return Measured(
        tool=TOOL,
        pitch_median_hz=features.pitch.median_hz,
        pitch_range_semitones=features.pitch.range_semitones,
        total_silence_sec=round(sum(i.end - i.start for i in features.pauses.intervals), 3),
        internal_pause_count=features.pauses.internal_pause_count,
        syllable_rate_estimate_per_sec=features.speaking_rate.speech_rate_syll_per_sec,
        spectral_centroid_hz=features.spectral.mean_centroid_hz,
        peak_amplitude=features.audio.peak_amplitude,
    )


def _support_check(category: str, result: Transformed, sample: Sample, reference: Sample) -> SupportCheck:
    """Compare an independent measurement with what the label implies. Never used to set labels."""
    measured, ref = sample.measured, reference.measured
    assert measured is not None and ref is not None
    if category == "excessive_pauses":
        inserted = sum(i.end - i.start for i in result.intervals)
        gained = None if None in (measured.total_silence_sec, ref.total_silence_sec) else measured.total_silence_sec - ref.total_silence_sec
        return SupportCheck(
            metric="total_silence_sec",
            reference_value=ref.total_silence_sec,
            sample_value=measured.total_silence_sec,
            expectation=f"detected silence rises by at least 60% of the {inserted:.2f} s inserted",
            supported=None if gained is None else bool(gained >= 0.6 * inserted),
        )
    if category in ("rushed_delivery", "slow_delivery"):
        factor = float(result.parameters["duration_factor"])
        ratio = sample.duration_sec / reference.duration_sec
        return SupportCheck(
            metric="duration_sec",
            reference_value=reference.duration_sec,
            sample_value=sample.duration_sec,
            expectation=f"duration is within 3% of {factor:.2f}x the reference",
            supported=bool(abs(ratio - factor) <= 0.03 * factor),
        )
    if category == "pitch_monotony":
        both = None not in (measured.pitch_range_semitones, ref.pitch_range_semitones)
        return SupportCheck(
            metric="pitch_range_semitones",
            reference_value=ref.pitch_range_semitones,
            sample_value=measured.pitch_range_semitones,
            expectation="measured pitch range is narrower than the reference",
            supported=bool(measured.pitch_range_semitones < ref.pitch_range_semitones) if both else None,
        )
    if category == "unclear_articulation":
        both = None not in (measured.spectral_centroid_hz, ref.spectral_centroid_hz)
        return SupportCheck(
            metric="spectral_centroid_hz",
            reference_value=ref.spectral_centroid_hz,
            sample_value=measured.spectral_centroid_hz,
            expectation="mean spectral centroid is lower than the reference",
            supported=bool(measured.spectral_centroid_hz < ref.spectral_centroid_hz) if both else None,
        )
    return SupportCheck(
        metric="none",
        reference_value=None,
        sample_value=None,
        expectation="no independent automatic check is implemented for this category",
        supported=None,
    )


def build_dataset(
    registry_path: Path,
    out_dir: Path,
    *,
    seed: int = DEFAULT_SEED,
    only_sources: list[str] | None = None,
    only_levels: tuple[str, ...] = LEVELS,
    dataset_name: str = DATASET_NAME,
    description: str | None = None,
) -> DatasetManifest:
    """Write audio under `out_dir/audio` and `out_dir/manifest.json`, and return the manifest."""
    sources_dir = registry_path.parent
    sources = [s for s in load_sources(registry_path) if only_sources is None or s.source_id in only_sources]
    if not sources:
        raise ValueError("no source recordings selected")
    speaker_split = split_speakers([s.speaker_id for s in sources], seed)
    split_of = {speaker: name for name, speakers in speaker_split.items() for speaker in speakers}

    pairs: list[Pair] = []
    samples: list[Sample] = []
    for source in sources:
        source_path = sources_dir / source.audio_path
        if sha256_of(source_path) != source.sha256:
            raise ValueError(f"checksum mismatch for source {source.source_id}: {source_path}")
        original = load_audio(source_path.read_bytes(), source_path.name, max_duration_sec=3600)
        pair_id = f"pair-{source.source_id}"
        split = split_of[source.speaker_id]

        def add(sample_id: str, audio_samples: np.ndarray, **fields) -> tuple[Sample, LoadedAudio]:
            relative = f"audio/{pair_id}/{sample_id}.flac"
            _write_flac(out_dir / relative, audio_samples)
            stored = _read_back(out_dir / relative)  # measure what was actually written
            sample = Sample(
                sample_id=sample_id,
                pair_id=pair_id,
                source_id=source.source_id,
                speaker_id=source.speaker_id,
                audio_path=relative,
                reference_audio_path=f"audio/{pair_id}/{source.source_id}__reference.flac",
                sha256=sha256_of(out_dir / relative),
                duration_sec=round(stored.duration_sec, 4),
                sample_rate_hz=stored.sample_rate,
                transcript=source.transcript,
                split=split,
                measured=_measure(stored),
                **fields,
            )
            samples.append(sample)
            return sample, stored

        reference, reference_audio = add(
            f"{source.source_id}__reference",
            original.samples,
            delivery_condition="reference",
            data_origin="real_recording" if source.speaker_kind == "human" else "synthetic",
            flaw_category=None,
            severity="none",
            severity_rank=0,
            flaw_intervals=[],
            generation=Generation(
                method="format_conversion",
                parameters={"from_sample_rate_hz": original.original_sample_rate, "to_sample_rate_hz": ANALYSIS_SAMPLE_RATE},
                tool="libsndfile, scipy.signal.resample_poly",
            ),
            annotation=Annotation(
                label_provenance="generated_by_construction",
                notes="Used as the reference because it is the unaltered source. Its delivery quality has not been rated by anyone.",
            ),
        )
        pairs.append(Pair(pair_id=pair_id, source_id=source.source_id, reference_sample_id=reference.sample_id, transcript=source.transcript))

        for category, recipe in RECIPES.items():
            for level in only_levels:
                result = recipe[level](reference_audio.samples, reference_audio.sample_rate)
                sample, _ = add(
                    f"{source.source_id}__{category}__{level}",
                    result.samples,
                    delivery_condition="flawed",
                    data_origin="transformed_real" if source.speaker_kind == "human" else "synthetic",
                    flaw_category=category,
                    severity=level,
                    severity_rank=SEVERITY_RANK[level],
                    flaw_intervals=[],
                    generation=Generation(method=result.method, parameters=result.parameters, tool=result.tool),
                    annotation=Annotation(
                        label_provenance="generated_by_construction",
                        label_support=LABEL_SUPPORT[category],
                        notes=ANNOTATION_NOTES[category],
                    ),
                )
                # Intervals are clipped to the stored duration, which can differ by a sample after encoding.
                sample.flaw_intervals = [
                    FlawInterval(
                        start=round(min(i.start, sample.duration_sec), 4),
                        end=round(min(i.end, sample.duration_sec), 4),
                        label=i.label,
                        detail=i.detail,
                    )
                    for i in result.intervals
                ]
                assert sample.measured is not None
                sample.measured.support_check = _support_check(category, result, sample, reference)

    manifest = DatasetManifest(
        schema_version=SCHEMA_VERSION,
        dataset_name=dataset_name,
        dataset_version=DATASET_VERSION,
        description=description
        or "Paired reference and deliberately flawed deliveries of the same recordings, with exact temporal labels. Flawed samples are signal-processing transforms of real recordings.",
        license="Audio: derived from LibriVox public-domain recordings distributed in LibriSpeech (CC BY 4.0). Metadata: CC BY 4.0.",
        built_with=TOOL,
        seed=seed,
        audio_format=AUDIO_FORMAT,
        flaw_categories_covered=list(RECIPES),
        flaw_categories_not_covered=NOT_COVERED,
        sources=sources,
        pairs=pairs,
        samples=samples,
        splits=SplitInfo(
            strategy="Whole speakers are assigned to one split each by a seeded shuffle; every sample of a pair shares its speaker's split.",
            seed=seed,
            unit="speaker",
            **speaker_split,
            notes="" if len(sources) >= 3 else "Fewer than three speakers: no held-out split can be formed without leakage, so all data is in train.",
        ),
    )
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return manifest
