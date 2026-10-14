"""API tests for POST /api/analyze with findings (Milestone 5.2). The speech model is scripted: no downloads."""

import io
from dataclasses import dataclass, field

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

import app.main as main_module
from app.config import Settings
from app.main import create_app

from .audio_samples import SR, encode, silence, tone
from .detection_fixtures import BASE_RATE, WORDS, Take, make_take
from .speech_fakes import FakeModel, FakeSegment, FakeWord, transcriber_failing_to_load, transcriber_with

REFERENCE = make_take()
SAME = make_take(swing_semitones=3.2)  # a second take at the same pace, so it is a different file
RUSHED = make_take(rate=BASE_RATE * 1.5)
PAUSED = make_take(pauses={14: 2.0})
OTHER_WORDS = make_take(rate=BASE_RATE * 1.3, swing_semitones=2.5)


@dataclass
class ScriptedModel(FakeModel):
    """Returns the known words of whichever generated take it is given, recognised by its length."""

    takes: list[Take] = field(default_factory=list)
    spoken: dict[int, list[str]] = field(default_factory=dict)

    def transcribe(self, samples, **kwargs):
        take = next((t for t in self.takes if len(t.audio) == len(samples)), None)
        if take is None:
            self.segments = []
        else:
            words = self.spoken.get(len(take.audio), take.words)
            self.segments = [
                FakeSegment(" " + " ".join(words), take.starts[0], take.ends[-1], [FakeWord(f" {w}", s, e) for w, s, e in zip(words, take.starts, take.ends)])
            ]
        return super().transcribe(samples, **kwargs)


def scripted(**spoken) -> ScriptedModel:
    return ScriptedModel(takes=[REFERENCE, SAME, RUSHED, PAUSED, OTHER_WORDS], spoken=spoken)


def client_with(model=None, settings: Settings | None = None, **kwargs) -> TestClient:
    return TestClient(create_app(settings or Settings(), transcriber=transcriber_with(model or scripted())), **kwargs)


client = client_with()


def analyze(participant: Take | bytes, reference: Take | bytes | None = None, api: TestClient = client, name: str = "take.wav", **form):
    def as_bytes(item):
        return item if isinstance(item, bytes) else encode(item.audio)

    files = {"file": (name, as_bytes(participant))}
    if reference is not None:
        files["reference"] = ("reference.wav", as_bytes(reference))
    return api.post("/api/analyze", files=files, data=form or None)


def rule(body, category):
    return next(r for r in body["rules"] if r["category"] == category)


# --- Successful analyses: findings, no findings, partial -------------------------------------


def test_participant_only_analysis_runs_the_reference_free_rules():
    body = analyze(SAME).json()

    assert body["status"] == "completed_no_findings"
    assert body["findings"] == []
    assert body["alignment_status"]["status"] == "no_reference"
    assert (body["reference"], body["comparison"]) == (None, None)
    assert body["signal_quality"] == {"usable": True, "issues": []}
    assert body["transcripts"]["participant"]["source"] == "machine_generated"
    assert body["transcripts"]["participant"]["human_verified"] is False
    assert rule(body, "uneven_pacing")["status"] == "withheld"
    assert rule(body, "unclear_articulation")["status"] == "not_supported"
    assert body["settings"]["pace_ratio_threshold"] == 1.1
    # Fields the frontend already used are still there.
    assert body["components"]["transcription"]["status"] == "completed"
    assert body["features"]["pitch"]["status"] == "measured"
    assert body["alignment"]["transcript_source"] == "transcribed"


def test_a_rushed_take_against_a_reference_returns_a_measured_finding():
    response = analyze(RUSHED, REFERENCE)

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "completed"
    (finding,) = [f for f in body["findings"] if f["category"] == "rushed_delivery"]
    assert finding["id"] == f"pace_vs_reference:0-{int(round(RUSHED.ends[-1] * 1000))}"
    assert finding["severity"] == "major"
    assert finding["evidence"][0]["ratio"] == pytest.approx(1 / 1.5, abs=0.01)
    assert finding["evidence"][0]["unit"] == "s"
    assert finding["reference_interval"]["end"] == pytest.approx(REFERENCE.ends[-1], abs=0.01)
    assert body["alignment_status"]["status"] == "aligned"
    assert body["alignment_status"]["words_compared"] == WORDS
    assert body["transcripts"]["shared_for_comparison"] == {
        "source": "machine_generated",
        "review_status": "not_reviewed",
        "human_verified": False,
        "text": REFERENCE.text,
        "origin": "reference_recognition",
        "attested_for": [],
    }
    assert body["reference"]["filename"] == "reference.wav"
    assert body["reference"]["signal_quality"]["usable"] is True
    duration = next(m for m in body["comparison"]["global_metrics"] if m["name"] == "duration")
    assert duration["ratio"] == pytest.approx(1 / 1.5, abs=0.01)


