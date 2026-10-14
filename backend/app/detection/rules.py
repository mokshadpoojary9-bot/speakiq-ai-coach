"""Transparent, configurable rules that turn measurements into temporal findings.

Every rule either reports findings backed by measured values and a participant-audio interval,
reports that it checked and found nothing, or says why it could not check. No rule estimates a
value it does not have, and none looks at who is speaking: pitch is only ever compared in
semitones relative to the speaker's own median, never in Hz.
"""

import re
from dataclasses import dataclass

import numpy as np

from ..audio.schemas import AudioFeatures
from ..comparison.schemas import DeliveryAnalysis
from ..speech.alignment import normalize
from .schemas import (
    AlignmentStatus,
    DetectionResult,
    DetectionSettings,
    Evidence,
    Finding,
    QualityIssue,
    RuleReport,
    RuleUsed,
    SignalQuality,
    Span,
)

OCTAVE_JUMP_SEMITONES = 8.0
MAX_WINDOW_JUMP_FRACTION = 0.01
# How far a recognised word boundary may sit inside a measured pause and still count as outside it.
BOUNDARY_TOLERANCE_SEC = 0.2
MAX_WORDS_ACROSS_PAUSE = 3

ALIGNMENT_STRATEGY = (
    "Both recordings are aligned to one shared transcript. A word is compared only if it was recognised at that "
    "position in both recordings, so each measurement covers the same spoken words. Raw timestamps are never "
    "compared across recordings."
)
PITCH_NORMALIZATION = (
    "Pitch is converted to semitones relative to each speaker's own median before comparison. "
    "Durations and pauses are in seconds. Loudness, spectral and MFCC features are not compared."
)


@dataclass(frozen=True)
class WordPair:
    index: int
    word: str
    ref_start: float
    ref_end: float
    par_start: float
    par_end: float


def _round(value: float | None, digits: int = 3) -> float | None:
    return None if value is None else round(float(value), digits)


def _evidence(feature: str, unit: str, participant: float | None, reference: float | None = None) -> Evidence:
    both = participant is not None and reference is not None
    return Evidence(
        feature=feature,
        unit=unit,
        participant_value=_round(participant),
        reference_value=_round(reference),
        difference=_round(participant - reference) if both else None,
        ratio=_round(participant / reference) if both and reference else None,
    )


def _finding_id(rule_id: str, start: float, end: float) -> str:
    return f"{rule_id}:{int(round(start * 1000))}-{int(round(end * 1000))}"


# --- Signal quality --------------------------------------------------------------------------


def assess_signal_quality(features: AudioFeatures, settings: DetectionSettings) -> SignalQuality:
    issues: list[QualityIssue] = []
    if features.audio.peak_amplitude < 1e-3:
        issues.append(QualityIssue(code="no_signal", level="blocking", message="The recording is silent or almost silent."))
    elif features.pauses.status == "unavailable":
        issues.append(
            QualityIssue(
                code="speech_not_separable",
                level="blocking",
                message=features.pauses.limitations[0] if features.pauses.limitations else "Speech could not be separated from the background.",
            )
        )
    if features.audio.duration_sec < settings.min_duration_sec:
        issues.append(
            QualityIssue(
                code="too_short",
                level="blocking",
                message=f"The recording is {features.audio.duration_sec:.1f} s long; delivery rules need at least {settings.min_duration_sec:g} s.",
            )
        )
    clipping = features.clipping
    if clipping.verdict == "detected":
        issues.append(
            QualityIssue(
                code="clipping_detected",
                level="warning",
                message=f"Clipping detected ({clipping.flat_top_runs} flat-topped peaks). The recording is distorted, so every measurement is less trustworthy.",
                affects=["rushed_delivery", "slow_delivery", "excessive_pause", "irregular_pauses", "uneven_pacing", "pitch_monotony", "filler_word"],
            )
        )
    elif clipping.verdict == "uncertain":
        issues.append(QualityIssue(code="clipping_uncertain", level="warning", message=clipping.limitations[0]))
    if features.pitch.status != "measured" or features.pitch.reliability == "low":
        issues.append(
            QualityIssue(
                code="pitch_unreliable",
                level="warning",
                message=features.pitch.limitations[0] if features.pitch.limitations else "Pitch could not be tracked reliably.",
                affects=["pitch_monotony"],
            )
        )
    if features.pauses.status == "measured" and features.pauses.reliability == "low":
        issues.append(
            QualityIssue(
                code="pauses_low_confidence",
                level="warning",
                message=features.pauses.limitations[0],
                affects=["excessive_pause", "irregular_pauses", "rushed_delivery", "slow_delivery", "uneven_pacing"],
            )
        )
    return SignalQuality(usable=not any(issue.level == "blocking" for issue in issues), issues=issues)


def _quality(base: str, category: str, quality: SignalQuality) -> str:
    return "low" if any(category in issue.affects for issue in quality.issues) else base


def _quality_notes(category: str, quality: SignalQuality) -> list[str]:
    return [issue.message for issue in quality.issues if category in issue.affects]


# --- Measurement helpers ---------------------------------------------------------------------


def silence_within(features: AudioFeatures, start: float, end: float) -> float:
    """Measured silence, in seconds, inside [start, end]."""
    return sum(max(0.0, min(pause.end, end) - max(pause.start, start)) for pause in features.pauses.intervals)


def pitch_window_stats(features: AudioFeatures, start: float, end: float) -> dict[str, float] | None:
    """Variation of voiced pitch inside a window, in semitones around this speaker's median there.

    Unvoiced frames are skipped, never filled in. Returns None when pitch was not measured.
    """
    series = features.pitch.series
    if features.pitch.status != "measured" or series is None:
        return None
    times = series.start_sec + np.arange(len(series.values)) * series.hop_sec
    hz = np.array([np.nan if v is None else v for v in series.values], dtype=np.float64)
    inside = hz[(times >= start) & (times <= end)]
    voiced = inside[~np.isnan(inside)]
    if len(voiced) < 2:
        return {"voiced_frames": float(len(voiced))}
    semitones = 12 * np.log2(voiced / np.median(voiced))
    p5, p95 = np.percentile(semitones, [5, 95])
    adjacent = ~np.isnan(inside[:-1]) & ~np.isnan(inside[1:])
    leaps = np.abs(12 * np.log2(inside[1:][adjacent] / inside[:-1][adjacent])) if adjacent.any() else np.array([])
    return {
        "voiced_frames": float(len(voiced)),
        "range_semitones": float(p95 - p5),
        "sd_semitones": float(np.std(semitones)),
        "octave_jump_fraction": float(np.mean(leaps > OCTAVE_JUMP_SEMITONES)) if len(leaps) else 0.0,
    }


