"""Stress tests: unusual but plausible uploads must give honest results or clear errors, never a crash."""

import io
import math

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from app.audio import AudioError, extract_features, load_audio
from app.config import Settings
from app.main import create_app

from .audio_samples import SR, encode, loaded, silence, syllables, tone
from .speech_fakes import FakeModel, transcriber_with

client = TestClient(create_app(Settings(), transcriber=transcriber_with(FakeModel([]))))


def noise(duration_sec: float, amplitude: float, seed: int = 0, sample_rate: int = SR) -> np.ndarray:
    return (amplitude * np.random.default_rng(seed).standard_normal(int(duration_sec * sample_rate))).astype(np.float32)


def assert_well_formed(result) -> None:
    """Every number that is reported is finite, and every interval lies inside the recording."""
    duration = result.audio.duration_sec
    for series in (result.energy.series, result.pitch.series, result.spectral.centroid):
        if series is not None:
            assert all(v is None or math.isfinite(v) for v in series.values)
    for pause in result.pauses.intervals:
        assert 0 <= pause.start < pause.end <= duration + 1e-6
    assert all(math.isfinite(v) for v in result.mfcc.mean + result.mfcc.std)
    assert all(0 <= p <= 1 for p in result.waveform.peaks)


@pytest.mark.parametrize("sample_rate", [8_000, 11_025, 16_000, 22_050, 32_000, 44_100, 48_000, 96_000])
def test_any_common_sample_rate_gives_the_same_pitch_and_duration(sample_rate):
    result = extract_features(loaded(tone(220, 1.5, sample_rate=sample_rate), sample_rate=sample_rate))

    assert result.audio.sample_rate_hz == sample_rate
    assert result.audio.analysis_sample_rate_hz == SR
    assert result.audio.duration_sec == pytest.approx(1.5, abs=0.01)
    assert result.pitch.median_hz == pytest.approx(220, abs=2)
    assert_well_formed(result)


def test_unusual_sample_rate_is_resampled_exactly():
    result = extract_features(loaded(tone(220, 1.0, sample_rate=12_345), sample_rate=12_345))

    assert result.audio.duration_sec == pytest.approx(1.0, abs=0.01)
    assert result.pitch.median_hz == pytest.approx(220, abs=2)


def test_digital_silence_reports_timing_as_unavailable():
    result = extract_features(loaded(silence(2.0)))

    assert result.audio.peak_amplitude == 0
    assert (result.pauses.status, result.speaking_rate.status) == ("unavailable", "unavailable")
    assert result.pitch.voiced_fraction == 0
    assert_well_formed(result)


def test_stereo_channels_that_cancel_out_are_treated_as_silence_not_as_an_error():
    left = tone(220, 1.0)
    result = extract_features(loaded(np.stack([left, -left], axis=1)))

    assert result.audio.channels == 2
    assert result.audio.peak_amplitude == pytest.approx(0, abs=1e-6)
    assert result.pauses.status == "unavailable"


def test_pure_noise_is_not_mistaken_for_voiced_speech():
    result = extract_features(loaded(noise(3.0, 0.1)))

    assert result.pitch.status == "measured"
    assert result.pitch.voiced_fraction < 0.1
    assert result.pauses.internal_pause_count == 0
    assert_well_formed(result)


def test_light_background_noise_does_not_hide_a_pause():
    speech = np.concatenate([syllables(8), silence(1.0), syllables(8)])
    result = extract_features(loaded(speech + noise(len(speech) / SR, 0.0005)))

    assert result.pauses.internal_pause_count == 1
    assert result.pauses.intervals[0].start == pytest.approx(2.0, abs=0.1)
    assert result.pitch.median_hz == pytest.approx(150, abs=3)


def test_heavy_background_noise_hides_pauses_and_the_limitation_says_so():
    """Known limitation, pinned here so a change in behaviour is noticed: the silence threshold is
    relative to the loudest frame, so noise above it makes pauses undetectable."""
    speech = np.concatenate([syllables(8), silence(1.0), syllables(8)])
    result = extract_features(loaded(speech + noise(len(speech) / SR, 0.05)))

    assert result.pauses.status == "measured"
    assert result.pauses.internal_pause_count == 0
    assert any("background noise can hide pauses" in text for text in result.pauses.limitations)
    assert_well_formed(result)


def test_clipped_audio_is_analysed_and_its_peak_is_reported_at_full_scale():
    clipped = np.clip(3.0 * tone(220, 1.5, amplitude=0.9), -1.0, 1.0)

    result = extract_features(loaded(clipped))

    assert result.audio.peak_amplitude == pytest.approx(1.0, abs=0.001)
    assert result.pitch.median_hz == pytest.approx(220, abs=2)
    assert_well_formed(result)