def test_a_matching_take_against_a_reference_is_a_valid_no_finding_result():
    body = analyze(SAME, REFERENCE).json()

    assert body["status"] == "completed_no_findings"
    assert body["findings"] == []
    assert {r["status"] for r in body["rules"]} == {"not_triggered", "not_supported"}
    assert body["alignment_status"]["status"] == "aligned"


def test_a_user_transcript_is_recorded_as_user_provided_and_shared_with_the_reference():
    body = analyze(PAUSED, REFERENCE, transcript=REFERENCE.text.upper()).json()

    assert body["transcripts"]["participant"]["source"] == "user_provided"
    assert body["transcripts"]["shared_for_comparison"]["source"] == "user_provided"
    assert body["alignment_status"]["transcript_source"] == "user_provided"
    (pause,) = [f for f in body["findings"] if f["category"] == "excessive_pause"]
    assert pause["start"] == pytest.approx(PAUSED.ends[14], abs=0.06)
    assert pause["evidence"][0]["participant_value"] == pytest.approx(2.0, abs=0.08)
    assert pause["severity"] == "major"


def test_the_api_never_reports_human_verification():
    for response in (analyze(SAME), analyze(RUSHED, REFERENCE, transcript=REFERENCE.text, reference_transcript=REFERENCE.text)):
        transcripts = response.json()["transcripts"]
        assert all(info is None or info["human_verified"] is False for info in transcripts.values())
        assert '"human_verified":true' not in response.text.replace(" ", "")


def test_different_transcripts_withhold_the_comparison_and_say_so():
    other = " ".join(f"x{i}" for i in range(WORDS))
    body = analyze(RUSHED, REFERENCE, transcript=other, reference_transcript=REFERENCE.text).json()

    assert body["status"] == "partial"
    assert body["alignment_status"]["status"] == "unavailable"
    assert "contain different words" in body["alignment_status"]["reason"]
    assert body["comparison"] is None
    assert body["transcripts"]["shared_for_comparison"] is None
    assert not any(f["rule"]["rule_id"].endswith("_vs_reference") for f in body["findings"])
    assert body["limitations"][0].startswith("The reference recording was not used:")


def test_a_reference_of_different_speech_fails_alignment_instead_of_being_compared():
    said = [f"other{i}" for i in range(WORDS)]
    model = scripted(**{})
    model.spoken[len(OTHER_WORDS.audio)] = said
    body = analyze(OTHER_WORDS, REFERENCE, api=client_with(model)).json()

    assert body["status"] == "partial"
    assert body["alignment_status"]["status"] == "unavailable"
    assert "Only 0% of the transcript's words were recognised in the participant recording" in body["alignment_status"]["reason"]
    assert body["alignment_status"]["participant_coverage"] == 0
    assert not any(f["reference_interval"] for f in body["findings"])


def test_transcription_being_unavailable_gives_a_partial_result_with_acoustic_findings_only():
    api = TestClient(create_app(Settings(), transcriber=transcriber_failing_to_load(ImportError("faster_whisper"))))
    body = analyze(PAUSED, api=api).json()

    assert body["status"] == "partial"
    assert body["components"]["transcription"]["code"] == "missing_dependency"
    assert body["transcripts"]["participant"] == {"source": "none", "review_status": "not_reviewed", "human_verified": False, "text": None}
    assert [f["category"] for f in body["findings"]] == ["excessive_pause"]  # measured from the audio alone
    assert rule(body, "filler_word")["status"] == "withheld"
    assert rule(body, "rushed_delivery")["status"] == "withheld"
    assert body["limitations"][0].startswith("Transcription did not run")