# --- Alignment -------------------------------------------------------------------------------


def build_alignment(
    participant: DeliveryAnalysis,
    reference: DeliveryAnalysis | None,
    transcript_source: str,
    settings: DetectionSettings,
    withheld_reason: str | None = None,
) -> tuple[AlignmentStatus, list[WordPair]]:
    if reference is None:
        return AlignmentStatus(status="no_reference", reason="No reference recording was supplied.", transcript_source=transcript_source), []

    def unavailable(reason: str, **fields) -> tuple[AlignmentStatus, list[WordPair]]:
        return (
            AlignmentStatus(
                status="unavailable", reason=reason, strategy=ALIGNMENT_STRATEGY, transcript_source=transcript_source, **fields
            ),
            [],
        )

    if withheld_reason:
        return unavailable(withheld_reason)
    ref, par = reference.alignment, participant.alignment
    if ref is None or par is None:
        which = "reference" if ref is None else "participant"
        return unavailable(f"The {which} recording has no word alignment, so the recordings cannot be lined up.")
    if [normalize(w.word) for w in ref.words] != [normalize(w.word) for w in par.words]:
        return unavailable("The two recordings were aligned to different transcripts.")
    coverage = {
        "participant_coverage": par.coverage,
        "reference_coverage": ref.coverage,
        "transcript_word_count": len(ref.words),
        "unmatched_recognised": {"participant": len(par.unmatched_recognized), "reference": len(ref.unmatched_recognized)},
    }
    for name, alignment in (("reference", ref), ("participant", par)):
        if alignment.coverage < settings.min_alignment_coverage:
            return unavailable(
                f"Only {alignment.coverage:.0%} of the transcript's words were recognised in the {name} recording "
                f"(at least {settings.min_alignment_coverage:.0%} is needed), so it does not appear to contain the same words.",
                **coverage,
            )
    pairs: list[WordPair] = []
    excluded = {
        "not_recognised_in_reference": 0,
        "not_recognised_in_participant": 0,
        "invalid_or_out_of_order_times": 0,
        "isolated_match": 0,
    }
    for r, p in zip(ref.words, par.words):
        if r.status != "aligned" or None in (r.start, r.end):
            excluded["not_recognised_in_reference"] += 1
            continue
        if p.status != "aligned" or None in (p.start, p.end):
            excluded["not_recognised_in_participant"] += 1
            continue
        if r.end >= r.start and p.end >= p.start:
            pairs.append(WordPair(r.index, p.word, r.start, r.end, p.start, p.end))
        else:
            excluded["invalid_or_out_of_order_times"] += 1
    # A matched word with no matched neighbour on either side is where a repeated word such as 'the'
    # gets matched to the wrong occurrence, so it is not trusted as an anchor. This is done before the
    # order check so that one badly placed word cannot knock out the correctly placed words after it.
    anchored = [pair for run in _runs(pairs) if len(run) >= 2 for pair in run]
    excluded["isolated_match"] = len(pairs) - len(anchored)
    pairs = []
    for pair in anchored:
        # A word is only usable if it comes after the previous usable word in both recordings.
        if not pairs or (pair.ref_start >= pairs[-1].ref_start and pair.par_start >= pairs[-1].par_start):
            pairs.append(pair)
        else:
            excluded["invalid_or_out_of_order_times"] += 1
    coverage["words_excluded"] = {reason: count for reason, count in excluded.items() if count}
    if len(pairs) < settings.min_compared_words:
        return unavailable(
            f"Only {len(pairs)} words were recognised at the same position in both recordings; "
            f"at least {settings.min_compared_words} are needed.",
            **coverage,
        )
    return (
        AlignmentStatus(
            status="aligned",
            strategy=ALIGNMENT_STRATEGY,
            transcript_source=transcript_source,
            words_compared=len(pairs),
            participant_window=Span(start=pairs[0].par_start, end=pairs[-1].par_end),
            reference_window=Span(start=pairs[0].ref_start, end=pairs[-1].ref_end),
            normalization=PITCH_NORMALIZATION,
            **coverage,
        ),
        pairs,
    )


def _downgrade_for_thin_comparison(findings: list[Finding], alignment: AlignmentStatus, settings: DetectionSettings) -> None:
    """Reference-based findings are not 'high' quality when much of the transcript could not be compared."""
    if alignment.status != "aligned" or not alignment.transcript_word_count:
        return
    fraction = alignment.words_compared / alignment.transcript_word_count
    if fraction >= settings.high_quality_compared_fraction:
        return
    note = (
        f"Only {alignment.words_compared} of {alignment.transcript_word_count} transcript words could be compared "
        "(the rest were misrecognised or skipped), so this rests on part of the recording."
    )
    for finding in findings:
        if finding.reference_interval is not None:
            if finding.evidence_quality == "high":
                finding.evidence_quality = "moderate"
            finding.limitations.append(note)


def _runs(pairs: list[WordPair]) -> list[list[WordPair]]:
    """Groups of words that are consecutive in the transcript, so no skipped word hides inside a group."""
    runs: list[list[WordPair]] = []
    for pair in pairs:
        if runs and pair.index == runs[-1][-1].index + 1:
            runs[-1].append(pair)
        else:
            runs.append([pair])
    return runs


def _speaking_time(features: AudioFeatures, start: float, end: float) -> float:
    return max(0.0, (end - start) - silence_within(features, start, end))


def _pace(participant: AudioFeatures, reference: AudioFeatures, words: list[WordPair]) -> tuple[float, float]:
    """Speaking time, pauses removed, that each recording takes over the same run of words."""
    return (
        _speaking_time(participant, words[0].par_start, words[-1].par_end),
        _speaking_time(reference, words[0].ref_start, words[-1].ref_end),
    )


# --- Rules -----------------------------------------------------------------------------------


def _withheld(rule_id: str, category: str, reason: str, status: str = "withheld") -> RuleReport:
    return RuleReport(rule_id=rule_id, category=category, status=status, reason=reason)


