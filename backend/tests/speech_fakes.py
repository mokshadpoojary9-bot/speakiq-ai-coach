"""Stand-ins for the faster-whisper model, so tests need no model download, token or network."""

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from app.config import Settings
from app.speech import FasterWhisperTranscriber


@dataclass
class FakeWord:
    word: str
    start: float
    end: float
    probability: float = 0.9


@dataclass
class FakeSegment:
    text: str
    start: float
    end: float
    words: list[FakeWord] | None = None


def segment(text: str, start: float, step: float = 0.4) -> FakeSegment:
    """One segment whose words are spaced `step` seconds apart, in faster-whisper's ' word' format."""
    words = [
        FakeWord(f" {token}", round(start + i * step, 3), round(start + i * step + step * 0.8, 3))
        for i, token in enumerate(text.split())
    ]
    return FakeSegment(f" {text}", start, words[-1].end, words)


@dataclass
class FakeModel:
    segments: list[FakeSegment] = field(default_factory=list)
    language: str = "en"
    error: Exception | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    def transcribe(self, samples, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return iter(self.segments), SimpleNamespace(language=self.language, language_probability=0.98765)


def transcriber_with(model: FakeModel, settings: Settings | None = None) -> FasterWhisperTranscriber:
    return FasterWhisperTranscriber(settings or Settings(), model_loader=lambda _: model)


def transcriber_failing_to_load(error: Exception, settings: Settings | None = None) -> FasterWhisperTranscriber:
    def loader(_):
        raise error

    return FasterWhisperTranscriber(settings or Settings(), model_loader=loader)