def test_samples_beyond_full_scale_in_a_float_file_do_not_break_the_waveform():
    buffer = io.BytesIO()
    sf.write(buffer, 2.5 * tone(220, 1.0, amplitude=1.0), SR, format="WAV", subtype="FLOAT")

    result = extract_features(load_audio(buffer.getvalue(), "loud.wav", max_duration_sec=60))

    assert result.audio.peak_amplitude > 1
    assert max(result.waveform.peaks) == 1.0
    assert_well_formed(result)


def test_non_finite_samples_are_rejected():
    samples = tone(220, 1.0)
    samples[100] = np.nan
    buffer = io.BytesIO()
    sf.write(buffer, samples, SR, format="WAV", subtype="FLOAT")

    with pytest.raises(AudioError) as error:
        load_audio(buffer.getvalue(), "nan.wav", max_duration_sec=60)

    assert error.value.code == "invalid_samples"


@pytest.mark.parametrize("duration", [0.3, 0.35, 0.5, 1.0])
def test_short_clips_at_or_above_the_minimum_are_analysed(duration):
    result = extract_features(loaded(tone(220, duration)))

    assert result.audio.duration_sec == pytest.approx(duration, abs=0.01)
    assert result.energy.status == "measured"
    assert result.pauses.intervals == []
    assert_well_formed(result)


@pytest.mark.parametrize("duration", [0.001, 0.05, 0.29])
def test_clips_below_the_minimum_are_rejected_with_a_clear_code(duration):
    response = client.post("/api/analyze", files={"file": ("short.wav", encode(tone(220, duration)))})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "audio_too_short"


def test_a_wav_header_with_no_samples_is_rejected():
    buffer = io.BytesIO()
    sf.write(buffer, np.zeros(0, dtype=np.float32), SR, format="WAV")

    response = client.post("/api/analyze", files={"file": ("empty.wav", buffer.getvalue())})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "audio_too_short"


@pytest.mark.parametrize(
    ("data", "filename", "status", "code"),
    [
        (b"", "empty.wav", 400, "empty_upload"),
        (b"", "empty.mp3", 400, "empty_upload"),
        (b"plain text, not audio", "notes.txt", 415, "unsupported_audio"),
        (encode(tone(220, 1.0)), "voice.m4a", 415, "unsupported_audio"),
        (encode(tone(220, 1.0)), "clip.webm", 415, "unsupported_audio"),
        (encode(tone(220, 1.0)), "no_extension", 415, "unsupported_audio"),
        (b"ID3\x03\x00\x00\x00\x00\x00\x0fgarbage that is not mpeg audio", "fake.mp3", 415, "undecodable_audio"),
        # The header promises a second of audio but only a few samples follow; what is there is too short.
        (encode(tone(220, 1.0))[:60], "truncated.wav", 400, "audio_too_short"),
        (b"\x00" * 4096, "zeros.flac", 415, "undecodable_audio"),
        (encode(tone(220, 1.0), fmt="FLAC"), "really_flac.txt", 415, "unsupported_audio"),
    ],
    ids=["empty-wav", "empty-mp3", "text", "m4a", "webm", "no-extension", "fake-mp3", "truncated-wav", "zeros-flac", "wrong-extension"],
)
def test_empty_and_unsupported_uploads_get_clear_errors(data, filename, status, code):
    for route in ("/api/features", "/api/transcribe", "/api/align", "/api/analyze"):
        response = client.post(route, files={"file": (filename, data)})

        assert (response.status_code, response.json()["detail"]["code"]) == (status, code), route


def test_a_file_whose_content_and_extension_disagree_is_decoded_by_content():
    """libsndfile detects the real format, so a FLAC named .wav still works."""
    response = client.post("/api/features", files={"file": ("mislabelled.wav", encode(tone(220, 1.0), fmt="FLAC"))})

    assert response.status_code == 200
    assert response.json()["pitch"]["median_hz"] == pytest.approx(220, abs=2)


def test_analyze_survives_every_stress_signal_end_to_end():
    signals = {
        "silence": silence(1.0),
        "noise": noise(1.0, 0.2),
        "clipped": np.clip(5 * tone(220, 1.0), -1, 1),
        "dc_offset": tone(220, 1.0, amplitude=0.2) + 0.5,
        "very_quiet": tone(220, 1.0, amplitude=1e-4),
        "impulse": np.concatenate([silence(0.5), np.ones(1, dtype=np.float32), silence(0.5)]),
    }
    for name, samples in signals.items():
        response = client.post("/api/analyze", files={"file": (f"{name}.wav", encode(samples.astype(np.float32)))})

        assert response.status_code == 200, name
        body = response.json()
        assert body["components"]["features"]["status"] == "completed", name
        assert body["transcription"]["status"] == "no_speech", name  # the fake model hears nothing
        assert body["alignment"] is None, name