def pace_against_reference(
    participant: AudioFeatures, reference: AudioFeatures, pairs: list[WordPair], quality: SignalQuality, settings: DetectionSettings
) -> tuple[list[RuleReport], list[Finding]]:
    rule_id = "pace_vs_reference"
    thresholds = {"pace_ratio_threshold": settings.pace_ratio_threshold}
    runs = [run for run in _runs(pairs) if len(run) >= 2]
    par_time = sum(_pace(participant, reference, run)[0] for run in runs)
    ref_time = sum(_pace(participant, reference, run)[1] for run in runs)
    if ref_time <= 0 or par_time <= 0:
        reason = "No run of two or more consecutive aligned words with measurable speaking time."
        return [_withheld(rule_id, c, reason) for c in ("rushed_delivery", "slow_delivery")], []

    ratio = par_time / ref_time
    measured = {"participant_speaking_sec": _round(par_time), "reference_speaking_sec": _round(ref_time), "ratio": _round(ratio)}
    rushed, slow = ratio <= 1 / settings.pace_ratio_threshold, ratio >= settings.pace_ratio_threshold
    reports = [
        RuleReport(rule_id=rule_id, category=category, status="triggered" if hit else "not_triggered", findings=int(hit), measured=measured, thresholds=thresholds)
        for category, hit in (("rushed_delivery", rushed), ("slow_delivery", slow))
    ]
    if not (rushed or slow):
        return reports, []

    category = "rushed_delivery" if rushed else "slow_delivery"
    magnitude = max(ratio, 1 / ratio)
    severity = "major" if magnitude >= settings.pace_major_ratio else "moderate" if magnitude >= settings.pace_moderate_ratio else "minor"
    low = _quality("high", category, quality) == "low"
    start, end = pairs[0].par_start, pairs[-1].par_end
    percent = abs(1 - ratio) * 100
    finding = Finding(
        id=_finding_id(rule_id, start, end),
        category=category,
        title="Faster than the reference" if rushed else "Slower than the reference",
        start=_round(start),
        end=_round(end),
        reference_interval=Span(start=_round(pairs[0].ref_start), end=_round(pairs[-1].ref_end)),
        evidence=[
            _evidence("speaking_time_for_the_same_words", "s", par_time, ref_time),
            _evidence("words_compared", "count", float(len(pairs)), float(len(pairs))),
        ],
        comparison_method=(
            "Speaking time, with measured pauses removed, that each recording takes over the same runs of consecutive "
            "aligned words. " + ALIGNMENT_STRATEGY
        ),
        rule=RuleUsed(
            rule_id=rule_id,
            description="Flag when the participant's speaking time for the same words differs from the reference's by more than the threshold ratio.",
            thresholds=thresholds | {"moderate_from": settings.pace_moderate_ratio, "major_from": settings.pace_major_ratio},
        ),
        evidence_quality=_quality("high", category, quality),
        severity=None if low else severity,
        severity_basis=(
            None
            if low
            else f"Size of the measured pace difference ({magnitude:.2f}x): minor below {settings.pace_moderate_ratio}x, "
            f"moderate below {settings.pace_major_ratio}x, major above. A magnitude band, not a judgement of how it sounds."
        ),
        explanation=(
            f"You took {par_time:.1f} s of speaking time for the {len(pairs)} words that took the reference {ref_time:.1f} s, "
            f"about {percent:.0f}% {'less' if rushed else 'more'}. Pauses are not counted in either."
        ),
        limitations=[
            "Word boundaries come from a speech recogniser and are accurate to roughly a tenth of a second.",
            "A different pace from the reference is not necessarily worse; it is only different.",
            *_quality_notes(category, quality),
        ],
    )
    return reports, [finding]


def pace_without_reference(participant: DeliveryAnalysis, quality: SignalQuality, settings: DetectionSettings) -> tuple[list[RuleReport], list[Finding]]:
    rule_id = "pace_words_per_minute"
    thresholds = {"fast_above": settings.words_per_minute_fast, "slow_below": settings.words_per_minute_slow}

    def withheld(reason: str) -> tuple[list[RuleReport], list[Finding]]:
        return [_withheld(rule_id, c, reason) for c in ("rushed_delivery", "slow_delivery")], []

    transcription = participant.transcription
    if transcription is None or not transcription.words:
        return withheld("Needs recognised words with timestamps, which are not available.")
    if transcription.language not in (None, "en"):
        return withheld(f"The words-per-minute thresholds are for English; this recording was recognised as '{transcription.language}'.")
    words = transcription.words
    span = words[-1].end - words[0].start
    if len(words) < settings.min_words_for_rate or span < settings.min_seconds_for_rate:
        return withheld(
            f"Needs at least {settings.min_words_for_rate} recognised words over {settings.min_seconds_for_rate:g} s; "
            f"found {len(words)} over {span:.1f} s."
        )
    rate = len(words) / span * 60
    fast, slow = rate > settings.words_per_minute_fast, rate < settings.words_per_minute_slow
    measured = {"words_per_minute": _round(rate, 1), "words": len(words), "span_sec": _round(span)}
    reports = [
        RuleReport(rule_id=rule_id, category=category, status="triggered" if hit else "not_triggered", findings=int(hit), measured=measured, thresholds=thresholds)
        for category, hit in (("rushed_delivery", fast), ("slow_delivery", slow))
    ]
    if not (fast or slow):
        return reports, []
    category = "rushed_delivery" if fast else "slow_delivery"
    limit = settings.words_per_minute_fast if fast else settings.words_per_minute_slow
    finding = Finding(
        id=_finding_id(rule_id, words[0].start, words[-1].end),
        category=category,
        title="Fast overall pace" if fast else "Slow overall pace",
        start=_round(words[0].start),
        end=_round(words[-1].end),
        evidence=[_evidence("words_per_minute", "words/min", rate), _evidence("recognised_words", "count", float(len(words)))],
        comparison_method="Recognised words divided by the time from the first word to the last, including pauses. No reference recording was used.",
        rule=RuleUsed(
            rule_id=rule_id,
            description="Flag when recognised words per minute fall outside a fixed range for English speech.",
            thresholds=thresholds,
        ),
        evidence_quality=_quality("moderate", category, quality),
        explanation=f"About {rate:.0f} words per minute over {span:.1f} s, {'above' if fast else 'below'} the {limit:g} words-per-minute limit.",
        limitations=[
            "The limits are general guidance for English, not validated for this speaker, text or purpose. Dense or technical text is naturally slower.",
            "Counts recognised words, so recognition errors change the figure.",
            "No severity is given because there is no reference to measure the size of the difference against.",
            *_quality_notes(category, quality),
        ],
    )
    return reports, [finding]


