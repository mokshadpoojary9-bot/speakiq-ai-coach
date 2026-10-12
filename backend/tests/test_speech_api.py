import numpy as np
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app

from .audio_samples import encode, silence, syllables, tone
from .speech_fakes import FakeModel, segment, transcriber_failing_to_load, transcriber_with

SECRET = "hf_test_secret_value_123"
WAV = encode(np.concatenate([syllables(8), silence(0.8), syllables(8)]))
SPOKEN = FakeModel([segment("good morning everyone", 0.1), segment("thank you for coming", 2.9)])


def client_for(transcriber, settings: Settings | None = None) -> TestClient:
    settings = settings or Settings()
    return TestClient(create_app(settings, transcriber=transcriber))


def upload(client: TestClient, route: str, data: bytes = WAV, filename: str = "talk.wav", **form):
    return client.post(route, files={"file": (filename, data, "application/octet-stream")}, data=form or None)


ok = client_for(transcriber_with(SPOKEN))
no_dependency = client_for(transcriber_failing_to_load(ImportError("faster_whisper")))


# --- /api/health -------------------------------------------------------------------------------


def test_health_reports_safe_configuration_and_never_the_token():
    settings = Settings(hf_token=SECRET, whisper_model="small")
    response = client_for(transcriber_with(SPOKEN, settings), settings).get("/api/health")

    body = response.json()
    assert body["status"] == "ok"
    assert body["transcription"] == {
        "engine": "faster-whisper",
        "dependency_installed": True,
        "model": "small",
        "device": "cpu",
        "compute_type": "int8",
        "model_loaded": False,
        "hf_token_configured": True,
    }
    assert body["limits"]["supported_extensions"] == [".wav", ".flac", ".ogg", ".mp3"]
    assert SECRET not in response.text


def test_old_unprefixed_routes_are_gone():
    assert ok.get("/health").status_code == 404
    assert upload(ok, "/analysis/features").status_code == 404


def test_openapi_documents_the_api_routes():
    assert ok.get("/docs").status_code == 200
    paths = ok.get("/openapi.json").json()["paths"]
    assert {"/api/health", "/api/features", "/api/transcribe", "/api/align", "/api/analyze"} <= set(paths)


# --- /api/transcribe ---------------------------------------------------------------------------


def test_transcribe_returns_text_and_word_timestamps():
    response = upload(ok, "/api/transcribe", language="en")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    assert body["text"] == "good morning everyone thank you for coming"
    assert body["word_timestamps"] == "available"
    assert body["words"][0] == {"start": 0.1, "end": 0.42, "word": "good", "probability": 0.9}
    assert len(body["segments"]) == 2


def test_transcribe_rejects_bad_uploads_before_touching_the_model():
    model = FakeModel([segment("hello", 0.0)])
    client = client_for(transcriber_with(model))

    cases = [
        (b"", "talk.wav", 400, "empty_upload"),
        (b"definitely not audio", "talk.wav", 415, "undecodable_audio"),
        (WAV, "talk.m4a", 415, "unsupported_audio"),
        (encode(tone(200, 0.1)), "talk.wav", 400, "audio_too_short"),
    ]
    for data, filename, status, code in cases:
        response = upload(client, "/api/transcribe", data, filename)
        assert (response.status_code, response.json()["detail"]["code"]) == (status, code)
    assert model.calls == []


def test_transcribe_reports_a_missing_dependency():
    response = upload(no_dependency, "/api/transcribe")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "missing_dependency"


def test_transcribe_reports_missing_hugging_face_configuration():
    transcriber = transcriber_failing_to_load(RuntimeError("401 Unauthorized: gated repo"))

    response = upload(client_for(transcriber), "/api/transcribe")

    assert response.status_code == 503
    detail = response.json()["detail"]
    assert detail["code"] == "hf_auth_required"
    assert "HF_TOKEN" in detail["message"]


def test_transcribe_reports_a_model_failure():
    response = upload(client_for(transcriber_with(FakeModel(error=RuntimeError("boom")))), "/api/transcribe")

    assert response.status_code == 500
    assert response.json()["detail"]["code"] == "transcription_failed"


