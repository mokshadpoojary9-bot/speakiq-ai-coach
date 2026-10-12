"""Versioned schema for the SpeakIQ contrastive speech dataset. All times are in seconds.

Structural rules live here. Cross-record rules (duplicates, timestamps against durations,
transcripts, splits, files on disk) live in `validate.py` so each problem is reported separately.
"""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

SCHEMA_VERSION = "1.0.0"

DeliveryCondition = Literal["reference", "flawed"]

FlawCategory = Literal[
    "excessive_pauses",
    "rushed_delivery",
    "slow_delivery",
    "filler_words",
    "uneven_pacing",
    "pitch_monotony",
    "unclear_articulation",
]

# Ordered from no flaw to most flawed. `near_reference` is a barely altered sample.
Severity = Literal["none", "near_reference", "mild", "moderate", "severe"]
SEVERITY_RANK: dict[str, int] = {"none": 0, "near_reference": 1, "mild": 2, "moderate": 3, "severe": 4}

# real_recording: a human recording, only format-converted.
# transformed_real: a human recording altered by signal processing.
# synthetic: generated speech (for example text-to-speech). No human spoke it.
DataOrigin = Literal["real_recording", "transformed_real", "synthetic"]

# generated_by_construction: the label is known because the build applied that change.
# manual: a person listened and labelled. automatic_estimate: produced by an algorithm.
LabelProvenance = Literal["generated_by_construction", "manual", "automatic_estimate"]

# by_construction: the transform directly produces the labelled property.
# proxy: the transform only imitates an acoustic correlate of the labelled property.
LabelSupport = Literal["by_construction", "proxy"]

TranscriptProvenance = Literal["automatic_asr_unverified", "manual_verified", "source_text"]

SplitName = Literal["train", "validation", "test"]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FlawInterval(Strict):
    start: float
    end: float
    label: str = Field(min_length=1)
    detail: str = ""


class SourceRecording(Strict):
    source_id: str = Field(min_length=1)
    speaker_id: str = Field(min_length=1)
    speaker_kind: Literal["human", "synthetic"]
    audio_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    origin: str = Field(min_length=1)
    description: str = Field(min_length=1)
    license: str = Field(min_length=1)
    attribution: str = Field(min_length=1)
    url: str = ""
    transcript: str = Field(min_length=1)
    transcript_provenance: TranscriptProvenance
    transcript_tool: str = ""
    notes: str = ""


class Generation(Strict):
    method: str = Field(min_length=1)
    parameters: dict[str, float | int | str | list[float]] = {}
    tool: str = Field(min_length=1)


class Annotation(Strict):
    label_provenance: LabelProvenance
    label_support: LabelSupport | None = None
    annotator: str | None = None
    notes: str = ""


class SupportCheck(Strict):
    """Whether an independent automatic measurement moves the way the label implies."""

    metric: str
    reference_value: float | None
    sample_value: float | None
    expectation: str
    supported: bool | None = Field(description="Null when no automatic check exists for this category.")


class Measured(Strict):
    """Automatic estimates from the SpeakIQ audio pipeline. These are not labels."""

    provenance: Literal["automatic_estimate"] = "automatic_estimate"
    tool: str
    pitch_median_hz: float | None = None
    pitch_range_semitones: float | None = None
    total_silence_sec: float | None = None
    internal_pause_count: int | None = None
    syllable_rate_estimate_per_sec: float | None = None
    spectral_centroid_hz: float | None = None
    peak_amplitude: float | None = None
    support_check: SupportCheck | None = None


class Sample(Strict):
    sample_id: str = Field(pattern=r"^[a-z0-9][a-z0-9_.-]*$")
    pair_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    speaker_id: str = Field(min_length=1)
    audio_path: str = Field(min_length=1)
    reference_audio_path: str = Field(min_length=1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    duration_sec: float = Field(gt=0)
    sample_rate_hz: int = Field(gt=0)
    transcript: str = Field(min_length=1)
    transcript_differs_from_reference: bool = False
    transcript_difference_note: str = ""
    delivery_condition: DeliveryCondition
    data_origin: DataOrigin
    flaw_category: FlawCategory | None
    severity: Severity
    severity_rank: int = Field(ge=0, le=4)
    flaw_intervals: list[FlawInterval]
    generation: Generation
    annotation: Annotation
    measured: Measured | None = None
    split: SplitName


class Pair(Strict):
    """One reference delivery and every flawed delivery derived from the same recording."""

    pair_id: str = Field(min_length=1)
    source_id: str = Field(min_length=1)
    reference_sample_id: str = Field(min_length=1)
    transcript: str = Field(min_length=1)


class SplitInfo(Strict):
    strategy: str = Field(min_length=1)
    seed: int
    unit: Literal["speaker"]
    train: list[str]
    validation: list[str]
    test: list[str]
    notes: str = ""


class DatasetManifest(Strict):
    schema_version: Literal["1.0.0"]
    dataset_name: str = Field(min_length=1)
    dataset_version: str = Field(pattern=r"^\d+\.\d+\.\d+$")
    description: str = Field(min_length=1)
    license: str = Field(min_length=1)
    built_with: str = Field(min_length=1)
    seed: int
    audio_format: str = Field(min_length=1)
    flaw_categories_covered: list[FlawCategory]
    flaw_categories_not_covered: dict[str, str]
    sources: list[SourceRecording]
    pairs: list[Pair]
    samples: list[Sample]
    splits: SplitInfo