def _locate_pause(pairs: list[WordPair], start: float, end: float) -> tuple[WordPair, WordPair] | None:
    """The aligned words just before and just after a participant pause, if they are close together in the transcript."""
    before = [p for p in pairs if p.par_end <= start + BOUNDARY_TOLERANCE_SEC]
    after = [p for p in pairs if p.par_start >= end - BOUNDARY_TOLERANCE_SEC]
    if not before or not after:
        return None
    left, right = before[-1], after[0]
    if not (0 < right.index - left.index <= MAX_WORDS_ACROSS_PAUSE):
        return None
    return left, right


def pauses_against_reference(
    participant: AudioFeatures, reference: AudioFeatures, pairs: list[WordPair], quality: SignalQuality, settings: DetectionSettings
) -> tuple[RuleReport, list[Finding]]:
    rule_id, category = "pause_vs_reference", "excessive_pause"
    thresholds = {"pause_excess_sec": settings.pause_excess_sec}
    if participant.pauses.status != "measured" or reference.pauses.status != "measured":
        return _withheld(rule_id, category, "Pauses could not be measured in both recordings."), []

    low = _quality("high", category, quality) == "low" or reference.pauses.reliability == "low"
    findings: list[Finding] = []
    located = 0
    internal = [p for p in participant.pauses.intervals if p.position == "internal"]
    for pause in internal:
        words = _locate_pause(pairs, pause.start, pause.end)
        if words is None:
            continue
        located += 1
        left, right = words
        duration = pause.end - pause.start
        ref_silence = silence_within(reference, left.ref_start, right.ref_end)
        excess = duration - ref_silence
        if excess < settings.pause_excess_sec:
            continue
        severity = "major" if excess >= settings.pause_major_excess_sec else "moderate" if excess >= settings.pause_moderate_excess_sec else "minor"
        findings.append(
            Finding(
                id=_finding_id(rule_id, pause.start, pause.end),
                category=category,
                title="Possible longer pause than the reference" if low else "Longer pause than the reference",
                start=pause.start,
                end=pause.end,
                reference_interval=Span(start=_round(left.ref_start), end=_round(right.ref_end)),
                evidence=[_evidence("silence_between_the_same_words", "s", duration, ref_silence)],
                comparison_method=(
                    f"Measured silence in the participant recording between '{left.word}' and '{right.word}', against the measured "
                    "silence across the same words in the reference. " + ALIGNMENT_STRATEGY
                ),
                rule=RuleUsed(
                    rule_id=rule_id,
                    description="Flag a measured pause that is longer than the reference's silence at the same words by more than the threshold.",
                    thresholds=thresholds | {"moderate_from": settings.pause_moderate_excess_sec, "major_from": settings.pause_major_excess_sec},
                ),
                evidence_quality="low" if low else "high",
                severity=None if low else severity,
                severity_basis=(
                    None
                    if low
                    else f"Extra silence beyond the reference ({excess:.2f} s): minor below {settings.pause_moderate_excess_sec:g} s, "
                    f"moderate below {settings.pause_major_excess_sec:g} s, major above. A magnitude band, not a judgement of how it sounds."
                ),
                explanation=(
                    f"There are {duration:.2f} s of silence after '{left.word}', where the reference has {ref_silence:.2f} s "
                    f"across the same words: {excess:.2f} s more."
                ),
                limitations=[
                    "A longer pause can be deliberate. This reports the difference, not whether it helps or hurts.",
                    "The silence itself is measured from the audio; only its position in the text relies on recognised word times.",
                    *(["Background noise makes it uncertain whether this is true silence."] if low else []),
                    *_quality_notes(category, quality),
                ],
            )
        )
    report = RuleReport(
        rule_id=rule_id,
        category=category,
        status="triggered" if findings else "not_triggered",
        findings=len(findings),
        measured={"participant_internal_pauses": len(internal), "pauses_located_between_aligned_words": located},
        thresholds=thresholds,
        reason="" if located == len(internal) else f"{len(internal) - located} pause(s) could not be placed between aligned words and were not compared.",
    )
    return report, findings


def pause_placement(
    participant: AudioFeatures, reference: AudioFeatures, pairs: list[WordPair], quality: SignalQuality, settings: DetectionSettings
) -> tuple[RuleReport, list[Finding]]:
    """Places where the reference pauses and the participant does not, or barely does.

    Together with `pauses_against_reference`, which reports the opposite case, this covers how the
    participant's pause placement departs from the reference's.
    """
    rule_id, category = "pause_placement_vs_reference", "irregular_pauses"
    thresholds = {"pause_excess_sec": settings.pause_excess_sec}
    if participant.pauses.status != "measured" or reference.pauses.status != "measured":
        return _withheld(rule_id, category, "Pauses could not be measured in both recordings."), []

    low = _quality("high", category, quality) == "low" or reference.pauses.reliability == "low"
    findings: list[Finding] = []
    located = 0
    internal = [p for p in reference.pauses.intervals if p.position == "internal"]
    # Group the reference's pauses by the pair of aligned words they fall between. When a word in between was
    # not recognised, two pauses share one pair; they are one place and are compared once, together.
    places: dict[tuple[int, int], tuple[WordPair, WordPair, list]] = {}
    for pause in internal:
        before = [p for p in pairs if p.ref_end <= pause.start + BOUNDARY_TOLERANCE_SEC]
        after = [p for p in pairs if p.ref_start >= pause.end - BOUNDARY_TOLERANCE_SEC]
        if not before or not after or not (0 < after[0].index - before[-1].index <= MAX_WORDS_ACROSS_PAUSE):
            continue
        located += 1
        places.setdefault((before[-1].index, after[0].index), (before[-1], after[0], []))[2].append(pause)
    for left, right, grouped in places.values():
        pause = Span(start=grouped[0].start, end=grouped[-1].end)
        duration = sum(p.end - p.start for p in grouped)
        par_silence = silence_within(participant, left.par_start, right.par_end)
        missing = duration - par_silence
        if missing < settings.pause_excess_sec:
            continue
        findings.append(
            Finding(
                id=_finding_id(rule_id, left.par_start, right.par_end),
                category=category,
                title="Possibly shorter or missing pause compared with the reference" if low else "Shorter or missing pause compared with the reference",
                start=_round(left.par_start),
                end=_round(right.par_end),
                reference_interval=Span(start=pause.start, end=pause.end),
                evidence=[_evidence("silence_between_the_same_words", "s", par_silence, duration)],
                comparison_method=(
                    f"Measured silence across '{left.word}' to '{right.word}' in the participant recording, against the "
                    "reference's measured pause between the same words. " + ALIGNMENT_STRATEGY
                ),
                rule=RuleUsed(
                    rule_id=rule_id,
                    description="Flag a place where the reference pauses and the participant's silence at the same words is shorter by more than the threshold.",
                    thresholds=thresholds,
                ),
                evidence_quality="low" if low else "high",
                explanation=(
                    f"The reference pauses for {duration:.2f} s between '{left.word}' and '{right.word}'; "
                    f"you have {par_silence:.2f} s of silence there, {missing:.2f} s less."
                ),
                limitations=[
                    "Pausing differently from the reference is not necessarily worse; this only reports where the pattern differs.",
                    "The interval covers the two words on either side of where the reference pauses, located by recognised word times.",
                    "No severity is given for pause placement.",
                    *(["Background noise makes the silence measurements uncertain."] if low else []),
                    *_quality_notes(category, quality),
                ],
            )
        )
    report = RuleReport(
        rule_id=rule_id,
        category=category,
        status="triggered" if findings else "not_triggered",
        findings=len(findings),
        measured={"reference_internal_pauses": len(internal), "pauses_located_between_aligned_words": located},
        thresholds=thresholds,
        reason="" if located == len(internal) else f"{len(internal) - located} reference pause(s) could not be placed between aligned words and were not compared.",
    )
    return report, findings