def test_validation_errors_use_the_same_error_shape():
    bad_language = upload(ok, "/api/transcribe", language="not a language")
    no_file = ok.post("/api/transcribe", data={"language": "en"})

    for response in (bad_language, no_file):
        assert response.status_code == 422
        assert response.json()["detail"]["code"] == "invalid_request"
    assert bad_language.json()["detail"]["message"].startswith("language:")
    assert no_file.json()["detail"]["message"].startswith("file:")


# --- /api/align --------------------------------------------------------------------------------


def test_align_maps_supplied_transcript_words_to_times():
    response = upload(ok, "/api/align", transcript="Good morning, everyone. Thank you all for coming!")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "partial"
    assert body["transcript_source"] == "supplied"
    assert (body["word_count"], body["aligned_count"], body["unaligned_count"]) == (8, 7, 1)
    assert body["words"][0] == {
        "index": 0, "word": "Good", "status": "aligned", "start": 0.1, "end": 0.42,
        "recognized_as": None, "probability": 0.9,
    }  # fmt: skip
    missing = body["words"][5]
    assert (missing["word"], missing["status"], missing["start"], missing["end"]) == ("all", "unaligned", None, None)


def test_align_without_a_transcript_uses_the_recognised_text():
    for form in ({}, {"transcript": "   "}):
        body = upload(ok, "/api/align", **form).json()

        assert body["transcript_source"] == "transcribed"
        assert body["status"] == "aligned"
        assert body["word_count"] == 7


def test_align_reports_an_error_when_no_speech_was_recognised():
    response = upload(client_for(transcriber_with(FakeModel([]))), "/api/align", transcript="hello there")

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "no_word_timestamps"


def test_align_reports_a_failed_alignment_without_inventing_times():
    body = upload(ok, "/api/align", transcript="completely unrelated words that were never said at all").json()

    assert body["status"] == "failed"
    assert body["coverage"] == 0
    assert all(word["start"] is None for word in body["words"])


def test_align_passes_on_transcription_errors():
    assert upload(no_dependency, "/api/align", transcript="hello").json()["detail"]["code"] == "missing_dependency"


# --- /api/analyze ------------------------------------------------------------------------------


def test_analyze_runs_features_transcription_and_alignment():
    response = upload(ok, "/api/analyze", transcript="good morning everyone thank you for coming")

    assert response.status_code == 200
    body = response.json()
    assert body["is_demo"] is False
    assert {name: part["status"] for name, part in body["components"].items()} == {
        "features": "completed",
        "transcription": "completed",
        "alignment": "completed",
    }
    assert body["features"]["pauses"]["internal_pause_count"] == 1  # measured from the real signal
    assert body["features"]["transcript_rate"]["word_count"] == 7
    assert body["transcription"]["text"] == "good morning everyone thank you for coming"
    assert body["alignment"]["status"] == "aligned"


def test_analyze_still_returns_features_when_transcription_is_unavailable():
    response = upload(no_dependency, "/api/analyze", transcript="good morning")

    assert response.status_code == 200
    body = response.json()
    assert body["features"]["pitch"]["status"] == "measured"
    assert body["transcription"] is None
    assert body["alignment"] is None
    assert body["components"]["transcription"]["status"] == "unavailable"
    assert body["components"]["transcription"]["code"] == "missing_dependency"
    assert body["components"]["alignment"]["code"] == "transcription_required"


def test_analyze_distinguishes_a_model_failure_and_missing_speech():
    failed = upload(client_for(transcriber_with(FakeModel(error=RuntimeError("boom")))), "/api/analyze").json()
    assert failed["components"]["transcription"]["status"] == "failed"

    quiet = upload(client_for(transcriber_with(FakeModel([]))), "/api/analyze").json()
    assert quiet["transcription"]["status"] == "no_speech"
    assert quiet["alignment"] is None
    assert quiet["components"]["alignment"]["status"] == "unavailable"


def test_analyze_rejects_invalid_audio():
    response = upload(ok, "/api/analyze", b"nope", "talk.wav")

    assert response.status_code == 415
    assert response.json()["detail"]["code"] == "undecodable_audio"
