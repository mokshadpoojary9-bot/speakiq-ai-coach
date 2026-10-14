"""Regression tests for alignment, comparison and the delivery rules (Milestone 5.2).

Audio is generated with known word times, pauses, rates and pitch. Every expected number below
follows from those generation parameters; nothing is copied from the implementation's output.
"""

import numpy as np
import pytest

from app.audio import extract_features
from app.comparison import compare_deliveries
from app.detection import DetectionSettings, run_detection
from app.detection.coaching import TEMPLATES, build_coaching
from app.detection.rules import pitch_window_stats, silence_within

from .audio_samples import SR, loaded, silence, tone
from .detection_fixtures import BASE_RATE, WORDS, analysis_of, make_take, noise

REFERENCE_TAKE = make_take()
REFERENCE = analysis_of(REFERENCE_TAKE)
TEXT = REFERENCE_TAKE.text


def detect(take, *, reference=REFERENCE, **kwargs):
    return run_detection(analysis_of(take, transcript=TEXT, **kwargs), reference, transcript_source="user_provided")


def categories(result) -> list[str]:
    return [f.category for f in result.findings]


def rule(result, category):
    return next(r for r in result.rules if r.category == category)


def only(result, category):
    (finding,) = [f for f in result.findings if f.category == category]
    return finding


# --- G1 / G10: comparable recordings and a valid no-finding result ---------------------------


def test_an_identically_paced_take_produces_no_findings_and_every_rule_reports_that_it_checked():
    result = detect(make_take())

    assert result.findings == []
    assert result.alignment_status.status == "aligned"
    assert result.alignment_status.words_compared == WORDS
    assert result.signal_quality.usable
    statuses = {r.category: r.status for r in result.rules}
    assert statuses == {
        "rushed_delivery": "not_triggered",
        "slow_delivery": "not_triggered",
        "excessive_pause": "not_triggered",
        "irregular_pauses": "not_triggered",
        "uneven_pacing": "not_triggered",
        "filler_word": "not_triggered",
        "pitch_monotony": "not_triggered",
        "unclear_articulation": "not_supported",
    }
    assert rule(result, "rushed_delivery").measured["ratio"] == pytest.approx(1.0, abs=0.01)


def test_a_small_pace_difference_below_the_threshold_is_not_a_finding():
    result = detect(make_take(rate=BASE_RATE * 1.05))

    assert result.findings == []
    assert rule(result, "rushed_delivery").measured["ratio"] == pytest.approx(1 / 1.05, abs=0.01)


def test_results_are_identical_across_repeated_runs():
    take = make_take(rate=BASE_RATE * 1.4, pauses={12: 1.0})

    first = detect(take).model_dump_json()
    second = detect(make_take(rate=BASE_RATE * 1.4, pauses={12: 1.0})).model_dump_json()

    assert first == second


# --- G2: faster and slower delivery ----------------------------------------------------------


@pytest.mark.parametrize(
    ("speed", "category", "severity"),
    [(1.15, "rushed_delivery", "minor"), (1.27, "rushed_delivery", "moderate"), (1.5, "rushed_delivery", "major"),
     (1 / 1.15, "slow_delivery", "minor"), (1 / 1.27, "slow_delivery", "moderate"), (1 / 1.5, "slow_delivery", "major")],
)  # fmt: skip
def test_pace_against_the_reference_is_measured_over_the_same_words(speed, category, severity):
    take = make_take(rate=BASE_RATE * speed)
    result = detect(take)

    finding = only(result, category)
    time = finding.evidence[0]
    assert time.feature == "speaking_time_for_the_same_words" and time.unit == "s"
    assert time.reference_value == pytest.approx(WORDS / BASE_RATE, abs=0.05)
    assert time.participant_value == pytest.approx(WORDS / (BASE_RATE * speed), abs=0.05)
    assert time.ratio == pytest.approx(1 / speed, abs=0.01)
    assert (finding.start, finding.end) == (pytest.approx(0, abs=0.01), pytest.approx(take.ends[-1], abs=0.01))
    assert finding.reference_interval.end == pytest.approx(REFERENCE_TAKE.ends[-1], abs=0.01)
    assert finding.severity == severity
    assert "magnitude band" in finding.severity_basis
    assert finding.evidence_quality == "high"
    other = "slow_delivery" if category == "rushed_delivery" else "rushed_delivery"
    assert rule(result, other).status == "not_triggered"


def test_pauses_do_not_count_as_slow_delivery():
    """Three seconds of extra silence make the take longer, but the words are spoken at the same rate."""
    result = detect(make_take(pauses={10: 1.5, 25: 1.5}))

    assert "slow_delivery" not in categories(result)
    assert rule(result, "slow_delivery").measured["ratio"] == pytest.approx(1.0, abs=0.03)
    assert categories(result).count("excessive_pause") == 2


def test_pace_without_a_reference_uses_words_per_minute_and_gives_no_severity():
    fast = run_detection(analysis_of(make_take(rate=3.75), source="transcribed"))
    slow = run_detection(analysis_of(make_take(rate=1.5), source="transcribed"))
    normal = run_detection(analysis_of(make_take(), source="transcribed"))

    finding = only(fast, "rushed_delivery")
    assert finding.evidence[0].feature == "words_per_minute"
    assert finding.evidence[0].participant_value == pytest.approx(3.75 * 60, rel=0.01)
    assert finding.evidence[0].reference_value is None
    assert (finding.severity, finding.evidence_quality) == (None, "moderate")
    assert any("No severity is given" in text for text in finding.limitations)
    assert only(slow, "slow_delivery").evidence[0].participant_value == pytest.approx(90, rel=0.01)
    assert not {"rushed_delivery", "slow_delivery"} & set(categories(normal))
    assert fast.alignment_status.status == "no_reference"


def test_words_per_minute_is_withheld_for_other_languages_and_short_recordings():
    take = make_take(rate=3.75)
    analysis = analysis_of(take, source="transcribed")
    analysis.transcription.language = "hi"
    short = analysis_of(make_take(words=15, rate=3.75), source="transcribed")

    assert rule(run_detection(analysis), "rushed_delivery").status == "withheld"
    assert "for English" in rule(run_detection(analysis), "rushed_delivery").reason
    assert rule(run_detection(short), "rushed_delivery").status == "withheld"
    assert "at least 20 recognised words" in rule(run_detection(short), "rushed_delivery").reason


# --- G3: longer pauses and irregular pacing --------------------------------------------------