def pauses_without_reference(participant: AudioFeatures, quality: SignalQuality, settings: DetectionSettings) -> tuple[RuleReport, list[Finding]]:
    rule_id, category = "long_pause", "excessive_pause"
    thresholds = {"long_pause_sec": settings.long_pause_sec}
    if participant.pauses.status != "measured":
        return _withheld(rule_id, category, "Pauses could not be measured in this recording."), []
    low = _quality("moderate", category, quality) == "low"
    internal = [p for p in participant.pauses.intervals if p.position == "internal"]
    findings = [
        Finding(
            id=_finding_id(rule_id, pause.start, pause.end),
            category=category,
            title="Possible long pause" if low else "Long pause",
            start=pause.start,
            end=pause.end,
            evidence=[_evidence("silence_duration", "s", pause.end - pause.start)],
            comparison_method="Measured silence within the recording against a fixed duration. No reference recording was used.",
            rule=RuleUsed(rule_id=rule_id, description="Flag a measured silence inside the speech that lasts longer than the threshold.", thresholds=thresholds),
            evidence_quality="low" if low else "moderate",
            explanation=f"{pause.end - pause.start:.2f} s of silence, longer than the {settings.long_pause_sec:g} s limit.",
            limitations=[
                "A long pause can be deliberate. Without a reference there is nothing to say how long this pause was meant to be.",
                "No severity is given because there is no reference to measure the size of the difference against.",
                *(["Background noise makes it uncertain whether this is true silence."] if low else []),
                *_quality_notes(category, quality),
            ],
        )
        for pause in internal
        if pause.end - pause.start >= settings.long_pause_sec
    ]
    return (
        RuleReport(
            rule_id=rule_id,
            category=category,
            status="triggered" if findings else "not_triggered",
            findings=len(findings),
            measured={"participant_internal_pauses": len(internal), "longest_pause_sec": _round(max((p.end - p.start for p in internal), default=0.0))},
            thresholds=thresholds,
        ),
        findings,
    )


def uneven_pacing(
    participant: AudioFeatures, reference: AudioFeatures, pairs: list[WordPair], quality: SignalQuality, settings: DetectionSettings
) -> tuple[RuleReport, list[Finding]]:
    rule_id, category = "pacing_vs_reference", "uneven_pacing"
    thresholds = {
        "chunk_words": settings.pacing_chunk_words,
        "spread_ratio": settings.pacing_spread_ratio,
        "chunk_deviation": settings.pacing_chunk_deviation,
    }
    chunks: list[list[WordPair]] = []
    for run in _runs(pairs):
        count = len(run) // settings.pacing_chunk_words
        for part in np.array_split(np.arange(len(run)), count) if count else []:
            chunks.append([run[i] for i in part])
    paces = [(chunk, *_pace(participant, reference, chunk)) for chunk in chunks]
    paces = [(chunk, par, ref) for chunk, par, ref in paces if par > 0 and ref > 0]
    if len(paces) < settings.pacing_min_chunks:
        return (
            _withheld(
                rule_id,
                category,
                f"Needs at least {settings.pacing_min_chunks} runs of {settings.pacing_chunk_words} consecutive aligned words; found {len(paces)}.",
            ),
            [],
        )
    overall = sum(par for _, par, _ in paces) / sum(ref for _, _, ref in paces)
    # Each chunk's pace relative to this speaker's overall pace, so being uniformly fast or slow is not 'uneven'.
    relative = [(chunk, par, ref, (par / ref) / overall) for chunk, par, ref in paces]
    spread = max(r for *_, r in relative) / min(r for *_, r in relative)
    measured = {"chunks": len(relative), "spread_ratio": _round(spread), "overall_pace_ratio": _round(overall)}
    if spread < settings.pacing_spread_ratio:
        return RuleReport(rule_id=rule_id, category=category, status="not_triggered", measured=measured, thresholds=thresholds), []

    findings = []
    for chunk, par, ref, rel in relative:
        slower, faster = rel >= settings.pacing_chunk_deviation, rel <= 1 / settings.pacing_chunk_deviation
        if not (slower or faster):
            continue
        start, end = chunk[0].par_start, chunk[-1].par_end
        findings.append(
            Finding(
                id=_finding_id(rule_id, start, end),
                category=category,
                title="Slower stretch than your overall pace" if slower else "Faster stretch than your overall pace",
                start=_round(start),
                end=_round(end),
                reference_interval=Span(start=_round(chunk[0].ref_start), end=_round(chunk[-1].ref_end)),
                evidence=[
                    _evidence("speaking_time_for_the_same_words", "s", par, ref),
                    _evidence("pace_relative_to_own_overall_pace", "ratio", rel),
                    _evidence("pace_spread_across_stretches", "ratio", spread),
                ],
                comparison_method=(
                    f"Pace against the reference measured separately for each run of about {settings.pacing_chunk_words} consecutive "
                    "aligned words, then divided by the participant's overall pace against the reference. " + ALIGNMENT_STRATEGY
                ),
                rule=RuleUsed(
                    rule_id=rule_id,
                    description="When pace relative to the reference varies across stretches by more than the spread ratio, flag the stretches that deviate from the overall pace by more than the chunk deviation.",
                    thresholds=thresholds,
                ),
                evidence_quality=_quality("moderate", category, quality),
                explanation=(
                    f"From '{chunk[0].word}' to '{chunk[-1].word}' you were about {abs(rel - 1) * 100:.0f}% "
                    f"{'slower' if slower else 'faster'} than your own overall pace, measured against the reference's timing of the same words."
                ),
                limitations=[
                    "Each stretch is only a few seconds long, so recognised word boundaries (accurate to about a tenth of a second) add noticeable error.",
                    "No severity is given: the size of this measurement's error has not been established.",
                    *_quality_notes(category, quality),
                ],
            )
        )
    return (
        RuleReport(
            rule_id=rule_id,
            category=category,
            status="triggered" if findings else "not_triggered",
            findings=len(findings),
            measured=measured,
            thresholds=thresholds,
        ),
        findings,
    )


