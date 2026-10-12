import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

from .audio_samples import encode, silence, syllables, tone

client = TestClient(create_app(Settings()))


def post(data: bytes, filename: str = "talk.wav", transcript: str | None = None, api: TestClient = client):
    form = {"transcript": transcript} if transcript is not None else None
    return api.post("/analysis/features", files={"file": (filename, data, "application/octet-stream")}, data=form)


def test_returns_real_measurements_for_a_wav_upload():
    signal = np.concatenate([syllables(8), silence(0.8), syllables(8)])

    response = post(encode(signal), transcript="one two three four five six seven eight")

    assert response.status_code == 200
    body = response.json()
    assert body["is_demo"] is False
    assert body["audio"]["filename"] == "talk.wav"
    assert body["audio"]["duration_sec"] == pytest.approx(4.8, abs=0.01)
    assert body["pitch"]["status"] == "measured"
    assert body["pitch"]["median_hz"] == pytest.approx(150, abs=3)
    assert body["pauses"]["internal_pause_count"] == 1
    assert body["speaking_rate"]["status"] == "estimated"
    assert body["speaking_rate"]["syllable_nuclei"] == 16
    assert body["transcript_rate"]["word_count"] == 8
    assert len(body["mfcc"]["mean"]) == 13
    assert body["spectral"]["mean_centroid_hz"] > 0


@pytest.mark.parametrize("fmt, filename", [("FLAC", "talk.flac"), ("OGG", "talk.ogg"), ("MP3", "talk.mp3")])
def test_accepts_other_supported_formats(fmt, filename):
    response = post(encode(tone(220, 1.0), fmt=fmt), filename=filename)

    assert response.status_code == 200
    assert response.json()["pitch"]["median_hz"] == pytest.approx(220, abs=3)


def test_rejects_unsupported_and_undecodable_files():
    assert post(b"hello", filename="notes.pdf").status_code == 415
    undecodable = post(b"RIFF this is not really a wav file", filename="talk.wav")
    assert undecodable.status_code == 415
    assert "could not be decoded" in undecodable.json()["detail"]


def test_rejects_uploads_over_the_size_limit():
    small = TestClient(create_app(Settings(max_upload_mb=0.01)))

    response = post(encode(tone(220, 2.0)), api=small)

    assert response.status_code == 413
    assert "0.01 MB" in response.json()["detail"]


def test_rejects_recordings_over_the_duration_limit():
    short = TestClient(create_app(Settings(max_audio_seconds=1)))

    assert post(encode(tone(220, 2.0)), api=short).status_code == 413


def test_rejects_recordings_that_are_too_short():
    assert post(encode(tone(220, 0.1))).status_code == 400


def test_requires_a_file():
    assert client.post("/analysis/features", data={"transcript": "hello"}).status_code == 422


def test_rejects_an_oversized_transcript():
    assert post(encode(tone(220, 1.0)), transcript="word " * 5000).status_code == 422