@pytest.mark.parametrize(("extra", "severity"), [(0.6, "minor"), (1.0, "moderate"), (1.8, "major")])
def test_a_longer_pause_is_reported_at_its_measured_interval(extra, severity):
    take = make_take(pauses={14: extra})
    result = detect(take)

    finding = only(result, "excessive_pause")
    # The silence sits between the end of word 14 and the start of word 15.
    assert finding.start == pytest.approx(take.ends[14], abs=0.06)
    assert finding.end == pytest.approx(take.starts[15], abs=0.06)
    silence_evidence = finding.evidence[0]
    assert silence_evidence.participant_value == pytest.approx(extra, abs=0.08)
    assert silence_evidence.reference_value == 0
    assert finding.severity == severity
    assert "'w14'" in finding.comparison_method and "'w15'" in finding.comparison_method
    assert finding.reference_interval.start == pytest.approx(REFERENCE_TAKE.starts[14], abs=0.01)


def test_a_pause_the_reference_also_has_is_not_a_finding():
    both_pause = analysis_of(make_take(pauses={14: 1.0}))
    result = run_detection(analysis_of(make_take(pauses={14: 1.1}), transcript=TEXT), both_pause, transcript_source="user_provided")

    assert "excessive_pause" not in categories(result)
    assert rule(result, "excessive_pause").measured["pauses_located_between_aligned_words"] == 1


def test_a_short_extra_pause_below_the_threshold_is_not_a_finding():
    assert "excessive_pause" not in categories(detect(make_take(pauses={14: 0.3})))


def test_a_long_pause_without_a_reference_is_reported_without_severity():
    result = run_detection(analysis_of(make_take(pauses={14: 2.0, 30: 0.8}), source="transcribed"))

    finding = only(result, "excessive_pause")
    assert finding.rule.rule_id == "long_pause"
    assert finding.evidence[0].participant_value == pytest.approx(2.0, abs=0.08)
    assert (finding.severity, finding.reference_interval) == (None, None)


def test_uneven_pacing_flags_the_stretches_that_depart_from_the_speakers_own_pace():
    slow_middle = make_take(48, rate=lambda i: 1.8 if 16 <= i < 32 else 3.6)
    reference = analysis_of(make_take(48))
    result = run_detection(analysis_of(slow_middle, transcript=make_take(48).text), reference, transcript_source="user_provided")

    uneven = [f for f in result.findings if f.category == "uneven_pacing"]
    slower = [f for f in uneven if f.title.startswith("Slower")]
    faster = [f for f in uneven if f.title.startswith("Faster")]
    assert slower and faster
    # Stretches are runs of about five words and need not start exactly where the pace changes, so each
    # is judged by its midpoint: 'slower' ones fall inside words 16-31 and 'faster' ones outside.
    slow_start, slow_end = slow_middle.starts[16], slow_middle.ends[31]
    for finding in slower:
        assert slow_start < (finding.start + finding.end) / 2 < slow_end
    for finding in faster:
        assert not slow_start < (finding.start + finding.end) / 2 < slow_end
    assert all(f.severity is None and f.evidence_quality == "moderate" for f in uneven)
    assert rule(result, "uneven_pacing").measured["spread_ratio"] == pytest.approx(2.0, abs=0.1)


def test_being_uniformly_fast_is_rushed_but_not_uneven():
    result = detect(make_take(rate=BASE_RATE * 1.5))

    assert "uneven_pacing" not in categories(result)
    assert rule(result, "uneven_pacing").measured["spread_ratio"] == pytest.approx(1.0, abs=0.05)


def test_uneven_pacing_is_withheld_without_a_reference():
    report = rule(run_detection(analysis_of(make_take(), source="transcribed")), "uneven_pacing")

    assert report.status == "withheld"
    assert "Needs a reference recording" in report.reason


# --- G4: filler words ------------------------------------------------------------------------


def test_recognised_fillers_are_reported_at_their_word_times():
    take = make_take()
    spoken = list(take.words)
    spoken[7], spoken[21] = "um", "Uh,"
    result = run_detection(analysis_of(take, spoken=spoken, transcript=" ".join(spoken), source="transcribed"))

    fillers = [f for f in result.findings if f.category == "filler_word"]
    assert [(f.start, f.end) for f in fillers] == [(take.starts[7], take.ends[7]), (take.starts[21], take.ends[21])]
    assert fillers[0].title == "Filler sound: “um”"
    assert fillers[0].evidence[0].feature == "recogniser_word_probability"
    assert fillers[0].severity is None


def test_a_filler_missing_from_the_supplied_script_is_noted():
    take = make_take()
    spoken = list(take.words)
    spoken[7] = "um"
    result = run_detection(analysis_of(take, spoken=spoken, transcript=take.text))

    assert "It is not in the transcript you supplied." in only(result, "filler_word").comparison_method


def test_real_words_are_never_counted_as_fillers_and_zero_is_not_called_none():
    take = make_take()
    spoken = list(take.words)
    spoken[3], spoken[4], spoken[5] = "like", "so", "well"
    report = rule(run_detection(analysis_of(take, spoken=spoken, transcript=" ".join(spoken), source="transcribed")), "filler_word")

    assert (report.status, report.findings) == ("not_triggered", 0)
    assert "not evidence that there were none" in report.reason


def spoken_with(replacements: dict[int, str], probabilities: dict[int, float] | None = None):
    take = make_take()
    spoken = list(take.words)
    for index, word in replacements.items():
        spoken[index] = word
    analysis = analysis_of(take, spoken=spoken, transcript=" ".join(spoken), source="transcribed")
    for index, probability in (probabilities or {}).items():
        analysis.transcription.words[index].probability = probability
    return take, analysis


@pytest.mark.parametrize("heard", ["um", "Um,", "UH", "uh...", "Erm,", "ER,", "hmm", "Hmmmm.", "ummm", "uhhh", "errm", "mm", "mhm"])
def test_filler_spellings_the_recogniser_produces_are_recognised(heard):
    """Includes the capitalised and punctuated forms the real model returned for synthesised test speech."""
    take, analysis = spoken_with({9: heard})

    finding = only(run_detection(analysis), "filler_word")

    assert (finding.start, finding.end) == (take.starts[9], take.ends[9])


@pytest.mark.parametrize("heard", ["umbrella", "her", "him", "mum", "error", "a", "I", "m", "hum", "summer", "ermine", "uhuru", "oh", "like"])
def test_words_that_merely_resemble_fillers_are_not_reported(heard):
    _, analysis = spoken_with({9: heard})

    assert "filler_word" not in categories(run_detection(analysis))


