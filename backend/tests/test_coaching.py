"""Evidence-based coaching (Prompt 7): every recommendation must trace to measured findings.

Findings come from running the real rules on generated audio, so the values a recommendation
quotes are checked against what was actually measured.
"""

import ast
from pathlib import Path

import numpy as np
import pytest

import app.detection.coaching as coaching_module
from app.detection import run_detection
from app.detection.coaching import REASONS, TEMPLATES, build_coaching

from .detection_fixtures import BASE_RATE, analysis_of, make_take

REFERENCE_TAKE = make_take()
REFERENCE = analysis_of(REFERENCE_TAKE)
TEXT = REFERENCE_TAKE.text


def findings_for(take, *, spoken=None, audio=None, reference=REFERENCE):
    return run_detection(analysis_of(take, transcript=TEXT, spoken=spoken, audio=audio), reference, transcript_source="user_provided").findings


def tip_for(tips, category):
    (tip,) = [t for t in tips if t.category == category]
    return tip


# --- Evidence-to-recommendation links ---------------------------------------------------------


def test_each_recommendation_carries_the_measurements_of_the_findings_behind_it():
    take = make_take(rate=BASE_RATE * 1.5, pauses={5: 1.5, 20: 1.2})
    findings = findings_for(take)
    by_id = {f.id: f for f in findings}

    tips = build_coaching(findings)

    assert tips
    for tip in tips:
        assert [e.finding_id for e in tip.evidence] == tip.finding_ids
        for item in tip.evidence:
            finding = by_id[item.finding_id]
            primary = finding.evidence[0]
            # Interval and numbers are the finding's own, not recomputed or rounded differently.
            assert (item.start, item.end) == (finding.start, finding.end)
            assert (item.feature, item.unit) == (primary.feature, primary.unit)
            assert item.participant_value == primary.participant_value
            assert item.reference_value == primary.reference_value
            assert item.difference == primary.difference
            assert item.evidence_quality == finding.evidence_quality
            assert finding.category == tip.category


def test_a_pace_recommendation_states_the_feature_the_difference_the_interval_and_the_reason():
    take = make_take(rate=BASE_RATE * 1.5)
    tip = tip_for(build_coaching(findings_for(take)), "rushed_delivery")

    (item,) = tip.evidence
    assert item.feature == "speaking_time_for_the_same_words"
    assert item.unit == "s"
    assert item.reference_value == pytest.approx(len(take.words) / BASE_RATE, abs=0.05)
    assert item.participant_value == pytest.approx(len(take.words) / (BASE_RATE * 1.5), abs=0.05)
    assert item.difference == pytest.approx(item.participant_value - item.reference_value, abs=0.001)
    assert (item.start, item.end) == (pytest.approx(0, abs=0.01), pytest.approx(take.ends[-1], abs=0.01))
    assert "speaking time for the same words" in tip.reason
    assert "threshold" in tip.reason
    assert tip.certainty == "confirmed"


def test_several_findings_of_one_kind_are_all_linked_with_their_own_intervals():
    take = make_take(pauses={5: 1.5, 14: 1.5, 22: 1.5, 30: 1.5})
    pauses = [f for f in findings_for(take) if f.category == "excessive_pause"]

    tip = tip_for(build_coaching(pauses), "excessive_pause")

    assert len(tip.evidence) == len(pauses) == 4
    assert [(e.start, e.end) for e in tip.evidence] == [(f.start, f.end) for f in pauses]
    assert all(e.end > e.start for e in tip.evidence)


def test_every_template_has_a_reason_and_no_recommendation_exists_without_a_finding():
    assert set(REASONS) == set(TEMPLATES)
    assert all(reason.strip() for reason in REASONS.values())
    assert build_coaching([]) == []


# --- Missing measurements ---------------------------------------------------------------------


def test_without_a_reference_the_recommendation_reports_no_reference_values_rather_than_inventing_them():
    # 40 words at 4.5 per second plus a 2 s pause is about 220 words per minute, over the 200 limit.
    findings = run_detection(analysis_of(make_take(rate=4.5, pauses={14: 2.0}), source="transcribed")).findings

    tips = build_coaching(findings)

    assert {t.category for t in tips} == {"rushed_delivery", "excessive_pause"}
    for tip in tips:
        assert all(e.reference_value is None and e.difference is None for e in tip.evidence)
        assert "reference" not in tip.reason.lower() or "no reference" in tip.reason.lower()


def test_a_measurement_that_was_withheld_produces_no_recommendation():
    """The pitch is narrow, but tracking was made unreliable, so the pitch rule is withheld and nothing is advised."""
    analysis = analysis_of(make_take(swing_semitones=0.4), transcript=TEXT)
    analysis.features.pitch = analysis.features.pitch.model_copy(update={"reliability": "low", "limitations": ["Low reliability: test."]})

    result = run_detection(analysis, REFERENCE, transcript_source="user_provided")

    assert next(r for r in result.rules if r.category == "pitch_monotony").status == "withheld"
    assert not any(t.category == "pitch_monotony" for t in build_coaching(result.findings))


