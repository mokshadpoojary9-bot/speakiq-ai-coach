"""Contract for signal quality, alignment status and temporal findings. All times are in seconds."""

from typing import Literal

from pydantic import BaseModel, Field

FindingCategory = Literal[
    "rushed_delivery",
    "slow_delivery",
    "excessive_pause",
    "irregular_pauses",
    "filler_word",
    "uneven_pacing",
    "pitch_monotony",
    "unclear_articulation",
]

# high: measured against a reference over well-aligned words on a clean recording.
# moderate: measured, but without a reference, from recognised words only, or with caveats.
# low: the underlying measurement is itself flagged unreliable for this recording.
EvidenceQuality = Literal["high", "moderate", "low"]

# A magnitude band of the measured deviation. It is not a rating of how the delivery sounds.
Severity = Literal["minor", "moderate", "major"]


class DetectionSettings(BaseModel):
    """Every threshold a rule uses. Defaults are operating points checked against the demonstration
    dataset (see `python -m app.detection.evaluate`); none has been validated with listeners."""

    # A recording is only compared when at least this share of the shared transcript was recognised in it.
    min_alignment_coverage: float = Field(default=0.6, gt=0, le=1)
    min_compared_words: int = Field(default=10, ge=2)
    # Below this share of the transcript compared, reference-based findings are not rated 'high' quality.
    high_quality_compared_fraction: float = Field(default=0.8, gt=0, le=1)
    min_duration_sec: float = Field(default=3.0, gt=0)

    # Pace against a reference: participant speaking time divided by reference speaking time for the same words.
    pace_ratio_threshold: float = Field(default=1.10, gt=1)
    pace_moderate_ratio: float = Field(default=1.20, gt=1)
    pace_major_ratio: float = Field(default=1.35, gt=1)

    # Pace without a reference: recognised words per minute. English only.
    words_per_minute_fast: float = Field(default=200, gt=0)
    words_per_minute_slow: float = Field(default=100, gt=0)
    min_words_for_rate: int = Field(default=20, ge=1)
    min_seconds_for_rate: float = Field(default=8, gt=0)

    # Pauses against a reference: how much longer than the reference's silence at the same words.
    pause_excess_sec: float = Field(default=0.4, gt=0)
    pause_moderate_excess_sec: float = Field(default=0.8, gt=0)
    pause_major_excess_sec: float = Field(default=1.5, gt=0)
    # Pauses without a reference.
    long_pause_sec: float = Field(default=1.5, gt=0)

    # Uneven pacing against a reference: pace measured per run of words, relative to the overall pace.
    pacing_chunk_words: int = Field(default=5, ge=3)
    pacing_min_chunks: int = Field(default=3, ge=2)
    pacing_spread_ratio: float = Field(default=1.5, gt=1)
    pacing_chunk_deviation: float = Field(default=1.25, gt=1)

    # Pitch variation: 5th-95th percentile range in semitones over voiced frames.
    monotony_ratio: float = Field(default=0.7, gt=0, lt=1)
    monotony_range_semitones: float = Field(default=4.0, gt=0)
    min_voiced_frames: int = Field(default=150, ge=1)

    # Non-lexical hesitation sounds only. Words such as 'like' or 'so' are real words and are not counted.
    filler_words: tuple[str, ...] = ("um", "umm", "uh", "uhh", "uhm", "er", "erm", "hmm", "mm", "mhm")
    # Below this recogniser probability a filler is reported as 'possible' with low evidence quality.
    filler_min_probability: float = Field(default=0.5, ge=0, le=1)


class Span(BaseModel):
    start: float
    end: float


class QualityIssue(BaseModel):
    code: str
    # blocking: nothing can be concluded from this recording. warning: findings are less trustworthy.
    level: Literal["blocking", "warning"]
    message: str
    affects: list[str] = Field(default=[], description="Finding categories whose evidence this weakens.")


class SignalQuality(BaseModel):
    usable: bool
    issues: list[QualityIssue]


class AlignmentStatus(BaseModel):
    """Whether, and how, the participant recording could be lined up with the reference."""

    status: Literal["aligned", "unavailable", "no_reference"]
    reason: str = ""
    strategy: str = ""
    transcript_source: Literal["user_provided", "machine_generated", "none"] = "none"
    transcript_word_count: int = 0
    words_compared: int = 0
    words_excluded: dict[str, int] = Field(
        default={}, description="Transcript words left out of the comparison, counted by reason."
    )
    participant_coverage: float | None = None
    reference_coverage: float | None = None
    participant_window: Span | None = None
    reference_window: Span | None = None
    normalization: str = ""


class Evidence(BaseModel):
    feature: str
    unit: str
    participant_value: float | None
    reference_value: float | None = None
    difference: float | None = Field(default=None, description="Participant minus reference.")
    ratio: float | None = Field(default=None, description="Participant divided by reference.")


class RuleUsed(BaseModel):
    rule_id: str
    description: str
    thresholds: dict[str, float | int | str]


class Finding(BaseModel):
    id: str = Field(description="Stable for the same input and settings: rule and interval in milliseconds.")
    category: FindingCategory
    title: str
    start: float = Field(ge=0, description="In the participant recording.")
    end: float
    reference_interval: Span | None = None
    evidence: list[Evidence]
    comparison_method: str
    rule: RuleUsed
    evidence_quality: EvidenceQuality
    severity: Severity | None = None
    severity_basis: str | None = None
    explanation: str
    limitations: list[str]


class RuleReport(BaseModel):
    """What happened to each rule, so 'nothing found' can be told apart from 'could not check'."""

    rule_id: str
    category: FindingCategory
    # triggered: produced findings. not_triggered: checked, nothing over threshold.
    # withheld: could not be checked for this input; see reason. not_supported: no defensible method exists.
    status: Literal["triggered", "not_triggered", "withheld", "not_supported"]
    reason: str = ""
    findings: int = 0
    measured: dict[str, float | int | None] = {}
    thresholds: dict[str, float | int | str] = {}


class DetectionResult(BaseModel):
    signal_quality: SignalQuality
    alignment_status: AlignmentStatus
    findings: list[Finding]
    rules: list[RuleReport]
    limitations: list[str]