def test_a_filler_the_recogniser_was_unsure_of_is_only_possible():
    _, analysis = spoken_with({9: "um", 20: "uh"}, probabilities={9: 0.33, 20: 0.91})

    unsure, sure = [f for f in run_detection(analysis).findings if f.category == "filler_word"]

    assert unsure.title == "Possible filler sound: “um”"
    assert unsure.evidence_quality == "low"
    assert "It was not confident (probability 0.33)." in unsure.explanation
    assert sure.title == "Filler sound: “uh”"
    assert sure.evidence_quality == "moderate"
    assert unsure.evidence[0].participant_value == 0.33


def test_filler_rule_reports_a_rate_and_one_finding_per_occurrence():
    take, analysis = spoken_with({3: "um", 4: "um", 30: "uh"})
    result = run_detection(analysis)

    report = rule(result, "filler_word")
    fillers = [f for f in result.findings if f.category == "filler_word"]

    assert (report.status, report.findings) == ("triggered", 3)
    assert len({f.id for f in fillers}) == 3
    assert report.measured["fillers"] == 3
    assert report.measured["fillers_per_minute"] == pytest.approx(3 / take.ends[-1] * 60, abs=0.2)


def test_fillers_are_withheld_without_word_timestamps():
    analysis = analysis_of(make_take())
    analysis.transcription = None

    assert rule(run_detection(analysis), "filler_word").status == "withheld"


# --- G5 / G6: missing reference, mismatched transcripts, failed alignment ---------------------


def test_without_a_reference_only_reference_free_rules_run():
    result = run_detection(analysis_of(make_take(), source="transcribed"), transcript_source="machine_generated")

    assert result.alignment_status.status == "no_reference"
    assert result.alignment_status.transcript_source == "machine_generated"
    assert {r.rule_id for r in result.rules if r.status != "withheld"} == {"pace_words_per_minute", "long_pause", "filler_lexicon", "filled_pause_acoustic", "pitch_range", "articulation"}
    assert all(f.reference_interval is None for f in result.findings)


def test_recordings_aligned_to_different_transcripts_are_not_compared():
    other = analysis_of(make_take(rate=BASE_RATE * 1.5), transcript=" ".join(f"x{i}" for i in range(WORDS)))
    result = run_detection(other, REFERENCE, transcript_source="user_provided")

    assert result.alignment_status.status == "unavailable"
    assert "different transcripts" in result.alignment_status.reason
    assert all(f.rule.rule_id != "pace_vs_reference" for f in result.findings)
    assert result.limitations[0].startswith("The reference recording was not used")
    assert rule(result, "uneven_pacing").status == "withheld"


def test_a_withheld_reason_from_the_caller_is_respected():
    result = run_detection(
        analysis_of(make_take(rate=BASE_RATE * 1.5), transcript=TEXT),
        REFERENCE,
        comparison_withheld_reason="The participant and reference transcripts contain different words.",
    )

    assert result.alignment_status.reason == "The participant and reference transcripts contain different words."
    assert all(f.reference_interval is None for f in result.findings)


def test_a_participant_who_said_something_else_fails_the_coverage_check():
    """Rushed audio, but only a quarter of the transcript was recognised in it: no reference-based claim is made."""
    take = make_take(rate=BASE_RATE * 1.5)
    spoken = [w if i % 4 == 0 else f"other{i}" for i, w in enumerate(take.words)]
    result = detect(take, spoken=spoken)

    assert result.alignment_status.status == "unavailable"
    assert "Only 25% of the transcript's words were recognised in the participant recording" in result.alignment_status.reason
    assert result.alignment_status.participant_coverage == 0.25
    assert not any(f.rule.rule_id.endswith("_vs_reference") for f in result.findings)


def test_missing_alignment_on_either_side_makes_the_comparison_unavailable():
    no_participant = run_detection(analysis_of(make_take(), aligned=False), REFERENCE)
    no_reference = run_detection(analysis_of(make_take(), transcript=TEXT), analysis_of(REFERENCE_TAKE, aligned=False))

    assert "participant recording has no word alignment" in no_participant.alignment_status.reason
    assert "reference recording has no word alignment" in no_reference.alignment_status.reason


def test_an_unusable_reference_is_reported_and_not_compared():
    quiet_reference = analysis_of(REFERENCE_TAKE, audio=silence(REFERENCE_TAKE.ends[-1]))
    result = run_detection(analysis_of(make_take(rate=BASE_RATE * 1.5), transcript=TEXT), quiet_reference)

    assert result.alignment_status.status == "unavailable"
    assert result.alignment_status.reason.startswith("The reference recording cannot be used:")
    assert result.signal_quality.usable  # the participant recording itself is fine


# --- Recognition errors and unmatched words (limitations fix) --------------------------------


def test_words_left_out_of_the_comparison_are_counted_by_reason():
    take = make_take(rate=BASE_RATE * 1.5)
    spoken = list(take.words)
    for i in (10, 12, 14):
        spoken[i] = f"misheard{i}"  # leaves words 11 and 13 matched but with no matched neighbour
    result = detect(take, spoken=spoken)

    status = result.alignment_status
    assert status.words_excluded == {"not_recognised_in_participant": 3, "isolated_match": 2}
    assert status.words_compared == WORDS - 5
    assert only(result, "rushed_delivery").evidence[0].ratio == pytest.approx(1 / 1.5, abs=0.02)


def test_an_isolated_match_at_the_wrong_place_cannot_distort_the_comparison():
    """A repeated word matched to a later occurrence: surrounded by unmatched words, with a time from elsewhere."""
    take = make_take()
    analysis = analysis_of(take, transcript=TEXT)
    words = analysis.alignment.words
    for i in (10, 12):
        words[i] = words[i].model_copy(update={"status": "unaligned", "start": None, "end": None})
    words[11] = words[11].model_copy(update={"start": take.starts[30], "end": take.ends[30]})  # ten seconds late

    result = run_detection(analysis, REFERENCE, transcript_source="user_provided")

    assert result.alignment_status.words_excluded == {"not_recognised_in_participant": 2, "isolated_match": 1}
    assert result.alignment_status.words_compared == WORDS - 3  # the words after it are all still compared
    assert result.findings == []
    assert rule(result, "rushed_delivery").measured["ratio"] == pytest.approx(1.0, abs=0.02)


def test_findings_resting_on_a_thin_comparison_are_not_rated_high_quality():
    take = make_take(rate=BASE_RATE * 1.5)
    spoken = [w if i < 28 else f"misheard{i}" for i, w in enumerate(take.words)]  # 70% of the transcript recognised

    thin = only(detect(take, spoken=spoken), "rushed_delivery")
    full = only(detect(take), "rushed_delivery")

    assert (full.evidence_quality, thin.evidence_quality) == ("high", "moderate")
    assert thin.limitations[-1].startswith("Only 28 of 40 transcript words could be compared")
    assert not any("could be compared" in text for text in full.limitations)
    assert thin.evidence[0].ratio == pytest.approx(1 / 1.5, abs=0.02)  # measured over the 28 words only