def _is_filler(key: str, fillers: set[str]) -> bool:
    """Whether a normalised word is a hesitation sound, including drawn-out spellings such as 'ummm' or 'uhhh'."""
    if key in fillers:
        return True
    squeezed = re.sub(r"(.)\1+", r"\1", key)  # 'ummm' -> 'um', 'errrm' -> 'erm'
    return len(squeezed) >= 2 and squeezed in {re.sub(r"(.)\1+", r"\1", f) for f in fillers}


def filler_words(participant: DeliveryAnalysis, quality: SignalQuality, settings: DetectionSettings) -> tuple[RuleReport, list[Finding]]:
    rule_id, category = "filler_lexicon", "filler_word"
    thresholds = {"fillers": ", ".join(settings.filler_words)}
    transcription = participant.transcription
    if transcription is None or transcription.word_timestamps != "available":
        return _withheld(rule_id, category, "Needs recognised words with timestamps, which are not available."), []
    script = {normalize(w.word) for w in participant.alignment.words} if participant.alignment and participant.alignment.transcript_source == "supplied" else None
    fillers = set(settings.filler_words)
    findings = []
    for word in transcription.words:
        key = normalize(word.word)
        if not _is_filler(key, fillers) or word.end <= word.start:
            continue
        unscripted = script is not None and key not in script
        unsure = word.probability is not None and word.probability < settings.filler_min_probability
        findings.append(
            Finding(
                id=_finding_id(rule_id, word.start, word.end),
                category=category,
                title=f"Possible filler sound: “{key}”" if unsure else f"Filler sound: “{key}”",
                start=word.start,
                end=word.end,
                evidence=[_evidence("recogniser_word_probability", "probability", word.probability)],
                comparison_method="The recognised word is in the list of hesitation sounds." + (" It is not in the transcript you supplied." if unscripted else ""),
                rule=RuleUsed(rule_id=rule_id, description="Flag recognised words that are non-lexical hesitation sounds.", thresholds=thresholds),
                evidence_quality="low" if unsure else _quality("moderate", category, quality),
                explanation=f"The recogniser heard “{word.word}” here."
                + (f" It was not confident (probability {word.probability:.2f})." if unsure else ""),
                limitations=[
                    "This relies on the speech recogniser, which can mishear a short word as a filler or the reverse.",
                    "No severity is given: one filler is not a measure of how much they affect a delivery.",
                    *_quality_notes(category, quality),
                ],
            )
        )
    return (
        RuleReport(
            rule_id=rule_id,
            category=category,
            status="triggered" if findings else "not_triggered",
            findings=len(findings),
            measured={
                "recognised_words": len(transcription.words),
                "fillers": len(findings),
                "fillers_per_minute": _round(len(findings) / transcription.duration_sec * 60, 1) if transcription.duration_sec > 0 else None,
            },
            thresholds=thresholds,
            reason=(
                "Counts only the fillers the recogniser transcribed. Recognisers often leave fillers out, so the true number may be higher."
                if findings
                else "None were recognised. Speech recognisers often leave fillers out, so this is not evidence that there were none."
            ),
        ),
        findings,
    )


def steady_voiced_stretches(
    f0: list[float | None], centroid: list[float | None], hop_sec: float, settings: DetectionSettings
) -> list[tuple[int, int]]:
    """Frame ranges [i, j) where every frame is voiced, with pitch and spectral centroid held close to the stretch's median."""
    stretches: list[tuple[int, int]] = []
    min_frames = max(2, int(np.ceil(settings.filled_pause_min_sec / hop_sec - 1e-9)))
    i = 0
    while i < len(f0):
        if f0[i] is None or centroid[i] is None:
            i += 1
            continue
        j = i + 1
        while j < len(f0) and f0[j] is not None and centroid[j] is not None:
            semitones = 12 * np.log2(np.array(f0[i : j + 1], dtype=float))
            spectrum = np.array(centroid[i : j + 1], dtype=float)
            if (
                np.abs(semitones - np.median(semitones)).max() > settings.filled_pause_pitch_semitones
                or np.abs(spectrum / np.median(spectrum) - 1).max() > settings.filled_pause_centroid_spread
            ):
                break
            j += 1
        if j - i >= min_frames:
            stretches.append((i, j))
            i = j
        else:
            i += 1
    return stretches


def _time_outside(start: float, end: float, spans: list[tuple[float, float]]) -> float:
    covered = sum(max(0.0, min(end, e) - max(start, s)) for s, e in spans)
    return max(0.0, (end - start) - covered)


