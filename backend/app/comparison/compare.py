"""Reference-versus-participant comparison built only from measurements and aligned word times."""

from ..audio.schemas import AudioFeatures
from ..speech.alignment import normalize
from .schemas import (
    ComparisonResult,
    ComparisonSettings,
    DeliveryAnalysis,
    MetricComparison,
    Span,
    TimingDifference,
    WordComparison,
    WordLevelComparison,
)

NOT_IMPLEMENTED = [
    "Deciding whether a difference is a flaw",
    "Severity levels",
    "Frame-by-frame pitch or energy contour comparison",
    "Coaching generated from the comparison",
]

NOT_COMPARED = {
    "energy_db": "Levels depend on microphone distance and recording gain, so two recordings cannot be compared without calibration.",
    "spectral_and_mfcc": "These describe the recording chain and the speaker's voice as much as the delivery.",
}


def _metric(
    name: str,
    unit: str,
    basis: str,
    reference: float | None,
    participant: float | None,
    *,
    comparable: bool = True,
    note: str = "",
) -> MetricComparison:
    both = reference is not None and participant is not None
    if not both:
        comparable = False
        note = (note + " " if note else "") + "Not available for both recordings."
    return MetricComparison(
        name=name,
        unit=unit,
        basis=basis,
        reference=reference,
        participant=participant,
        difference=round(participant - reference, 4) if both else None,
        ratio=round(participant / reference, 4) if both and reference else None,
        comparable=comparable,
        note=note.strip(),
    )


def _silence_total(features: AudioFeatures) -> float | None:
    if features.pauses.status != "measured":
        return None
    return round(sum(i.end - i.start for i in features.pauses.intervals if i.position == "internal"), 3)


def compare_global(reference: AudioFeatures, participant: AudioFeatures) -> list[MetricComparison]:
    pauses_ok = reference.pauses.reliability == participant.pauses.reliability == "ok"
    pause_note = "" if pauses_ok else "Pause detection is flagged low-confidence or unavailable for at least one recording."
    pitch_ok = reference.pitch.reliability == participant.pitch.reliability == "ok"
    pitch_note = (
        "In semitones relative to each speaker, so different voices can be compared."
        if pitch_ok
        else "Pitch tracking is flagged unreliable or unavailable for at least one recording."
    )
    rate_note = "Syllable counts are estimates from energy peaks, not validated counts."
    return [
        _metric("duration", "s", "measured", reference.audio.duration_sec, participant.audio.duration_sec),
        _metric(
            "internal_pause_count", "count", "measured",
            reference.pauses.internal_pause_count, participant.pauses.internal_pause_count,
            comparable=pauses_ok, note=pause_note,
        ),
        _metric(
            "internal_pause_total", "s", "measured",
            _silence_total(reference), _silence_total(participant),
            comparable=pauses_ok, note=pause_note,
        ),
        _metric(
            "pitch_range", "semitones", "measured",
            reference.pitch.range_semitones, participant.pitch.range_semitones,
            comparable=pitch_ok, note=pitch_note,
        ),
        _metric(
            "pitch_interquartile_range", "semitones", "measured",
            reference.pitch.iqr_semitones, participant.pitch.iqr_semitones,
            comparable=pitch_ok, note=pitch_note,
        ),
        _metric(
            "pitch_median", "Hz", "measured",
            reference.pitch.median_hz, participant.pitch.median_hz,
            comparable=False, note="Depends on the speaker's voice, not on delivery. Shown for context only.",
        ),
        _metric(
            "speech_rate", "syllables/s", "estimated",
            reference.speaking_rate.speech_rate_syll_per_sec, participant.speaking_rate.speech_rate_syll_per_sec,
            note=rate_note,
        ),
        _metric(
            "articulation_rate", "syllables/s", "estimated",
            reference.speaking_rate.articulation_rate_syll_per_sec, participant.speaking_rate.articulation_rate_syll_per_sec,
            note=rate_note,
        ),
    ]  # fmt: skip