def test_unusable_audio_is_reported_not_analysed_as_if_reliable():
    body = analyze(encode(silence(8.0))).json()

    assert body["status"] == "partial"
    assert body["signal_quality"]["usable"] is False
    assert body["signal_quality"]["issues"][0]["code"] == "no_signal"
    assert body["findings"] == []
    assert all(r["status"] in ("withheld", "not_supported") for r in body["rules"])


def test_clipped_audio_is_flagged_in_signal_quality():
    body = analyze(encode(np.clip(RUSHED.audio * 8, -1, 1)), REFERENCE).json()

    codes = [issue["code"] for issue in body["signal_quality"]["issues"]]
    assert "clipping_detected" in codes
    assert body["signal_quality"]["usable"] is True


def test_identical_requests_give_identical_responses():
    first = analyze(RUSHED, REFERENCE, transcript=REFERENCE.text)
    second = analyze(RUSHED, REFERENCE, transcript=REFERENCE.text)

    assert first.json() == second.json()


# --- Invalid input ---------------------------------------------------------------------------


def wav(samples: np.ndarray, sample_rate: int = SR) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, samples, sample_rate, format="WAV")
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("data", "name", "status", "code"),
    [
        (b"", "empty.wav", 400, "empty_upload"),
        (b"plain text", "notes.txt", 415, "unsupported_audio"),
        (b"not really audio", "broken.wav", 415, "undecodable_audio"),
        (wav(tone(200, 0.1)), "short.wav", 400, "audio_too_short"),
        (wav(tone(200, 2.0, sample_rate=4000), 4000), "lowrate.wav", 400, "sample_rate_too_low"),
        (wav(np.stack([tone(200, 2.0)] * 3, axis=1)), "surround.wav", 400, "too_many_channels"),
    ],
    ids=["empty", "unsupported", "undecodable", "too-short", "low-sample-rate", "too-many-channels"],
)
def test_invalid_uploads_return_structured_errors_for_participant_and_reference(data, name, status, code):
    as_participant = analyze(data, name=name)
    as_reference = client.post("/api/analyze", files={"file": ("take.wav", encode(SAME.audio)), "reference": (name, data)})

    for response in (as_participant, as_reference):
        assert response.status_code == status
        assert set(response.json()) == {"detail"}
        assert set(response.json()["detail"]) == {"code", "message"}
        assert response.json()["detail"]["code"] == code


def test_limits_on_size_duration_and_transcript_length():
    small = client_with(settings=Settings(max_upload_mb=0.01))
    brief = client_with(settings=Settings(max_audio_seconds=2))

    assert analyze(SAME, api=small).json()["detail"]["code"] == "upload_too_large"
    assert analyze(SAME, api=brief).json()["detail"]["code"] == "audio_too_long"
    too_long = analyze(SAME, REFERENCE, reference_transcript="word " * 5000)
    assert (too_long.status_code, too_long.json()["detail"]["code"]) == (422, "invalid_request")
    assert client.post("/api/analyze", data={"transcript": "hello"}).json()["detail"]["message"].startswith("file:")


def test_a_processing_failure_returns_a_safe_error_without_internals(monkeypatch):
    def explode(*args, **kwargs):
        raise RuntimeError(r"C:\Users\someone\secret\model.bin HF_TOKEN=hf_abc123")

    monkeypatch.setattr(main_module, "extract_features", explode)
    api = client_with(raise_server_exceptions=False)

    response = analyze(SAME, api=api)

    assert response.status_code == 500
    assert response.json() == {
        "detail": {"code": "processing_failed", "message": "The analysis failed unexpectedly. Nothing was stored. Please try again."}
    }
    for leak in ("secret", "hf_abc123", "Traceback", "RuntimeError", "C:\\"):
        assert leak not in response.text


# --- Contract --------------------------------------------------------------------------------