def filled_pauses(
    participant: DeliveryAnalysis, lexical: list[Finding], quality: SignalQuality, settings: DetectionSettings
) -> tuple[RuleReport, list[Finding]]:
    """Possible filled pauses ('uh', 'um') the recogniser did not transcribe, found from the sound itself."""
    rule_id, category = "filled_pause_acoustic", "filler_word"
    thresholds = {
        "min_duration_sec": settings.filled_pause_min_sec,
        "max_pitch_deviation_semitones": settings.filled_pause_pitch_semitones,
        "max_spectral_centroid_deviation": settings.filled_pause_centroid_spread,
        "min_time_outside_recognised_words_sec": settings.filled_pause_min_outside_words_sec,
    }
    transcription = participant.transcription
    pitch, centroid = participant.features.pitch.series, participant.features.spectral.centroid
    if transcription is None or transcription.word_timestamps != "available":
        return _withheld(rule_id, category, "Needs recognised words with timestamps, to tell sounds inside words from sounds between them."), []
    if pitch is None or centroid is None:
        return _withheld(rule_id, category, "Needs the pitch track and spectral centroid, which were not measured for this recording."), []

    def centroid_at(k: int) -> float | None:
        index = int(round((pitch.start_sec + k * pitch.hop_sec - centroid.start_sec) / centroid.hop_sec))
        return centroid.values[index] if 0 <= index < len(centroid.values) else None

    aligned = [centroid_at(k) for k in range(len(pitch.values))]
    words = [(w.start, w.end) for w in transcription.words if w.end > w.start]
    already = [(f.start, f.end) for f in lexical]
    findings = []
    for i, j in steady_voiced_stretches(pitch.values, aligned, pitch.hop_sec, settings):
        start, end = round(pitch.start_sec + i * pitch.hop_sec, 3), round(pitch.start_sec + j * pitch.hop_sec, 3)
        outside = _time_outside(start, end, words)
        if outside < settings.filled_pause_min_outside_words_sec or any(end > s and start < e for s, e in already):
            continue
        semitones = 12 * np.log2(np.array(pitch.values[i:j], dtype=float))
        spectrum = np.array(aligned[i:j], dtype=float)
        findings.append(
            Finding(
                id=_finding_id(rule_id, start, end),
                category=category,
                title="Possible filled pause",
                start=start,
                end=end,
                evidence=[
                    _evidence("steady_voiced_duration", "s", end - start),
                    _evidence("time_outside_recognised_words", "s", outside),
                    _evidence("pitch_deviation", "semitones", float(np.abs(semitones - np.median(semitones)).max())),
                    _evidence("spectral_centroid_deviation", "fraction", float(np.abs(spectrum / np.median(spectrum) - 1).max())),
                ],
                comparison_method="A voiced sound with level pitch and an unchanging spectrum, mostly between recognised words.",
                rule=RuleUsed(
                    rule_id=rule_id,
                    description="Flag steady voiced sounds the recogniser did not transcribe as a word, as possible filled pauses.",
                    thresholds=thresholds,
                ),
                evidence_quality="low",
                explanation=(
                    f"A steady voiced sound lasted {end - start:.2f} s here, {outside:.2f} s of it outside the recognised words. "
                    "Filled pauses such as “uh” or “um” sound like this, but so can a drawn-out word or a sung note."
                ),
                limitations=[
                    "Found from the sound alone, so it cannot tell a filler from a held vowel; listen to the marked moment.",
                    "Checked only on synthetic fillers inserted into recordings, not on natural hesitations.",
                    "Short or breathy fillers, and fillers the pitch tracker cannot follow, are not found.",
                    *_quality_notes(category, quality),
                ],
            )
        )
    return (
        RuleReport(
            rule_id=rule_id,
            category=category,
            status="triggered" if findings else "not_triggered",
            findings=len(findings),
            measured={"possible_filled_pauses": len(findings)},
            thresholds=thresholds,
            reason=(
                "Possible filled pauses found from the sound, outside the recognised words. Each needs listening to."
                if findings
                else "No steady voiced sounds were found between the recognised words. Short or breathy fillers can still be missed."
            ),
        ),
        findings,
    )


def pitch_monotony(
    participant: DeliveryAnalysis,
    reference: DeliveryAnalysis | None,
    alignment: AlignmentStatus,
    quality: SignalQuality,
    settings: DetectionSettings,
) -> tuple[RuleReport, list[Finding]]:
    category = "pitch_monotony"
    compared = alignment.status == "aligned" and reference is not None
    rule_id = "pitch_range_vs_reference" if compared else "pitch_range"
    features = participant.features
    if any(issue.code == "pitch_unreliable" for issue in quality.issues):
        reason = next(issue.message for issue in quality.issues if issue.code == "pitch_unreliable")
        return _withheld(rule_id, category, f"Pitch tracking is not reliable for this recording, so pitch variation is not judged. {reason}"), []

    if compared:
        window = alignment.participant_window
    elif participant.transcription and participant.transcription.words:
        window = Span(start=participant.transcription.words[0].start, end=participant.transcription.words[-1].end)
    else:
        window = Span(start=0.0, end=features.audio.duration_sec)
    stats = pitch_window_stats(features, window.start, window.end)

    def unusable(found: dict[str, float] | None, who: str) -> str | None:
        if found is None or found["voiced_frames"] < settings.min_voiced_frames:
            frames = 0 if found is None else int(found["voiced_frames"])
            return f"Only {frames} voiced frames in the {who} window; at least {settings.min_voiced_frames} are needed."
        if found["octave_jump_fraction"] > MAX_WINDOW_JUMP_FRACTION:
            return f"The {who} pitch contour has octave jumps in this window ({found['octave_jump_fraction']:.1%} of steps), which make its range unreliable."
        return None

    problem = unusable(stats, "participant")
    if problem:
        return _withheld(rule_id, category, problem), []

    ref_stats = None
    if compared:
        ref_features = reference.features
        ref_reliable = ref_features.pitch.status == "measured" and ref_features.pitch.reliability == "ok"
        ref_stats = pitch_window_stats(ref_features, alignment.reference_window.start, alignment.reference_window.end)
        problem = None if ref_reliable else "Pitch tracking is not reliable for the reference recording."
        problem = problem or unusable(ref_stats, "reference")
        if problem:
            return _withheld(rule_id, category, problem + " Pitch variation is not compared."), []

    par_range = stats["range_semitones"]
    measured = {"participant_range_semitones": _round(par_range, 2), "participant_voiced_frames": int(stats["voiced_frames"])}
    if compared:
        ratio = par_range / ref_stats["range_semitones"] if ref_stats["range_semitones"] > 0 else None
        thresholds = {"monotony_ratio": settings.monotony_ratio}
        measured |= {"reference_range_semitones": _round(ref_stats["range_semitones"], 2), "ratio": _round(ratio)}
        hit = ratio is not None and ratio <= settings.monotony_ratio
    else:
        thresholds = {"monotony_range_semitones": settings.monotony_range_semitones}
        hit = par_range < settings.monotony_range_semitones
    if not hit:
        return RuleReport(rule_id=rule_id, category=category, status="not_triggered", measured=measured, thresholds=thresholds), []

    evidence = [
        _evidence("pitch_range_5th_to_95th_percentile", "semitones", par_range, ref_stats["range_semitones"] if compared else None),
        _evidence("pitch_standard_deviation", "semitones", stats["sd_semitones"], ref_stats["sd_semitones"] if compared else None),
        _evidence("voiced_frames_used", "count", stats["voiced_frames"], ref_stats["voiced_frames"] if compared else None),
    ]
    finding = Finding(
        id=_finding_id(rule_id, window.start, window.end),
        category=category,
        title="Possibly narrower pitch variation than the reference" if compared else "Possibly narrow pitch variation",
        start=_round(window.start),
        end=_round(window.end),
        reference_interval=alignment.reference_window if compared else None,
        evidence=evidence,
        comparison_method=(
            "5th-to-95th percentile range of pitch over voiced frames only, in semitones around each speaker's own median"
            + (", over the aligned words of both recordings. " + ALIGNMENT_STRATEGY if compared else ", against a fixed range. No reference recording was used.")
        ),
        rule=RuleUsed(
            rule_id=rule_id,
            description=(
                "Flag when the participant's pitch range is at most the threshold fraction of the reference's."
                if compared
                else "Flag when the pitch range is below the threshold."
            ),
            thresholds=thresholds,
        ),
        evidence_quality=_quality("moderate", category, quality),
        explanation=(
            f"Your pitch moved over {par_range:.1f} semitones, against {ref_stats['range_semitones']:.1f} for the reference over the same words."
            if compared
            else f"Your pitch moved over {par_range:.1f} semitones, below the {settings.monotony_range_semitones:g} semitone limit."
        ),
        limitations=[
            "Worded as 'possibly' because pitch tracking still makes errors and a narrow range is a normal speaking style for many people.",
            "Measured relative to your own voice: a naturally high or low voice does not affect this.",
            "No severity is given, and this says nothing about cause.",
            *_quality_notes(category, quality),
        ],
    )
    return RuleReport(rule_id=rule_id, category=category, status="triggered", findings=1, measured=measured, thresholds=thresholds), [finding]