def test_a_finding_with_no_measured_value_is_not_given_a_made_up_one():
    finding = findings_for(make_take(rate=BASE_RATE * 1.5))[0].model_copy(deep=True)
    finding.evidence[0].participant_value = None
    finding.evidence[0].reference_value = None
    finding.evidence[0].difference = None

    (tip,) = build_coaching([finding])

    assert (tip.evidence[0].participant_value, tip.evidence[0].reference_value, tip.evidence[0].difference) == (None, None, None)


# --- Confirmed versus uncertain ---------------------------------------------------------------


def test_recommendations_from_solid_measurements_are_confirmed():
    tips = build_coaching(findings_for(make_take(rate=BASE_RATE * 1.5, pauses={14: 1.5})))

    assert {t.certainty for t in tips} == {"confirmed"}
    assert all(t.caution is None for t in tips)


def test_recommendations_from_weak_evidence_are_uncertain():
    take = make_take(rate=BASE_RATE * 1.5)
    clipped = build_coaching(findings_for(take, audio=np.clip(take.audio * 8, -1, 1)))

    assert clipped and {t.certainty for t in clipped} == {"uncertain"}
    assert all(t.caution for t in clipped)


def test_a_recommendation_worded_as_possible_is_uncertain_even_with_usable_audio():
    tip = tip_for(build_coaching(findings_for(make_take(swing_semitones=0.4))), "pitch_monotony")

    assert tip.certainty == "uncertain"
    assert tip.evidence[0].feature == "pitch_range_5th_to_95th_percentile"
    assert tip.evidence[0].unit == "semitones"


def test_one_weak_finding_among_several_makes_the_recommendation_uncertain_and_says_which():
    take = make_take()
    spoken = list(take.words)
    spoken[9], spoken[20] = "um", "uh"
    analysis = analysis_of(take, spoken=spoken, transcript=" ".join(spoken), source="transcribed")
    analysis.transcription.words[9].probability = 0.3

    (tip,) = build_coaching(run_detection(analysis).findings)

    assert tip.certainty == "uncertain"
    assert [e.evidence_quality for e in tip.evidence] == ["low", "moderate"]
    assert tip.caution.startswith("1 of the 2 findings")


# --- Wording safeguards -----------------------------------------------------------------------


def test_no_recommendation_text_infers_state_of_mind_ability_or_identity():
    text = " ".join([*(" ".join(pair) for pair in TEMPLATES.values()), *REASONS.values()]).lower()

    banned = (
        "nervous", "anxious", "anxiety", "confiden", "stress", "personality", "competen", "intelligen", "shy",
        "accent", "native", "disorder", "impairment", "because you are", "you seem", "you sound", "lazy", "careless",
    )  # fmt: skip
    for word in banned:
        assert word not in text, word


def test_reasons_describe_the_measurement_not_a_cause():
    for key, reason in REASONS.items():
        assert "measured" in reason.lower() or "recognised" in reason.lower(), key
        assert " because you" not in reason.lower(), key


# --- No language model ------------------------------------------------------------------------


def test_coaching_is_deterministic_and_needs_no_language_model_or_network():
    findings = findings_for(make_take(rate=BASE_RATE * 1.5, pauses={14: 1.5}))

    first = [t.model_dump() for t in build_coaching(findings)]
    second = [t.model_dump() for t in build_coaching(findings)]

    assert first == second
    assert {t["source"] for t in first} == {"rule_based"}
    # The module imports nothing that could call a model or the network.
    imported = {
        node.module.split(".")[0] if isinstance(node, ast.ImportFrom) and node.module else alias.name.split(".")[0]
        for node in ast.walk(ast.parse(Path(coaching_module.__file__).read_text(encoding="utf-8")))
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
    }
    assert imported <= {"pydantic", "schemas", "typing"}


def test_the_api_returns_rule_based_coaching_with_no_model_configured(monkeypatch):
    from fastapi.testclient import TestClient

    from app.config import Settings
    from app.main import create_app

    from .audio_samples import encode
    from .speech_fakes import transcriber_failing_to_load

    for name in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "HF_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    # Even with transcription unavailable, a measured long pause still yields its rule-based recommendation.
    api = TestClient(create_app(Settings(), transcriber=transcriber_failing_to_load(ImportError("faster_whisper"))))
    body = api.post("/api/analyze", files={"file": ("take.wav", encode(make_take(pauses={14: 2.0}).audio))}).json()

    (tip,) = body["coaching"]
    assert (tip["source"], tip["category"], tip["certainty"]) == ("rule_based", "excessive_pause", "confirmed")
    assert tip["evidence"][0]["participant_value"] == pytest.approx(2.0, abs=0.08)
    assert tip["evidence"][0]["reference_value"] is None
    assert tip["reason"]
