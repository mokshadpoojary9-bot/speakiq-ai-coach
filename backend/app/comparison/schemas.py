"""Contract for comparing a participant's delivery with a reference delivery of the same text.

The comparison reports measured differences only. It does not decide that a difference is a
flaw, assign severity, or produce coaching; those need validated thresholds that do not exist yet.
All times are in seconds.
"""

from typing import Literal

from pydantic import BaseModel, Field

from ..audio.schemas import AudioFeatures
from ..speech.schemas import Alignment, Transcription


class DeliveryAnalysis(BaseModel):
    """Everything known about one recording. Either speech part may be missing."""

    features: AudioFeatures
    transcription: Transcription | None = None
    alignment: Alignment | None = None


class ComparisonSettings(BaseModel):
    # Word times are accurate to roughly 0.1 s on each side, so smaller gap changes are not reported.
    min_gap_difference_sec: float = Field(default=0.25, gt=0)


class MetricComparison(BaseModel):
    name: str
    unit: str
    basis: Literal["measured", "estimated"]
    reference: float | None
    participant: float | None
    difference: float | None = Field(description="Participant minus reference.")
    ratio: float | None = Field(description="Participant divided by reference.")
    comparable: bool = Field(description="False when the two values cannot fairly be compared; see note.")
    note: str = ""


class Span(BaseModel):
    start: float
    end: float


class WordComparison(BaseModel):
    index: int
    word: str
    reference: Span
    participant: Span
    duration_difference_sec: float


class TimingDifference(BaseModel):
    """A gap between two consecutive transcript words that is clearly longer or shorter than in the reference."""

    kind: Literal["longer_gap", "shorter_gap"]
    after_word_index: int
    after_word: str
    before_word: str
    participant_interval: Span = Field(description="End of the first word to start of the next, in the participant recording.")
    reference_interval: Span
    participant_gap_sec: float
    reference_gap_sec: float
    difference_sec: float
    evidence: str


class WordLevelComparison(BaseModel):
    status: Literal["completed", "unavailable"]
    reason: str = ""
    transcript_word_count: int = 0
    words_compared: int = 0
    gaps_compared: int = 0
    min_gap_difference_sec: float
    words: list[WordComparison] = []
    timing_differences: list[TimingDifference] = []


class ComparisonResult(BaseModel):
    # completed: global and word-level comparisons ran. partial: only the global comparison ran.
    status: Literal["completed", "partial"]
    global_metrics: list[MetricComparison]
    not_compared: dict[str, str] = Field(description="Measurements deliberately left out, and why.")
    word_level: WordLevelComparison
    not_implemented: list[str]
    limitations: list[str]