def compare_words(
    reference: DeliveryAnalysis, participant: DeliveryAnalysis, settings: ComparisonSettings
) -> WordLevelComparison:
    def unavailable(reason: str) -> WordLevelComparison:
        return WordLevelComparison(status="unavailable", reason=reason, min_gap_difference_sec=settings.min_gap_difference_sec)

    ref, par = reference.alignment, participant.alignment
    if ref is None or par is None:
        missing = "the reference" if ref is None else "the participant"
        return unavailable(f"No word alignment is available for {missing} recording.")
    ref_words = [normalize(w.word) for w in ref.words]
    par_words = [normalize(w.word) for w in par.words]
    if ref_words != par_words:
        return unavailable("The two recordings were not aligned to the same transcript, so their words cannot be paired.")

    # Only words actually recognised at that position in BOTH recordings have trustworthy times.
    usable = [
        r.status == "aligned" and p.status == "aligned" and None not in (r.start, r.end, p.start, p.end)
        for r, p in zip(ref.words, par.words)
    ]
    words = [
        WordComparison(
            index=r.index,
            word=p.word,
            reference=Span(start=r.start, end=r.end),
            participant=Span(start=p.start, end=p.end),
            duration_difference_sec=round((p.end - p.start) - (r.end - r.start), 3),
        )
        for r, p, ok in zip(ref.words, par.words, usable)
        if ok
    ]
    if not words:
        return unavailable("No transcript word was recognised at the same position in both recordings.")

    differences: list[TimingDifference] = []
    gaps = 0
    for i in range(len(usable) - 1):
        if not (usable[i] and usable[i + 1]):
            continue  # a gap is only measured between two adjacent words that both have times in both recordings
        gaps += 1
        ref_gap = ref.words[i + 1].start - ref.words[i].end
        par_gap = par.words[i + 1].start - par.words[i].end
        delta = par_gap - ref_gap
        if abs(delta) < settings.min_gap_difference_sec:
            continue
        longer = delta > 0
        differences.append(
            TimingDifference(
                kind="longer_gap" if longer else "shorter_gap",
                after_word_index=i,
                after_word=par.words[i].word,
                before_word=par.words[i + 1].word,
                participant_interval=Span(start=par.words[i].end, end=max(par.words[i].end, par.words[i + 1].start)),
                reference_interval=Span(start=ref.words[i].end, end=max(ref.words[i].end, ref.words[i + 1].start)),
                participant_gap_sec=round(par_gap, 3),
                reference_gap_sec=round(ref_gap, 3),
                difference_sec=round(delta, 3),
                evidence=(
                    f"The gap between '{par.words[i].word}' and '{par.words[i + 1].word}' is {par_gap:.2f} s in the "
                    f"participant recording and {ref_gap:.2f} s in the reference, {abs(delta):.2f} s "
                    f"{'longer' if longer else 'shorter'}."
                ),
            )
        )
    return WordLevelComparison(
        status="completed",
        transcript_word_count=len(ref.words),
        words_compared=len(words),
        gaps_compared=gaps,
        min_gap_difference_sec=settings.min_gap_difference_sec,
        words=words,
        timing_differences=differences,
    )


def compare_deliveries(
    reference: DeliveryAnalysis, participant: DeliveryAnalysis, settings: ComparisonSettings | None = None
) -> ComparisonResult:
    settings = settings or ComparisonSettings()
    word_level = compare_words(reference, participant, settings)
    return ComparisonResult(
        status="completed" if word_level.status == "completed" else "partial",
        global_metrics=compare_global(reference.features, participant.features),
        not_compared=NOT_COMPARED,
        word_level=word_level,
        not_implemented=NOT_IMPLEMENTED,
        limitations=[
            "These are differences, not flaws. A longer gap may be a deliberate pause; nothing here judges it.",
            "Word times come from a speech recogniser and are accurate to roughly a tenth of a second, so gap changes "
            f"smaller than {settings.min_gap_difference_sec:g} s are not reported.",
            "Only words recognised at the same position in both recordings are compared; misheard or skipped words leave gaps in coverage.",
            "No reference delivery has been rated as good. 'Reference' only means the recording being compared against.",
        ],
    )
