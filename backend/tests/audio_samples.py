"""Synthetic signals with known properties, so tests can check measurements against ground truth."""

import io

import numpy as np
import soundfile as sf

from app.audio import LoadedAudio, load_audio

SR = 16_000


def tone(freq_hz: float, duration_sec: float, *, amplitude: float = 0.5, sample_rate: int = SR) -> np.ndarray:
    t = np.arange(int(duration_sec * sample_rate)) / sample_rate
    return (amplitude * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


def silence(duration_sec: float, *, sample_rate: int = SR) -> np.ndarray:
    return np.zeros(int(duration_sec * sample_rate), dtype=np.float32)


def syllables(count: int, *, rate_per_sec: float = 4.0, f0_hz: float = 150.0, sample_rate: int = SR) -> np.ndarray:
    """A voiced, harmonic sound pulsed `count` times, like a string of evenly spaced syllables."""
    period = 1 / rate_per_sec
    t = np.arange(int(count * period * sample_rate)) / sample_rate
    voice = sum(np.sin(2 * np.pi * f0_hz * k * t) / k for k in range(1, 6))
    envelope = np.sin(np.pi * (t % period) / period) ** 2
    return (0.25 * voice * envelope).astype(np.float32)


def encode(samples: np.ndarray, *, sample_rate: int = SR, fmt: str = "WAV") -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, samples, sample_rate, format=fmt)
    return buffer.getvalue()


def loaded(samples: np.ndarray, *, sample_rate: int = SR) -> LoadedAudio:
    return load_audio(encode(samples, sample_rate=sample_rate), "test.wav", max_duration_sec=600)
