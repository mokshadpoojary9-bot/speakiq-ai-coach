"""Clarity estimate: articulation rate and recogniser word confidence, shown for information only."""

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.detection.clarity import clarity_values, estimate_clarity
from app.main import create_app

from .detection_fixtures import analysis_of, make_take, transcription_of
from .speech_fakes import transcriber_failing_to_load
from .test_detection_api import REFERENCE, RUSHED, SAME, analyze


def test_word_confidence_is_the_mean_recogniser_probability_and_the_share_below_one_half():
    take = make_take(words=4)
    transcription = transcription_of(take)
    for word, probability in zip(transcription.words, (0.9, 0.3, 0.8, None)):
        word.probability = probability

    values = clarity_values(analysis_of(take).features, transcription)

    assert values.words == 3  # a word without a probability is not counted
    assert values.mean_word_confidence == pytest.approx((0.9 + 0.3 + 0.8) / 3, abs=0.001)
    assert values.low_confidence_word_share == pytest.approx(1 / 3, abs=0.001)


def test_articulation_rate_follows_the_speed_of_speech_and_ignores_pauses():
    steady = clarity_values(analysis_of(make_take()).features, None)
    faster = clarity_values(analysis_of(make_take(rate=2.5 * 1.5)).features, None)
    paused = clarity_values(analysis_of(make_take(pauses={10: 1.5, 25: 1.5})).features, None)

    assert faster.articulation_rate_syll_per_sec / steady.articulation_rate_syll_per_sec == pytest.approx(1.5, abs=0.15)
    assert paused.articulation_rate_syll_per_sec == pytest.approx(steady.articulation_rate_syll_per_sec, rel=0.1)
    assert (steady.mean_word_confidence, steady.low_confidence_word_share, steady.words) == (None, None, 0)


def test_nothing_measured_is_unavailable_not_zero():
    take = make_take()
    empty = clarity_values(analysis_of(take).features, None).model_copy(update={"articulation_rate_syll_per_sec": None})

    estimate = estimate_clarity(empty)

    assert estimate.status == "unavailable"
    assert estimate.participant.mean_word_confidence is None


def test_the_api_returns_the_estimate_for_both_recordings_labelled_as_an_estimate():
    body = analyze(RUSHED, REFERENCE).json()

    clarity = body["clarity"]
    assert clarity["status"] == "estimated"
    assert clarity["participant"]["mean_word_confidence"] == pytest.approx(0.9)
    assert clarity["participant"]["low_confidence_word_share"] == 0
    assert clarity["participant"]["articulation_rate_syll_per_sec"] > clarity["reference"]["articulation_rate_syll_per_sec"] * 1.3
    assert any("estimate, not a measure" in line for line in clarity["limitations"])
    # It never becomes a finding.
    assert all(f["category"] != "unclear_articulation" for f in body["findings"])
    assert next(r for r in body["rules"] if r["category"] == "unclear_articulation")["status"] == "not_supported"


def test_without_a_reference_or_transcription_only_what_was_measured_is_shown():
    alone = analyze(SAME).json()["clarity"]
    api = TestClient(create_app(Settings(), transcriber=transcriber_failing_to_load(ImportError("faster_whisper"))))
    unheard = analyze(SAME, api=api).json()["clarity"]

    assert alone["reference"] is None
    assert unheard["status"] == "estimated"
    assert unheard["participant"]["articulation_rate_syll_per_sec"] == alone["participant"]["articulation_rate_syll_per_sec"]
    assert (unheard["participant"]["mean_word_confidence"], unheard["participant"]["words"]) == (None, 0)