def test_reference_free_findings_are_not_downgraded_by_comparison_coverage():
    take = make_take(pauses={5: 2.0}, rate=BASE_RATE * 1.5)
    spoken = [w if i < 28 else f"misheard{i}" for i, w in enumerate(take.words)]
    spoken[20] = "um"
    result = detect(take, spoken=spoken)

    filler = only(result, "filler_word")
    assert filler.reference_interval is None
    assert not any("could be compared" in text for text in filler.limitations)


# --- Pause placement against a reference (limitations fix) -----------------------------------


def test_a_pause_the_reference_makes_and_the_participant_skips_is_reported():
    reference_take = make_take(pauses={14: 1.0})
    participant_take = make_take()
    result = run_detection(
        analysis_of(participant_take, transcript=TEXT), analysis_of(reference_take), transcript_source="user_provided"
    )

    finding = only(result, "irregular_pauses")
    assert finding.rule.rule_id == "pause_placement_vs_reference"
    # The participant interval spans the two words either side of where the reference pauses.
    assert (finding.start, finding.end) == (pytest.approx(participant_take.starts[14], abs=0.01), pytest.approx(participant_take.ends[15], abs=0.01))
    assert finding.reference_interval.start == pytest.approx(reference_take.ends[14], abs=0.06)
    assert finding.reference_interval.end == pytest.approx(reference_take.starts[15], abs=0.06)
    silence_evidence = finding.evidence[0]
    assert silence_evidence.participant_value == 0
    assert silence_evidence.reference_value == pytest.approx(1.0, abs=0.08)
    assert (finding.severity, finding.evidence_quality) == (None, "high")
    assert "excessive_pause" not in categories(result)
    assert rule(result, "irregular_pauses").measured == {"reference_internal_pauses": 1, "pauses_located_between_aligned_words": 1}


def test_matching_pause_placement_is_not_a_finding():
    reference = analysis_of(make_take(pauses={14: 1.0, 30: 0.8}))
    result = run_detection(analysis_of(make_take(pauses={14: 0.9, 30: 0.7}), transcript=TEXT), reference)

    assert result.findings == []
    assert rule(result, "irregular_pauses").status == "not_triggered"


def test_pauses_in_different_places_are_reported_in_both_directions():
    """The reference pauses after word 14; the participant pauses after word 30 instead."""
    reference = analysis_of(make_take(pauses={14: 1.0}))
    result = run_detection(analysis_of(make_take(pauses={30: 1.0}), transcript=TEXT), reference)

    assert sorted(categories(result)) == ["excessive_pause", "irregular_pauses"]
    assert only(result, "irregular_pauses").start < only(result, "excessive_pause").start


def test_pause_placement_is_withheld_without_a_usable_reference():
    alone = rule(run_detection(analysis_of(make_take(), source="transcribed")), "irregular_pauses")
    different = analysis_of(make_take(), transcript=" ".join(f"x{i}" for i in range(WORDS)))
    unusable = rule(run_detection(different, analysis_of(make_take(pauses={14: 1.0}))), "irregular_pauses")

    assert alone.status == "withheld"
    assert "there is no general rule for how they should be spaced" in alone.reason
    assert unusable.status == "withheld"
    assert "The reference could not be used" in unusable.reason


def test_pause_placement_in_heavy_noise_is_only_possible():
    reference_take = make_take(pauses={14: 1.5})
    take = make_take()
    rms = float(np.sqrt(np.mean(take.audio**2)))
    result = detect(take, reference=analysis_of(reference_take), audio=take.audio + noise(len(take.audio), rms / 10 ** (5 / 20)))

    for finding in [f for f in result.findings if f.category == "irregular_pauses"]:
        assert finding.title.startswith("Possibly") and finding.evidence_quality == "low"


# --- G9: missing features, invalid timestamps, insufficient evidence -------------------------


def test_words_with_invalid_or_out_of_order_times_are_not_compared():
    take = make_take(rate=BASE_RATE * 1.5)
    analysis = analysis_of(take, transcript=TEXT)
    words = analysis.alignment.words
    words[5] = words[5].model_copy(update={"start": words[5].end + 1.0})  # ends before it starts
    words[9] = words[9].model_copy(update={"start": 0.0, "end": 0.1})  # earlier than the word before it
    words[12] = words[12].model_copy(update={"start": None, "end": None, "status": "unaligned"})

    result = run_detection(analysis, REFERENCE, transcript_source="user_provided")

    assert result.alignment_status.words_compared == WORDS - 3
    assert only(result, "rushed_delivery").evidence[0].ratio == pytest.approx(1 / 1.5, abs=0.03)


def test_too_few_comparable_words_is_insufficient_evidence():
    take = make_take(12, rate=BASE_RATE * 1.5)
    spoken = [w if i < 8 else f"other{i}" for i, w in enumerate(take.words)]
    reference = analysis_of(make_take(12))
    result = run_detection(analysis_of(take, spoken=spoken, transcript=make_take(12).text), reference)

    assert result.alignment_status.status == "unavailable"
    assert "Only 8 words were recognised at the same position in both recordings" in result.alignment_status.reason


def test_too_few_aligned_runs_withholds_uneven_pacing():
    report = rule(detect(make_take(rate=BASE_RATE * 1.5), reference=REFERENCE), "uneven_pacing")
    short = run_detection(analysis_of(make_take(12, rate=4), transcript=make_take(12).text), analysis_of(make_take(12)))

    assert report.status == "not_triggered"  # 40 words give 8 stretches
    assert rule(short, "uneven_pacing").status == "withheld"
    assert "Needs at least 3 runs of 5 consecutive aligned words" in rule(short, "uneven_pacing").reason


def test_pause_rule_is_withheld_when_pauses_were_not_measured_in_the_reference():
    reference = analysis_of(REFERENCE_TAKE)
    reference.features.pauses = reference.features.pauses.model_copy(update={"status": "unavailable", "intervals": []})
    # A reference whose pauses are unavailable is unusable as a whole, so nothing is compared against it.
    result = run_detection(analysis_of(make_take(pauses={14: 1.5}), transcript=TEXT), reference)

    assert result.alignment_status.status == "unavailable"
    assert only(result, "excessive_pause").rule.rule_id == "long_pause"


# --- G7 / E: pitch on valid voiced frames only -----------------------------------------------


