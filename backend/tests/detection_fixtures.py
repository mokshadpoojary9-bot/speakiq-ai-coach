"""Deterministic 'takes' for detection tests: generated audio plus the word times it was built from.

Each word is one voiced pulse, so the audio really does speed up, slow down and pause where the
word times say it does. The rules therefore run on genuine measurements of generated audio, and
expected values in tests follow from the generation parameters.
"""

from dataclasses import dataclass

import numpy as np

from app.audio import extract_features
from app.comparison.schemas import DeliveryAnalysis
from app.speech import align_transcript
from app.speech.schemas import RecognizedWord, Segment, Transcription

from .audio_samples import SR, loaded

BASE_RATE = 2.5  # words per second: 150 words per minute
WORDS = 40


@dataclass
class Take:
    audio: np.ndarray
    words: list[str]
    starts: list[float]
    ends: list[float]

    @property
    def text(self) -> str:
        return " ".join(self.words)


def contour(index: int, base_hz: float, swing_semitones: float) -> float:
    """Pitch of word `index`: a slow rise and fall around `base_hz`, the same shape at any speaking rate."""
    return base_hz * 2 ** (swing_semitones * np.sin(2 * np.pi * index / 10) / 12)


def make_take(
    words: int = WORDS,
    rate=BASE_RATE,
    *,
    pauses: dict[int, float] | None = None,
    base_hz: float = 150.0,
    swing_semitones: float = 3.0,
    amplitude: float = 0.25,
) -> Take:
    """`rate` is words per second, or a function of the word index. `pauses` maps a word index to silence after it."""
    pieces, starts, ends = [], [], []
    now = 0.0
    for i in range(words):
        duration = 1 / (rate(i) if callable(rate) else rate)
        n = int(round(duration * SR))
        t = np.arange(n) / SR
        f0 = contour(i, base_hz, swing_semitones)
        voice = sum(np.sin(2 * np.pi * f0 * k * t) / k for k in range(1, 6))
        pieces.append((amplitude * voice * np.sin(np.pi * t / duration) ** 2).astype(np.float32))
        starts.append(round(now, 4))
        now += n / SR
        ends.append(round(now, 4))
        gap = (pauses or {}).get(i)
        if gap:
            pieces.append(np.zeros(int(round(gap * SR)), dtype=np.float32))
            now += int(round(gap * SR)) / SR
    return Take(np.concatenate(pieces), [f"w{i}" for i in range(words)], starts, ends)


def transcription_of(take: Take, spoken: list[str] | None = None, language: str = "en") -> Transcription:
    """What a recogniser that heard `spoken` (default: the take's own words) at the take's times would return."""
    spoken = spoken or take.words
    words = [RecognizedWord(word=w, start=s, end=e, probability=0.9) for w, s, e in zip(spoken, take.starts, take.ends)]
    return Transcription(
        status="completed",
        text=" ".join(spoken),
        language=language,
        language_probability=0.99,
        duration_sec=round(len(take.audio) / SR, 3),
        engine="test",
        model="test",
        segments=[Segment(start=words[0].start, end=words[-1].end, text=" ".join(spoken))],
        words=words,
        word_timestamps="available",
        limitations=[],
    )


def analysis_of(
    take: Take,
    *,
    transcript: str | None = None,
    spoken: list[str] | None = None,
    audio: np.ndarray | None = None,
    aligned: bool = True,
    source: str = "supplied",
) -> DeliveryAnalysis:
    transcription = transcription_of(take, spoken)
    return DeliveryAnalysis(
        features=extract_features(loaded(take.audio if audio is None else audio)),
        transcription=transcription,
        alignment=align_transcript(transcript or take.text, transcription.words, source=source) if aligned else None,
    )


def noise(n: int, amplitude: float, seed: int = 0) -> np.ndarray:
    return (amplitude * np.random.default_rng(seed).standard_normal(n)).astype(np.float32)