def test_no_new_route_was_added_and_the_models_are_typed_in_openapi():
    schema = client.get("/openapi.json").json()

    # Still exactly one analysis route of each kind; the only other routes are the optional storage ones (Prompt 8).
    assert set(schema["paths"]) == {
        "/api/health", "/api/features", "/api/transcribe", "/api/align", "/api/analyze", "/api/compare",
        "/api/analyses", "/api/analyses/{analysis_id}",
    }  # fmt: skip
    form = schema["components"]["schemas"]["Body_analyze_api_analyze_post"]["properties"]
    assert set(form) == {
        "file", "reference", "transcript", "reference_transcript", "transcript_reviewed", "reference_transcript_reviewed", "language",
    }  # fmt: skip
    assert schema["components"]["schemas"]["Body_analyze_api_analyze_post"]["required"] == ["file"]
    models = schema["components"]["schemas"]
    for name in ("AnalyzeResponse", "Finding", "Evidence", "RuleReport", "SignalQuality", "QualityIssue", "AlignmentStatus", "DetectionSettings", "TranscriptInfo", "SharedTranscript", "CoachingTip"):
        assert name in models, name
    assert models["Finding"]["properties"]["severity"]["anyOf"][0]["enum"] == ["minor", "moderate", "major"]
    assert models["AnalyzeResponse"]["properties"]["status"]["enum"] == ["completed", "completed_no_findings", "partial"]
    assert set(models["Finding"]["required"]) >= {"id", "category", "start", "end", "evidence", "comparison_method", "rule", "evidence_quality", "explanation", "limitations"}


def test_response_shape_is_stable_for_the_frontend():
    body = analyze(RUSHED, REFERENCE).json()

    assert set(body) == {
        "is_demo", "status", "components", "signal_quality", "features", "transcription", "alignment", "transcripts",
        "reference", "alignment_status", "comparison", "findings", "rules", "coaching", "clarity", "settings", "limitations",
    }  # fmt: skip
    assert set(body["findings"][0]) == {
        "id", "category", "title", "start", "end", "reference_interval", "evidence", "comparison_method", "rule",
        "evidence_quality", "severity", "severity_basis", "explanation", "limitations",
    }  # fmt: skip
    assert {r["category"] for r in body["rules"]} == {
        "rushed_delivery", "slow_delivery", "excessive_pause", "irregular_pauses", "uneven_pacing", "filler_word", "pitch_monotony",
        "unclear_articulation",
    }  # fmt: skip


# --- Transcript provenance and review status (limitations fix) -------------------------------


def test_each_recordings_own_transcript_is_reported_separately_from_the_shared_one():
    """Without supplied text, both recordings are aligned to the reference's recognised words. The participant's
    own entry must still be what was recognised in the participant recording, not the reference's text."""
    model = scripted()
    heard = list(RUSHED.words)
    heard[5] = "misheard"
    model.spoken[len(RUSHED.audio)] = heard
    transcripts = analyze(RUSHED, REFERENCE, api=client_with(model)).json()["transcripts"]

    assert transcripts["participant"]["source"] == "machine_generated"
    assert "misheard" in transcripts["participant"]["text"]
    assert "misheard" not in transcripts["shared_for_comparison"]["text"]
    assert transcripts["shared_for_comparison"]["origin"] == "reference_recognition"
    assert transcripts["reference"]["text"] == REFERENCE.text


def test_a_users_statement_that_they_checked_the_transcript_is_recorded_as_an_attestation_not_verification():
    plain = analyze(RUSHED, REFERENCE, transcript=REFERENCE.text).json()["transcripts"]
    attested = analyze(RUSHED, REFERENCE, transcript=REFERENCE.text, transcript_reviewed="true").json()["transcripts"]

    assert plain["participant"]["review_status"] == "not_reviewed"
    assert attested["participant"]["review_status"] == "user_attested"
    assert attested["participant"]["human_verified"] is False
    # The statement was about the participant recording, so the shared text is not marked reviewed for the comparison.
    assert attested["shared_for_comparison"] | {"text": ""} == {
        "source": "user_provided",
        "review_status": "not_reviewed",
        "human_verified": False,
        "text": "",
        "origin": "participant_transcript",
        "attested_for": ["participant"],
    }
    # The reference's own text was recognised by the model, so nothing the user said applies to it.
    assert (attested["reference"]["source"], attested["reference"]["review_status"]) == ("machine_generated", "not_reviewed")


def test_machine_generated_text_can_never_be_marked_reviewed():
    transcripts = analyze(RUSHED, REFERENCE, transcript_reviewed="true", reference_transcript_reviewed="true").json()["transcripts"]

    for info in transcripts.values():
        assert (info["source"], info["review_status"]) == ("machine_generated", "not_reviewed")