def test_narrow_pitch_variation_is_a_possible_finding_measured_in_semitones():
    flat = make_take(swing_semitones=0.4)
    result = detect(flat)

    finding = only(result, "pitch_monotony")
    spread = finding.evidence[0]
    assert finding.title.startswith("Possibly")
    assert (spread.feature, spread.unit) == ("pitch_range_5th_to_95th_percentile", "semitones")
    # The contour swings +/-swing semitones as a sine; its 5th-95th percentile range is about 1.9 x the swing.
    assert spread.participant_value == pytest.approx(1.9 * 0.4, abs=0.25)
    assert spread.reference_value == pytest.approx(1.9 * 3.0, abs=0.6)
    assert spread.ratio < 0.2
    assert finding.severity is None
    assert finding.evidence[2].feature == "voiced_frames_used"


def test_pitch_height_alone_never_triggers_or_prevents_a_finding():
    """The same melody sung low, typical and high gives the same result against a typical-pitch reference."""
    for base in (75.0, 150.0, 280.0):
        assert "pitch_monotony" not in categories(detect(make_take(base_hz=base)))
        assert only(detect(make_take(base_hz=base, swing_semitones=0.4)), "pitch_monotony").evidence[0].ratio < 0.2


def test_a_low_voice_is_measured_not_discarded():
    result = detect(make_take(base_hz=68.0))

    assert rule(result, "pitch_monotony").status == "not_triggered"
    assert rule(result, "pitch_monotony").measured["participant_range_semitones"] == pytest.approx(1.9 * 3.0, abs=0.6)
    assert not any(issue.code == "pitch_unreliable" for issue in result.signal_quality.issues)


def test_narrow_pitch_without_a_reference_uses_the_absolute_limit():
    flat = run_detection(analysis_of(make_take(swing_semitones=0.4), source="transcribed"))
    lively = run_detection(analysis_of(make_take(), source="transcribed"))

    finding = only(flat, "pitch_monotony")
    assert finding.rule.rule_id == "pitch_range"
    assert finding.rule.thresholds == {"monotony_range_semitones": 4.0}
    assert finding.evidence[0].reference_value is None
    assert "pitch_monotony" not in categories(lively)


def test_unvoiced_frames_are_skipped_not_filled_in():
    features = extract_features(loaded(make_take().audio))
    full = pitch_window_stats(features, 0, 16)
    gappy = features.model_copy(deep=True)
    gappy.pitch.series.values = [None if i % 3 == 0 else v for i, v in enumerate(gappy.pitch.series.values)]

    stats = pitch_window_stats(gappy, 0, 16)

    assert stats["voiced_frames"] < 0.7 * full["voiced_frames"]
    assert stats["range_semitones"] == pytest.approx(full["range_semitones"], abs=0.3)
    assert pitch_window_stats(features, 100, 200) == {"voiced_frames": 0.0}


def test_too_few_voiced_frames_withholds_the_pitch_rule():
    """Whispered speech: the same word rhythm, but hissing noise instead of a voice, apart from two voiced words."""
    take = make_take()
    step = len(take.audio) // WORDS
    envelope = np.sin(np.pi * (np.arange(len(take.audio)) % step) / step) ** 2
    whispered = (noise(len(take.audio), 0.2) * envelope).astype(np.float32)
    whispered[: 2 * step] = take.audio[: 2 * step]
    analysis = analysis_of(take, audio=whispered, source="transcribed")

    result = run_detection(analysis)
    report = rule(result, "pitch_monotony")

    assert result.signal_quality.usable
    assert analysis.features.pitch.voiced_fraction < 0.15
    assert report.status == "withheld"
    assert "voiced frames" in report.reason or "not reliable" in report.reason
    assert "pitch_monotony" not in categories(result)


def test_octave_errors_inside_the_window_withhold_the_pitch_rule():
    analysis = analysis_of(make_take(swing_semitones=0.4), transcript=TEXT)
    values = analysis.features.pitch.series.values
    analysis.features.pitch.series.values = [v * 2 if v and i % 15 == 0 else v for i, v in enumerate(values)]

    report = rule(run_detection(analysis, REFERENCE), "pitch_monotony")

    assert report.status == "withheld"
    assert "octave jumps" in report.reason


def creaky_take():
    """A voice that keeps dropping from 85 Hz into a 56 Hz creak, right at the bottom of what the tracker follows."""
    return make_take(base_hz=85.0, swing_semitones=0.0, rate=BASE_RATE), make_take(base_hz=56.0, swing_semitones=0.0)


def test_a_creaky_low_voice_is_flagged_unreliable_and_not_judged():
    modal, creak = creaky_take()
    step = len(modal.audio) // WORDS
    audio = modal.audio.copy()
    for i in range(0, WORDS, 3):  # every third word is creaky
        audio[i * step : (i + 1) * step] = creak.audio[i * step : (i + 1) * step]
    analysis = analysis_of(modal, audio=audio, transcript=TEXT)

    result = run_detection(analysis, REFERENCE, transcript_source="user_provided")

    pitch = analysis.features.pitch
    assert pitch.status == "measured" and pitch.reliability == "low"
    assert "changes when the tracker's lower limit is nudged" in pitch.limitations[0]
    assert pitch.median_hz == pytest.approx(85, abs=3)  # the valid low pitch is still reported
    issue = next(i for i in result.signal_quality.issues if i.code == "pitch_unreliable")
    assert issue.affects == ["pitch_monotony"]
    report = rule(result, "pitch_monotony")
    assert report.status == "withheld"
    assert "not reliable for this recording" in report.reason
    assert "pitch_monotony" not in categories(result)


def test_an_unreliable_reference_pitch_withholds_the_comparison_only():
    reference = analysis_of(REFERENCE_TAKE)
    reference.features.pitch = reference.features.pitch.model_copy(update={"reliability": "low"})

    report = rule(run_detection(analysis_of(make_take(swing_semitones=0.4), transcript=TEXT), reference), "pitch_monotony")

    assert report.status == "withheld"
    assert "not reliable for the reference recording" in report.reason


# --- G8 / E: noise, clipping and other signal-quality safeguards ------------------------------


def test_a_pause_in_heavy_noise_is_only_a_possible_finding_with_no_severity():
    take = make_take(pauses={14: 1.5})
    rms = float(np.sqrt(np.mean(take.audio[take.audio != 0] ** 2)))
    noisy = take.audio + noise(len(take.audio), rms / 10 ** (5 / 20))  # 5 dB signal-to-noise
    result = detect(take, audio=noisy)

    assert any(issue.code == "pauses_low_confidence" for issue in result.signal_quality.issues)
    pauses = [f for f in result.findings if f.category == "excessive_pause"]
    assert pauses
    assert all(f.title.startswith("Possible") and f.evidence_quality == "low" and f.severity is None for f in pauses)
    assert all(any("uncertain whether this is true silence" in text for text in f.limitations) for f in pauses)