ARTICULATION_REASON = (
    "No finding is made. Recognition confidence and spectral measures both depend on accent, voice and microphone, "
    "so judging by them would penalise who is speaking rather than how clearly. The report shows them as a clarity "
    "estimate, for information only."
)


def run_detection(
    participant: DeliveryAnalysis,
    reference: DeliveryAnalysis | None = None,
    *,
    transcript_source: str = "none",
    comparison_withheld_reason: str | None = None,
    settings: DetectionSettings | None = None,
) -> DetectionResult:
    settings = settings or DetectionSettings()
    quality = assess_signal_quality(participant.features, settings)
    if reference is not None and comparison_withheld_reason is None:
        reference_quality = assess_signal_quality(reference.features, settings)
        if not reference_quality.usable:
            blocking = next(issue for issue in reference_quality.issues if issue.level == "blocking")
            comparison_withheld_reason = f"The reference recording cannot be used: {blocking.message}"
    alignment, pairs = build_alignment(participant, reference, transcript_source, settings, comparison_withheld_reason)

    reports: list[RuleReport] = []
    findings: list[Finding] = []

    def add(result: tuple[RuleReport | list[RuleReport], list[Finding]]) -> None:
        report, found = result
        reports.extend(report if isinstance(report, list) else [report])
        findings.extend(found)

    if not quality.usable:
        reason = "The recording is not usable: " + next(issue.message for issue in quality.issues if issue.level == "blocking")
        for rule_id, category in (
            ("pace", "rushed_delivery"), ("pace", "slow_delivery"), ("pause", "excessive_pause"),
            ("pause_placement_vs_reference", "irregular_pauses"),
            ("filler_lexicon", "filler_word"), ("filled_pause_acoustic", "filler_word"),
            ("pacing_vs_reference", "uneven_pacing"), ("pitch_range", "pitch_monotony"),
        ):  # fmt: skip
            reports.append(_withheld(rule_id, category, reason))
    else:
        compared = alignment.status == "aligned" and reference is not None
        if compared:
            add(pace_against_reference(participant.features, reference.features, pairs, quality, settings))
            add(pauses_against_reference(participant.features, reference.features, pairs, quality, settings))
            add(pause_placement(participant.features, reference.features, pairs, quality, settings))
            add(uneven_pacing(participant.features, reference.features, pairs, quality, settings))
            _downgrade_for_thin_comparison(findings, alignment, settings)
        else:
            add(pace_without_reference(participant, quality, settings))
            add(pauses_without_reference(participant.features, quality, settings))
            placement = (
                "Needs a reference recording: where pauses belong depends on the text, so there is no general rule for "
                "how they should be spaced."
            )
            reports.append(
                _withheld("pause_placement_vs_reference", "irregular_pauses", placement if reference is None else f"The reference could not be used. {alignment.reason}")
            )
            why = "Needs a reference recording: without one, pace changes cannot be told apart from longer and shorter words."
            reports.append(_withheld("pacing_vs_reference", "uneven_pacing", why if reference is None else f"The reference could not be used. {alignment.reason}"))
        lexical = filler_words(participant, quality, settings)
        add(lexical)
        add(filled_pauses(participant, lexical[1], quality, settings))
        add(pitch_monotony(participant, reference, alignment, quality, settings))
    reports.append(_withheld("articulation", "unclear_articulation", ARTICULATION_REASON, status="not_supported"))

    limitations = [
        "Findings are measured differences that crossed a documented threshold. They are not proof of a problem, a diagnosis, or a statement about cause.",
        "Thresholds are project defaults checked on a small demonstration dataset of transformed recordings; they have not been validated with listeners.",
        "Severity, where given, is a band of the measured size of a difference, not a rating of how the delivery sounds.",
    ]
    if reference is not None and alignment.status != "aligned":
        limitations.insert(0, f"The reference recording was not used: {alignment.reason} Findings below do not rely on it.")
    return DetectionResult(
        signal_quality=quality,
        alignment_status=alignment,
        findings=sorted(findings, key=lambda f: (f.start, f.end, f.id)),
        rules=reports,
        limitations=limitations,
    )
