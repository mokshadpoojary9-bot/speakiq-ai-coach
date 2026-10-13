import numpy as np
import pytest
from fastapi.testclient import TestClient

from app.audio import extract_features
from app.comparison import ComparisonSettings, DeliveryAnalysis, compare_deliveries
from app.config import Settings
from app.main import create_app
from app.speech import align_transcript
from app.speech.schemas import RecognizedWord

from .audio_samples import encode, loaded, silence, syllables
from .speech_fakes import FakeModel, FakeSegment, FakeWord, transcriber_failing_to_load, transcriber_with

TEXT = "good morning everyone thank you for coming"
# Word start times in seconds; each word lasts 0.3 s.
REFERENCE_STARTS = [0.1, 0.5, 0.9, 1.5, 1.9, 2.7, 3.1]
# Same words, with 1.0 s more silence before 'thank' and 0.4 s less before 'for'.
PARTICIPANT_STARTS = [0.1, 0.5, 0.9, 2.5, 2.9, 3.3, 3.7]

REFERENCE_AUDIO = np.concatenate([syllables(8), silence(0.3), syllables(8)])
PARTICIPANT_AUDIO = np.concatenate([syllables(8), silence(1.3), syllables(8)])


def heard(starts, text=TEXT):
    return [RecognizedWord(word=w, start=s, end=round(s + 0.3, 3), probability=0.9) for w, s in zip(text.split(), starts)]


def analysis(audio, starts, transcript=TEXT, spoken=TEXT) -> DeliveryAnalysis:
    return DeliveryAnalysis(
        features=extract_features(loaded(audio)),
        alignment=align_transcript(transcript, heard(starts, spoken)) if starts else None,
    )


def metric(result, name):
    return next(m for m in result.global_metrics if m.name == name)


# --- compare_deliveries ----------------------------------------------------------------------


def test_reports_gaps_that_differ_from_the_reference_with_their_intervals():
    result = compare_deliveries(analysis(REFERENCE_AUDIO, REFERENCE_STARTS), analysis(PARTICIPANT_AUDIO, PARTICIPANT_STARTS))

    assert result.status == "completed"
    assert (result.word_level.words_compared, result.word_level.gaps_compared) == (7, 6)
    longer, shorter = result.word_level.timing_differences

    assert (longer.kind, longer.after_word, longer.before_word) == ("longer_gap", "everyone", "thank")
    assert longer.reference_gap_sec == pytest.approx(0.3)
    assert longer.participant_gap_sec == pytest.approx(1.3)
    assert longer.difference_sec == pytest.approx(1.0)
    # The interval is the silence itself in the participant recording: end of 'everyone' to start of 'thank'.
    assert (longer.participant_interval.start, longer.participant_interval.end) == (1.2, 2.5)
    assert (longer.reference_interval.start, longer.reference_interval.end) == (1.2, 1.5)
    assert "1.00 s longer" in longer.evidence

    assert (shorter.kind, shorter.after_word, shorter.before_word) == ("shorter_gap", "you", "for")
    assert (shorter.reference_gap_sec, shorter.participant_gap_sec) == (pytest.approx(0.5), pytest.approx(0.1))
    assert shorter.difference_sec == pytest.approx(-0.4)


def test_identical_timing_reports_no_differences():
    result = compare_deliveries(analysis(REFERENCE_AUDIO, REFERENCE_STARTS), analysis(REFERENCE_AUDIO, REFERENCE_STARTS))

    assert result.word_level.timing_differences == []
    assert all(w.duration_difference_sec == 0 for w in result.word_level.words)
    assert metric(result, "duration").ratio == 1


def test_differences_below_the_threshold_are_not_reported_and_the_threshold_is_configurable():
    nudged = [s + (0.15 if i >= 3 else 0) for i, s in enumerate(REFERENCE_STARTS)]
    reference, participant = analysis(REFERENCE_AUDIO, REFERENCE_STARTS), analysis(REFERENCE_AUDIO, nudged)

    assert compare_deliveries(reference, participant).word_level.timing_differences == []
    sensitive = compare_deliveries(reference, participant, ComparisonSettings(min_gap_difference_sec=0.1))
    assert [d.kind for d in sensitive.word_level.timing_differences] == ["longer_gap"]
    assert sensitive.word_level.min_gap_difference_sec == 0.1


def test_gaps_next_to_unrecognised_words_are_not_measured():
    """The participant's 'thank' was misheard, so neither gap touching it can be trusted."""
    spoken = TEXT.replace("thank", "tank")
    participant = analysis(PARTICIPANT_AUDIO, PARTICIPANT_STARTS, spoken=spoken)

    result = compare_deliveries(analysis(REFERENCE_AUDIO, REFERENCE_STARTS), participant)

    assert result.word_level.words_compared == 6
    assert result.word_level.gaps_compared == 4
    assert "thank" not in [w.word for w in result.word_level.words]
    assert all("thank" not in (d.after_word, d.before_word) for d in result.word_level.timing_differences)


def test_word_level_is_unavailable_without_alignment_but_global_measures_remain():
    result = compare_deliveries(analysis(REFERENCE_AUDIO, REFERENCE_STARTS), analysis(PARTICIPANT_AUDIO, None))

    assert result.status == "partial"
    assert result.word_level.status == "unavailable"
    assert "participant" in result.word_level.reason
    assert result.word_level.timing_differences == []
    assert metric(result, "duration").difference == pytest.approx(1.0, abs=0.01)