def test_clipping_lowers_the_evidence_quality_of_every_finding():
    take = make_take(rate=BASE_RATE * 1.5, pauses={14: 1.5})
    result = detect(take, audio=np.clip(take.audio * 8, -1, 1))

    issue = next(i for i in result.signal_quality.issues if i.code == "clipping_detected")
    assert issue.level == "warning" and "rushed_delivery" in issue.affects
    assert result.findings
    assert all(f.evidence_quality == "low" and f.severity is None for f in result.findings if f.category in issue.affects)
    assert all(any("Clipping detected" in text for text in f.limitations) for f in result.findings)


@pytest.mark.parametrize(
    ("audio", "code"),
    [(silence(8.0), "no_signal"), (noise(8 * SR, 0.1), "speech_not_separable"), (make_take(5).audio, "too_short")],
    ids=["silence", "steady-noise", "too-short"],
)
def test_unusable_audio_produces_no_findings_and_says_why(audio, code):
    analysis = analysis_of(make_take(), audio=audio, source="transcribed")

    result = run_detection(analysis)

    assert not result.signal_quality.usable
    assert [i.code for i in result.signal_quality.issues if i.level == "blocking"] == [code]
    assert result.findings == []
    checked = [r for r in result.rules if r.category != "unclear_articulation"]
    assert all(r.status == "withheld" and r.reason.startswith("The recording is not usable:") for r in checked)


def test_silence_measured_inside_a_window_is_the_overlap_only():
    features = extract_features(loaded(make_take(pauses={14: 1.0}).audio))
    pause = features.pauses.intervals[0]

    assert silence_within(features, 0, 100) == pytest.approx(1.0, abs=0.08)
    assert silence_within(features, pause.start + 0.4, 100) == pytest.approx(pause.end - pause.start - 0.4, abs=0.001)
    assert silence_within(features, 0, pause.start) == 0


# --- D6 / D7 / D8 and C: structure, severity, documentation -----------------------------------


def test_articulation_is_never_reported_and_says_why():
    report = rule(detect(make_take(rate=BASE_RATE * 1.5, pauses={14: 1.5}, swing_semitones=0.4)), "unclear_articulation")

    assert report.status == "not_supported"
    assert "would penalise who is speaking" in report.reason


def test_every_finding_is_complete_and_stays_inside_the_recording():
    take = make_take(rate=BASE_RATE * 1.5, pauses={14: 1.5}, swing_semitones=0.4)
    spoken = list(take.words)
    spoken[30] = "um"
    analysis = analysis_of(take, spoken=spoken, transcript=TEXT)
    result = run_detection(analysis, REFERENCE, transcript_source="user_provided")
    duration = analysis.features.audio.duration_sec

    assert {"rushed_delivery", "excessive_pause", "pitch_monotony", "filler_word"} <= set(categories(result))
    assert len({f.id for f in result.findings}) == len(result.findings)
    for finding in result.findings:
        assert finding.id.startswith(finding.rule.rule_id + ":")
        assert 0 <= finding.start < finding.end <= duration + 0.01
        assert finding.evidence and all(e.feature and e.unit for e in finding.evidence)
        assert finding.comparison_method and finding.explanation and finding.limitations
        assert finding.rule.description and finding.rule.thresholds
        assert finding.evidence_quality in ("high", "moderate", "low")
        if finding.reference_interval:
            assert finding.reference_interval.start < finding.reference_interval.end
    assert result.findings == sorted(result.findings, key=lambda f: (f.start, f.end, f.id))


def test_severity_is_only_given_by_the_two_reference_based_magnitude_rules():
    take = make_take(48, rate=lambda i: 2.2 if 16 <= i < 32 else 4.2, pauses={14: 1.5}, swing_semitones=0.4)
    spoken = list(take.words)
    spoken[40] = "uh"
    result = run_detection(analysis_of(take, spoken=spoken, transcript=make_take(48).text), analysis_of(make_take(48)))

    with_severity = {f.rule.rule_id for f in result.findings if f.severity}
    without = {f.rule.rule_id for f in result.findings if not f.severity}
    assert with_severity <= {"pace_vs_reference", "pause_vs_reference"}
    assert {"pacing_vs_reference", "filler_lexicon", "pitch_range_vs_reference"} <= without
    assert all(f.severity_basis for f in result.findings if f.severity)
    assert all(f.severity_basis is None for f in result.findings if not f.severity)


def test_thresholds_are_configurable_and_reported():
    take = make_take(rate=BASE_RATE * 1.15)
    strict = DetectionSettings(pace_ratio_threshold=1.3)
    lenient = run_detection(analysis_of(take, transcript=TEXT), REFERENCE)
    result = run_detection(analysis_of(take, transcript=TEXT), REFERENCE, settings=strict)

    assert "rushed_delivery" in categories(lenient)
    assert "rushed_delivery" not in categories(result)
    assert rule(result, "rushed_delivery").thresholds == {"pace_ratio_threshold": 1.3}
    assert only(lenient, "rushed_delivery").rule.thresholds == {"pace_ratio_threshold": 1.1, "moderate_from": 1.2, "major_from": 1.35}


def test_alignment_status_documents_window_strategy_and_normalisation():
    take = make_take(rate=BASE_RATE * 1.5)
    status = detect(take).alignment_status

    assert status.transcript_source == "user_provided"
    assert (status.transcript_word_count, status.words_compared) == (WORDS, WORDS)
    assert (status.participant_coverage, status.reference_coverage) == (1.0, 1.0)
    assert status.participant_window.end == pytest.approx(take.ends[-1], abs=0.01)
    assert status.reference_window.end == pytest.approx(REFERENCE_TAKE.ends[-1], abs=0.01)
    assert "Raw timestamps are never compared across recordings" in status.strategy
    assert "semitones relative to each speaker's own median" in status.normalization
    assert "Loudness, spectral and MFCC features are not compared" in status.normalization


def test_energy_spectral_and_mfcc_features_are_left_out_of_the_comparison_with_reasons():
    comparison = compare_deliveries(REFERENCE, analysis_of(make_take(rate=BASE_RATE * 1.5), transcript=TEXT))

    assert set(comparison.not_compared) == {"energy_db", "spectral_and_mfcc"}
    assert not any("energy" in m.name or "mfcc" in m.name or "spectral" in m.name for m in comparison.global_metrics)


def test_no_finding_or_limitation_claims_a_cause_or_a_diagnosis():
    take = make_take(rate=BASE_RATE * 1.5, pauses={14: 1.5}, swing_semitones=0.4)
    result = detect(take)
    text = result.model_dump_json().lower()

    for word in ("because you", "anxious", "nervous", "disorder", "diagnos", "accent is"):
        assert word not in text.replace("a diagnosis, or", "")
    assert any("not proof of a problem, a diagnosis, or a statement about cause" in line for line in result.limitations)


