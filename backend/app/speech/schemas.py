"""Response contract for transcription and word alignment. All times are in seconds."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class TimedSpan(BaseModel):
    start: float = Field(ge=0)
    end: float

    @model_validator(mode="after")
    def _end_not_before_start(self) -> "TimedSpan":
        if self.end < self.start:
            raise ValueError("end must not be before start")
        return self


class RecognizedWord(TimedSpan):
    word: str
    probability: float | None = Field(
        default=None, description="The recognition model's own probability for this word, when it reports one."
    )


class Segment(TimedSpan):
    text: str


class Transcription(BaseModel):
    status: Literal["completed", "no_speech"]
    text: str
    language: str | None
    language_probability: float | None
    duration_sec: float
    engine: str
    model: str
    segments: list[Segment]
    words: list[RecognizedWord]
    word_timestamps: Literal["available", "unavailable"]
    limitations: list[str]


# aligned: the transcript word was recognised at this position; times are for that word.
# substituted: a different word was recognised in its place; times are for the recognised word.
# unaligned: no recognised word could be matched; times are null rather than guessed.
WordAlignmentStatus = Literal["aligned", "substituted", "unaligned"]


class AlignedWord(BaseModel):
    index: int
    word: str
    status: WordAlignmentStatus
    start: float | None = None
    end: float | None = None
    recognized_as: str | None = None
    probability: float | None = None


class Alignment(BaseModel):
    # aligned: every transcript word is aligned. partial: some are. failed: none are.
    status: Literal["aligned", "partial", "failed"]
    transcript_source: Literal["supplied", "transcribed"]
    method: str
    word_count: int
    aligned_count: int
    substituted_count: int
    unaligned_count: int
    coverage: float = Field(description="Share of transcript words with status 'aligned', 0 to 1.")
    words: list[AlignedWord]
    unmatched_recognized: list[RecognizedWord] = Field(
        description="Words the recogniser heard that do not correspond to any transcript word."
    )
    limitations: list[str]


class TranscriptionEngineStatus(BaseModel):
    engine: str
    dependency_installed: bool
    model: str
    device: str
    compute_type: str
    model_loaded: bool
    hf_token_configured: bool