def test_word_level_is_unavailable_when_the_recordings_used_different_transcripts():
    other = analysis(PARTICIPANT_AUDIO, PARTICIPANT_STARTS, transcript="something else entirely was said here today friends")

    result = compare_deliveries(analysis(REFERENCE_AUDIO, REFERENCE_STARTS), other)

    assert result.word_level.status == "unavailable"
    assert "same transcript" in result.word_level.reason


def test_global_metrics_come_from_the_measurements():
    reference, participant = analysis(REFERENCE_AUDIO, REFERENCE_STARTS), analysis(PARTICIPANT_AUDIO, PARTICIPANT_STARTS)
    result = compare_deliveries(reference, participant)

    duration = metric(result, "duration")
    assert (duration.basis, duration.comparable) == ("measured", True)
    assert duration.reference == reference.features.audio.duration_sec
    assert duration.participant == participant.features.audio.duration_sec
    assert duration.difference == pytest.approx(1.0, abs=0.01)

    pause_total = metric(result, "internal_pause_total")
    assert pause_total.difference == pytest.approx(1.0, abs=0.08)
    assert metric(result, "internal_pause_count").difference == 0

    assert metric(result, "speech_rate").basis == "estimated"
    assert metric(result, "pitch_median").comparable is False
    assert metric(result, "pitch_range").comparable is True
    assert "energy_db" in result.not_compared


def test_unreliable_or_missing_measurements_are_marked_not_comparable():
    reference = analysis(REFERENCE_AUDIO, REFERENCE_STARTS)
    quiet = DeliveryAnalysis(features=extract_features(loaded(silence(2.0))))

    result = compare_deliveries(reference, quiet)

    for name in ("internal_pause_count", "internal_pause_total", "pitch_range", "speech_rate"):
        item = metric(result, name)
        assert item.participant is None, name
        assert (item.comparable, item.difference, item.ratio) == (False, None, None), name


def test_never_claims_flaws_severity_or_coaching():
    result = compare_deliveries(analysis(REFERENCE_AUDIO, REFERENCE_STARTS), analysis(PARTICIPANT_AUDIO, PARTICIPANT_STARTS))
    text = result.model_dump_json()

    assert "Deciding whether a difference is a flaw" in result.not_implemented
    assert "Severity levels" in result.not_implemented
    assert '"severity"' not in text and '"flaw_category"' not in text
    assert any("differences, not flaws" in line for line in result.limitations)


# --- POST /api/compare -----------------------------------------------------------------------


def words_for(starts):
    return [FakeSegment(f" {TEXT}", starts[0], starts[-1] + 0.3, [FakeWord(f" {w}", s, s + 0.3) for w, s in zip(TEXT.split(), starts)])]


class TwoRecordings(FakeModel):
    """Returns the reference timing for the shorter recording and the participant timing for the longer one."""

    def transcribe(self, samples, **kwargs):
        self.segments = words_for(REFERENCE_STARTS if len(samples) < len(PARTICIPANT_AUDIO) else PARTICIPANT_STARTS)
        return super().transcribe(samples, **kwargs)


def post(client, **form):
    files = {"reference": ("ref.wav", encode(REFERENCE_AUDIO)), "participant": ("take2.wav", encode(PARTICIPANT_AUDIO))}
    return client.post("/api/compare", files=files, data=form or None)


def test_compare_endpoint_aligns_both_recordings_to_the_supplied_transcript():
    response = post(TestClient(create_app(Settings(), transcriber=transcriber_with(TwoRecordings()))), transcript=TEXT)

    assert response.status_code == 200
    body = response.json()
    assert (body["is_demo"], body["transcript_source"]) == (False, "supplied")
    assert body["reference"]["filename"] == "ref.wav"
    assert body["participant"]["alignment"]["status"] == "completed"
    differences = body["comparison"]["word_level"]["timing_differences"]
    assert differences[0]["kind"] == "longer_gap"
    assert differences[0]["participant_interval"] == {"start": 1.2, "end": 2.5}


def test_compare_endpoint_falls_back_to_the_reference_transcription():
    response = post(TestClient(create_app(Settings(), transcriber=transcriber_with(TwoRecordings()))))

    body = response.json()
    assert body["transcript_source"] == "reference_transcription"
    assert body["comparison"]["status"] == "completed"
    assert body["comparison"]["word_level"]["words_compared"] == 7


def test_compare_endpoint_still_returns_measurements_when_transcription_is_unavailable():
    client = TestClient(create_app(Settings(), transcriber=transcriber_failing_to_load(ImportError("faster_whisper"))))

    body = post(client, transcript=TEXT).json()

    assert body["comparison"]["status"] == "partial"
    assert body["comparison"]["word_level"]["status"] == "unavailable"
    assert body["reference"]["transcription"]["code"] == "missing_dependency"
    assert next(m for m in body["comparison"]["global_metrics"] if m["name"] == "duration")["difference"] == pytest.approx(1.0, abs=0.01)


def test_compare_endpoint_validates_both_uploads():
    client = TestClient(create_app(Settings(), transcriber=transcriber_with(TwoRecordings())))

    bad = client.post("/api/compare", files={"reference": ("ref.wav", encode(REFERENCE_AUDIO)), "participant": ("x.wav", b"junk")})
    missing = client.post("/api/compare", files={"reference": ("ref.wav", encode(REFERENCE_AUDIO))})

    assert (bad.status_code, bad.json()["detail"]["code"]) == (415, "undecodable_audio")
    assert (missing.status_code, missing.json()["detail"]["code"]) == (422, "invalid_request")