# --- Rule-based coaching (limitations fix) ---------------------------------------------------


def test_one_tip_per_kind_of_finding_quoting_the_measured_evidence():
    take = make_take(rate=BASE_RATE * 1.5, pauses={5: 1.5, 14: 1.5, 22: 1.5, 30: 1.5}, swing_semitones=0.4)
    spoken = list(take.words)
    spoken[35] = "um"
    result = run_detection(analysis_of(take, spoken=spoken, transcript=TEXT), REFERENCE, transcript_source="user_provided")

    tips = build_coaching(result.findings)

    by_category = {tip.category: tip for tip in tips}
    assert set(by_category) == {f.category for f in result.findings}
    assert len(tips) == len(by_category)
    pause_tip = by_category["excessive_pause"]
    pauses = [f for f in result.findings if f.category == "excessive_pause"]
    assert pause_tip.finding_ids == [f.id for f in pauses] and len(pauses) == 4
    # The first three are quoted in full; the rest are counted, never dropped silently.
    assert pause_tip.based_on == " ".join(f.explanation for f in pauses[:3]) + " And 1 more like this."
    assert by_category["filler_word"].action == "Replace the filler sounds with a short silent pause."
    assert all(tip.source == "rule_based" for tip in tips)


def test_coaching_differs_with_and_without_a_reference_and_never_exists_without_a_finding():
    with_reference = build_coaching(detect(make_take(rate=BASE_RATE * 1.5)).findings)
    alone = build_coaching(run_detection(analysis_of(make_take(rate=3.75), source="transcribed")).findings)

    assert with_reference[0].id == "tip:pace_vs_reference:rushed_delivery"
    assert alone[0].id == "tip:pace_words_per_minute:rushed_delivery"
    assert "reference" in with_reference[0].practice and "Adding a reference recording" in alone[0].practice
    assert build_coaching([]) == []


def test_weak_evidence_adds_a_caution_and_unknown_rules_get_no_invented_advice():
    take = make_take(rate=BASE_RATE * 1.5)
    result = detect(take, audio=np.clip(take.audio * 8, -1, 1))
    tips = build_coaching(result.findings)

    assert tips and all(tip.caution for tip in tips)
    unknown = result.findings[0].model_copy(deep=True)
    unknown.rule.rule_id = "a_rule_with_no_template"
    assert build_coaching([unknown]) == []


def test_the_caution_says_how_much_of_the_evidence_is_weak():
    _, analysis = spoken_with({9: "um", 20: "uh", 30: "er"}, probabilities={9: 0.3})

    (tip,) = build_coaching(run_detection(analysis).findings)

    assert tip.caution == "1 of the 3 findings behind this have weak evidence; see their limitations before acting on it."


def test_coaching_text_makes_no_causal_or_personal_claims():
    text = " ".join(action + " " + practice for action, practice in TEMPLATES.values()).lower()

    for phrase in ("because you", "nervous", "anxious", "confident", "accent", "you are a", "bad", "poor", "wrong"):
        assert phrase not in text


# --- Outstanding-limitations fix: fillers ----------------------------------------------------


@pytest.mark.parametrize("pair", [("the", "the"), ("I", "I"), ("and", "and"), ("very", "very"), ("no", "no")])
def test_repeated_ordinary_words_are_not_fillers(pair):
    _, analysis = spoken_with({9: pair[0], 10: pair[1]})

    assert "filler_word" not in categories(run_detection(analysis))


def test_found_fillers_are_reported_as_a_lower_bound_not_a_complete_count():
    _, analysis = spoken_with({9: "um"})

    report = rule(run_detection(analysis), "filler_word")

    assert report.status == "triggered"
    assert "may be higher" in report.reason
    assert "transcribed" in report.reason


def test_nothing_recognised_is_withheld_not_reported_as_no_fillers():
    """An empty transcript says nothing about fillers, so the rule must not say it checked and found none."""
    analysis = analysis_of(make_take(), source="transcribed")
    analysis.transcription = analysis.transcription.model_copy(
        update={"status": "no_speech", "text": "", "words": [], "segments": [], "word_timestamps": "unavailable"}
    )
    analysis.alignment = None

    report = rule(run_detection(analysis), "filler_word")

    assert report.status == "withheld"
    assert report.findings == 0


# --- Outstanding-limitations fix: pause placement --------------------------------------------


def test_neither_recording_pausing_is_checked_and_clean():
    report = rule(detect(make_take()), "irregular_pauses")

    assert (report.status, report.findings) == ("not_triggered", 0)
    assert report.measured == {"reference_internal_pauses": 0, "pauses_located_between_aligned_words": 0}


def test_two_reference_pauses_between_the_same_aligned_words_give_one_finding():
    """Word 15 was not recognised in the participant recording, so the reference's pauses before and after it
    both fall between the same two aligned words. That is one place, not two findings."""
    reference_take = make_take(pauses={14: 1.0, 15: 1.0})
    participant = analysis_of(make_take(), transcript=TEXT)
    participant.alignment.words[15] = participant.alignment.words[15].model_copy(update={"status": "unaligned", "start": None, "end": None})

    result = run_detection(participant, analysis_of(reference_take), transcript_source="user_provided")

    placement = [f for f in result.findings if f.category == "irregular_pauses"]
    assert len(placement) == 1
    assert len({f.id for f in result.findings}) == len(result.findings)
    assert placement[0].evidence[0].reference_value == pytest.approx(2.0, abs=0.15)  # both pauses, counted once
    assert placement[0].evidence[0].participant_value == 0


def test_a_reference_pause_that_cannot_be_placed_between_aligned_words_is_not_compared():
    reference_take = make_take(pauses={14: 1.0})
    participant = analysis_of(make_take(), transcript=TEXT)
    for i in range(12, 18):  # the words around the reference's pause were not recognised
        participant.alignment.words[i] = participant.alignment.words[i].model_copy(update={"status": "unaligned", "start": None, "end": None})

    result = run_detection(participant, analysis_of(reference_take), transcript_source="user_provided")
    report = rule(result, "irregular_pauses")

    assert "irregular_pauses" not in categories(result)
    assert report.measured == {"reference_internal_pauses": 1, "pauses_located_between_aligned_words": 0}
    assert "1 reference pause(s) could not be placed between aligned words" in report.reason


