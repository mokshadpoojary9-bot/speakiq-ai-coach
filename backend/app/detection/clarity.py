"""A clarity estimate shown for information: how fast syllables are produced while speaking, and how
confident the recogniser was in the words. Neither is turned into a finding, because both also depend
on accent, voice, microphone and the recogniser itself."""

from typing import Literal

from pydantic import BaseModel, Field

from ..audio.schemas import AudioFeatures
from ..speech.schemas import Transcription

LOW_CONFIDENCE = 0.5

METHOD = (
    "Articulation rate is the number of syllable nuclei (intensity peaks in voiced speech) divided by the speaking "
    "time with pauses removed. Word confidence is the speech recogniser's probability for each recognised word, "
    f"averaged; low-confidence words are those below {LOW_CONFIDENCE}."
)

LIMITATIONS = [
    "This is an estimate, not a measure of how clearly someone speaks: accent, voice, background noise, the microphone "
    "and the recogniser's own errors all change these numbers.",
    "No threshold has been validated with listeners, so no finding or severity is given from it.",
    "Syllable nuclei are counted from the sound and can be over- or under-counted in fast or noisy speech.",
    "It is most useful compared with a reference recording of the same text made with the same microphone.",
]


class ClarityValues(BaseModel):
    articulation_rate_syll_per_sec: float | None = Field(description="Syllable nuclei per second of speech, pauses excluded.")
    mean_word_confidence: float | None = Field(description="Mean recogniser probability of the recognised words, 0 to 1.")
    low_confidence_word_share: float | None = Field(description=f"Share of recognised words below {LOW_CONFIDENCE} probability.")
    words: int = Field(description="Recognised words with a probability.")


class ClarityEstimate(BaseModel):
    status: Literal["estimated", "unavailable"]
    participant: ClarityValues
    reference: ClarityValues | None = Field(default=None, description="The same values for the reference recording, when one was sent.")
    method: str
    limitations: list[str]


def clarity_values(features: AudioFeatures, transcription: Transcription | None) -> ClarityValues:
    rate = features.speaking_rate.articulation_rate_syll_per_sec
    probabilities = [w.probability for w in (transcription.words if transcription else []) if w.probability is not None]
    return ClarityValues(
        articulation_rate_syll_per_sec=round(rate, 2) if rate is not None else None,
        mean_word_confidence=round(sum(probabilities) / len(probabilities), 3) if probabilities else None,
        low_confidence_word_share=round(sum(p < LOW_CONFIDENCE for p in probabilities) / len(probabilities), 3) if probabilities else None,
        words=len(probabilities),
    )


def estimate_clarity(participant: ClarityValues, reference: ClarityValues | None = None) -> ClarityEstimate:
    measured = participant.articulation_rate_syll_per_sec is not None or participant.mean_word_confidence is not None
    return ClarityEstimate(
        status="estimated" if measured else "unavailable",
        participant=participant,
        reference=reference,
        method=METHOD,
        limitations=LIMITATIONS,
    )