def test_a_reviewed_reference_transcript_is_the_shared_text_and_keeps_its_own_status():
    transcripts = analyze(RUSHED, REFERENCE, reference_transcript=REFERENCE.text, reference_transcript_reviewed="true").json()["transcripts"]

    assert (transcripts["reference"]["source"], transcripts["reference"]["review_status"]) == ("user_provided", "user_attested")
    shared = transcripts["shared_for_comparison"]
    assert (shared["origin"], shared["review_status"], shared["attested_for"]) == ("reference_transcript", "not_reviewed", ["reference"])
    assert (transcripts["participant"]["source"], transcripts["participant"]["review_status"]) == ("machine_generated", "not_reviewed")


# --- Coaching from real findings (limitations fix) -------------------------------------------


def test_coaching_is_built_only_from_the_findings_that_were_reported():
    body = analyze(RUSHED, REFERENCE).json()

    (tip,) = body["coaching"]
    (finding,) = [f for f in body["findings"] if f["category"] == "rushed_delivery"]
    assert tip["id"] == "tip:pace_vs_reference:rushed_delivery"
    assert tip["finding_ids"] == [finding["id"]]
    assert tip["based_on"] == finding["explanation"]
    assert (tip["action"], tip["source"], tip["caution"]) == ("Slow down across this passage.", "rule_based", None)


def test_no_findings_means_no_coaching():
    assert analyze(SAME, REFERENCE).json()["coaching"] == []
    assert analyze(encode(silence(8.0))).json()["coaching"] == []


def test_coaching_on_a_clipped_recording_carries_a_caution():
    body = analyze(encode(np.clip(RUSHED.audio * 8, -1, 1)), REFERENCE).json()

    assert body["coaching"]
    assert all("evidence behind this is weak" in tip["caution"] for tip in body["coaching"])
    reported = {f["id"] for f in body["findings"]}
    assert all(set(tip["finding_ids"]) <= reported for tip in body["coaching"])


# --- Outstanding-limitations fix: fair comparison and provenance -----------------------------


def test_transcripts_that_differ_only_in_case_and_punctuation_are_the_same_text():
    shouted = ", ".join(word.upper() for word in REFERENCE.words) + "!"
    body = analyze(RUSHED, REFERENCE, transcript=REFERENCE.text, reference_transcript=shouted).json()

    assert body["alignment_status"]["status"] == "aligned"
    assert body["alignment_status"]["words_compared"] == WORDS
    assert any(f["category"] == "rushed_delivery" for f in body["findings"])


def test_a_transcript_vouched_for_on_one_recording_is_not_presented_as_checked_for_both():
    one = analyze(RUSHED, REFERENCE, transcript=REFERENCE.text, transcript_reviewed="true").json()["transcripts"]
    both = analyze(
        RUSHED, REFERENCE, transcript=REFERENCE.text, transcript_reviewed="true",
        reference_transcript=REFERENCE.text, reference_transcript_reviewed="true",
    ).json()["transcripts"]  # fmt: skip
    neither = analyze(RUSHED, REFERENCE, transcript=REFERENCE.text).json()["transcripts"]

    # The user's statement is about the participant recording only; the shared text was not checked against the reference.
    assert one["participant"]["review_status"] == "user_attested"
    assert (one["shared_for_comparison"]["review_status"], one["shared_for_comparison"]["attested_for"]) == ("not_reviewed", ["participant"])
    assert (both["shared_for_comparison"]["review_status"], both["shared_for_comparison"]["attested_for"]) == ("user_attested", ["participant", "reference"])
    assert (neither["shared_for_comparison"]["review_status"], neither["shared_for_comparison"]["attested_for"]) == ("not_reviewed", [])
    for transcripts in (one, both, neither):
        assert all(info["human_verified"] is False for info in transcripts.values())


def test_machine_recognised_shared_text_has_nobody_vouching_for_it():
    shared = analyze(RUSHED, REFERENCE, transcript_reviewed="true").json()["transcripts"]["shared_for_comparison"]

    assert (shared["source"], shared["review_status"], shared["attested_for"]) == ("machine_generated", "not_reviewed", [])


def test_unmatched_recognised_words_are_reported_for_both_recordings():
    model = scripted()
    heard = list(RUSHED.words)
    heard[5] = "misheard"
    model.spoken[len(RUSHED.audio)] = heard
    status = analyze(RUSHED, REFERENCE, api=client_with(model)).json()["alignment_status"]

    assert status["unmatched_recognised"] == {"participant": 0, "reference": 0}  # a substitution, not an extra word
    assert status["words_excluded"]["not_recognised_in_participant"] == 1