def test_an_unreliable_reference_pause_measurement_makes_placement_findings_only_possible():
    reference = analysis_of(make_take(pauses={14: 1.0}))
    reference.features.pauses = reference.features.pauses.model_copy(update={"reliability": "low"})

    finding = only(run_detection(analysis_of(make_take(), transcript=TEXT), reference), "irregular_pauses")

    assert finding.title.startswith("Possibly")
    assert (finding.evidence_quality, finding.severity) == ("low", None)


def test_no_event_is_reported_twice_across_the_pause_rules():
    reference = analysis_of(make_take(pauses={8: 1.0, 20: 1.2}))
    result = run_detection(analysis_of(make_take(pauses={14: 1.5, 30: 2.0}), transcript=TEXT), reference)

    pause_like = [f for f in result.findings if f.category in ("excessive_pause", "irregular_pauses")]
    assert sorted(f.category for f in pause_like) == ["excessive_pause", "excessive_pause", "irregular_pauses", "irregular_pauses"]
    for a in pause_like:
        for b in pause_like:
            if a is not b:
                assert a.end <= b.start or b.end <= a.start  # no two findings cover the same stretch


# --- Outstanding-limitations fix: pitch ------------------------------------------------------


def test_missing_pitch_is_not_measurable_which_is_different_from_no_issue_found():
    lively = analysis_of(make_take(), transcript=TEXT)
    untracked = analysis_of(make_take(), transcript=TEXT)
    untracked.features.pitch = untracked.features.pitch.model_copy(
        update={"status": "unavailable", "series": None, "median_hz": None, "range_semitones": None, "reliability": None,
                "limitations": ["Pitch was not computed (no tracker)."]}
    )  # fmt: skip

    measured = rule(run_detection(lively, REFERENCE), "pitch_monotony")
    unmeasurable = rule(run_detection(untracked, REFERENCE), "pitch_monotony")

    assert measured.status == "not_triggered"
    assert measured.measured["participant_range_semitones"] > 0
    assert unmeasurable.status == "withheld"
    assert unmeasurable.measured == {}
    assert "Pitch was not computed" in unmeasurable.reason


def test_unvoiced_frames_stay_missing_and_are_never_turned_into_zero():
    features = extract_features(loaded(make_take(pauses={14: 1.0}).audio))
    values = features.pitch.series.values

    assert None in values  # the pause and the gaps between words have no pitch
    assert 0 not in values and 0.0 not in values
    assert min(v for v in values if v is not None) >= features.pitch.tracking_floor_hz * 0.99


# --- Outstanding-limitations fix: unmatched and extra words ----------------------------------


def test_extra_words_the_recogniser_heard_are_counted_and_not_treated_as_a_delivery_difference():
    """The participant said one word that is not in the transcript. It is reported as unmatched, and the
    comparison of the words that are in the transcript is unaffected."""
    take = make_take(WORDS + 1)
    spoken = [*REFERENCE_TAKE.words[:20], "extra", *REFERENCE_TAKE.words[20:]]
    result = run_detection(analysis_of(take, spoken=spoken, transcript=TEXT), REFERENCE, transcript_source="user_provided")

    status = result.alignment_status
    assert status.unmatched_recognised == {"participant": 1, "reference": 0}
    assert status.words_compared == WORDS
    assert result.findings == []


# --- Acoustic check for filled pauses the recogniser left out ---------------------------------


def with_hum(seconds: float, *, glide_semitones: float = 0.0, after_word: int = 10, gap: float = 0.8):
    """A take with a silent gap after `after_word`, and a steady voiced 'uh' placed in it that no recognised word covers."""
    take = make_take(pauses={after_word: gap})
    n = int(round(seconds * SR))
    t = np.arange(n) / SR
    f0 = 150 * 2 ** (glide_semitones * t / seconds / 12)
    phase = 2 * np.pi * np.cumsum(f0) / SR
    hum = sum(np.sin(k * phase) / k for k in range(1, 6)) * np.minimum(1, np.minimum(t, t[::-1]) / 0.03)
    start = take.ends[after_word] + (gap - seconds) / 2
    first = int(round(start * SR))
    audio = take.audio.copy()
    audio[first : first + n] += (0.25 * hum).astype(np.float32)
    return take, audio, start


def acoustic(result):
    return [f for f in result.findings if f.rule.rule_id == "filled_pause_acoustic"]


def test_a_steady_voiced_sound_between_recognised_words_is_a_possible_filled_pause():
    take, audio, start = with_hum(0.45)

    result = run_detection(analysis_of(take, audio=audio, source="transcribed"))

    (finding,) = acoustic(result)
    assert finding.category == "filler_word"
    assert finding.title == "Possible filled pause"
    assert finding.evidence_quality == "low" and finding.severity is None
    assert finding.start == pytest.approx(start, abs=0.06)
    assert finding.end == pytest.approx(start + 0.45, abs=0.06)
    outside = next(e for e in finding.evidence if e.feature == "time_outside_recognised_words")
    assert outside.participant_value >= 0.4
    tip = next(t for t in build_coaching(result.findings) if t.id == "tip:filled_pause_acoustic:filler_word")
    assert tip.certainty == "uncertain"


@pytest.mark.parametrize(
    "seconds, glide",
    [(0.12, 0.0), (0.45, 12.0)],
    ids=["too short", "pitch moves like speech"],
)
def test_short_or_moving_voiced_sounds_are_not_filled_pauses(seconds, glide):
    take, audio, _ = with_hum(seconds, glide_semitones=glide)

    assert acoustic(run_detection(analysis_of(take, audio=audio, source="transcribed"))) == []


def test_steady_sounds_inside_recognised_words_are_not_filled_pauses():
    take = make_take(rate=1.2)  # long, steady words: each is one held pitch

    result = run_detection(analysis_of(take, source="transcribed"))

    assert acoustic(result) == []
    report = next(r for r in result.rules if r.rule_id == "filled_pause_acoustic")
    assert report.status == "not_triggered"
    assert "can still be missed" in report.reason


def test_a_filler_the_recogniser_heard_is_not_counted_again_by_the_acoustic_check():
    take, audio, start = with_hum(0.45)
    analysis = analysis_of(take, audio=audio, source="transcribed")
    words = analysis.transcription.words
    words.insert(11, words[10].model_copy(update={"word": "uh", "start": round(start + 0.3, 3), "end": round(start + 0.42, 3)}))

    fillers = [f for f in run_detection(analysis).findings if f.category == "filler_word"]

    assert [f.rule.rule_id for f in fillers] == ["filler_lexicon"]


def test_the_acoustic_check_is_withheld_without_word_timestamps():
    analysis = analysis_of(make_take())
    analysis.transcription = None

    report = next(r for r in run_detection(analysis).rules if r.rule_id == "filled_pause_acoustic")
    assert report.status == "withheld"
