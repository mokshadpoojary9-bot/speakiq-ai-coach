"""Deterministic, rule-based coaching text built only from findings that were actually reported.

There is no language model here. Each tip is a fixed template chosen by the rule that produced
the findings, with the measured values quoted from those findings. Nothing is said about why a
difference happened, and no tip exists without a finding behind it.
"""

from typing import Literal

from pydantic import BaseModel, Field

from .schemas import Finding, FindingCategory


class TipEvidence(BaseModel):
    """The measurement behind a recommendation, copied from one finding. Never recomputed or filled in."""

    finding_id: str
    start: float = Field(description="Interval in the participant recording, as the finding reports it.")
    end: float
    feature: str
    unit: str
    participant_value: float | None
    reference_value: float | None = Field(description="Null when there was no reference to compare with.")
    difference: float | None
    evidence_quality: str


class CoachingTip(BaseModel):
    id: str
    category: FindingCategory
    finding_ids: list[str] = Field(description="The findings this tip is based on.")
    action: str
    practice: str
    based_on: str = Field(description="The measured evidence, quoted from the findings.")
    caution: str | None = Field(default=None, description="Present when the evidence behind the tip is weak.")
    # confirmed: every finding behind it rests on a usable measurement. uncertain: at least one is weak, or the
    # rule itself only ever claims a possibility.
    certainty: Literal["confirmed", "uncertain"] = "confirmed"
    reason: str = Field(default="", description="Why the measurement leads to this recommendation.")
    evidence: list[TipEvidence] = Field(default=[], description="One entry per finding, in the same order as finding_ids.")
    source: str = "rule_based"


# (action, practice) by the rule that produced the finding.
TEMPLATES: dict[str, tuple[str, str]] = {
    "pace_vs_reference:rushed_delivery": (
        "Slow down across this passage.",
        "Re-record it aiming to take about as long as the reference does over the same words, then run the comparison again and check the speaking time.",
    ),
    "pace_vs_reference:slow_delivery": (
        "Pick up the pace across this passage.",
        "Re-record it aiming to take about as long as the reference does over the same words, then run the comparison again and check the speaking time.",
    ),
    "pace_words_per_minute:rushed_delivery": (
        "Try a slower overall pace.",
        "Re-record the passage a little slower and compare the words-per-minute figure with this take. Adding a reference recording gives a word-for-word comparison.",
    ),
    "pace_words_per_minute:slow_delivery": (
        "Try a quicker overall pace.",
        "Re-record the passage a little faster and compare the words-per-minute figure with this take. Adding a reference recording gives a word-for-word comparison.",
    ),
    "pause_vs_reference:excessive_pause": (
        "Shorten the pauses at the marked points, unless you meant them.",
        "Rehearse the phrase on either side of each marked pause as one unit, then re-record and check the silence at those words against the reference.",
    ),
    "long_pause:excessive_pause": (
        "Check the long pauses at the marked points and shorten any you did not intend.",
        "Mark where you want to pause in the text, rehearse to those marks, then re-record and compare the pause lengths.",
    ),
    "pause_placement_vs_reference:irregular_pauses": (
        "Try pausing where the reference pauses.",
        "Mark the reference's pause points in your text, rehearse pausing briefly at each, then re-record and run the comparison again.",
    ),
    "pacing_vs_reference:uneven_pacing": (
        "Even out your pace between the marked stretches.",
        "Practise the faster and slower stretches back to back at one steady pace, then re-record and check that the stretches no longer stand out.",
    ),
    "filler_lexicon:filler_word": (
        "Replace the filler sounds with a short silent pause.",
        "Rehearse the sentences around each marked filler, stopping silently where the filler was, then re-record and check whether they are still recognised.",
    ),
    "pitch_range_vs_reference:pitch_monotony": (
        "Try varying your pitch more, if a livelier delivery suits the text.",
        "Pick the words you want to emphasise, raise or lower your pitch on them, then re-record and compare your pitch range with the reference.",
    ),
    "pitch_range:pitch_monotony": (
        "Try varying your pitch more, if a livelier delivery suits the text.",
        "Pick the words you want to emphasise, raise or lower your pitch on them, then re-record and compare the pitch range with this take.",
    ),
}

# Why each measurement leads to its recommendation. These describe the measurement, never a cause.
REASONS: dict[str, str] = {
    "pace_vs_reference:rushed_delivery": (
        "The measured speaking time for the same words, with pauses removed, was shorter than the reference's by more "
        "than the rule's threshold. Taking about as long as the reference over these words would remove the difference."
    ),
    "pace_vs_reference:slow_delivery": (
        "The measured speaking time for the same words, with pauses removed, was longer than the reference's by more "
        "than the rule's threshold. Taking about as long as the reference over these words would remove the difference."
    ),
    "pace_words_per_minute:rushed_delivery": (
        "The measured rate of recognised words was above the upper limit for English speech. There is no reference "
        "recording, so this compares with a general limit, not with how this text should be read."
    ),
    "pace_words_per_minute:slow_delivery": (
        "The measured rate of recognised words was below the lower limit for English speech. There is no reference "
        "recording, so this compares with a general limit, not with how this text should be read."
    ),
    "pause_vs_reference:excessive_pause": (
        "The measured silence at these points was longer than the reference's silence at the same words by more than "
        "the rule's threshold. Pauses you intended can stay; the others are where the timing differs."
    ),
    "long_pause:excessive_pause": (
        "The measured silence at these points was longer than the fixed limit. With no reference recording there is "
        "no way to tell which pauses were intended, so check each one."
    ),
    "pause_placement_vs_reference:irregular_pauses": (
        "The reference has a measured pause at these points and your measured silence there was shorter by more than "
        "the rule's threshold, so your pause pattern differs from the reference's here."
    ),
    "pacing_vs_reference:uneven_pacing": (
        "Your measured pace against the reference changed between these stretches by more than the rule's threshold, "
        "relative to your own overall pace."
    ),
    "filler_lexicon:filler_word": (
        "The recogniser transcribed these hesitation sounds at these times. Only recognised fillers are counted, so "
        "there may be others."
    ),
    "pitch_range_vs_reference:pitch_monotony": (
        "Your measured pitch range over voiced speech, relative to your own voice, was at most the rule's fraction of "
        "the reference's range over the same words. This is worded as a possibility because pitch tracking makes errors."
    ),
    "pitch_range:pitch_monotony": (
        "Your measured pitch range over voiced speech, relative to your own voice, was below the rule's limit. This is "
        "worded as a possibility because pitch tracking makes errors and a narrow range is a normal style for many people."
    ),
}

# Rules whose findings only ever claim a possibility, however clean the recording.
POSSIBILITY_RULES = {"pitch_range_vs_reference", "pitch_range"}

MAX_QUOTED = 3


def build_coaching(findings: list[Finding]) -> list[CoachingTip]:
    """One tip per rule and category that has findings, in the order the findings occur."""
    groups: dict[str, list[Finding]] = {}
    for finding in findings:
        groups.setdefault(f"{finding.rule.rule_id}:{finding.category}", []).append(finding)

    tips = []
    for key, group in groups.items():
        if key not in TEMPLATES:
            continue  # no advice is invented for a rule without a written template
        action, practice = TEMPLATES[key]
        quoted = " ".join(f.explanation for f in group[:MAX_QUOTED])
        more = len(group) - MAX_QUOTED
        weak = [f for f in group if f.evidence_quality == "low"]
        possible = group[0].rule.rule_id in POSSIBILITY_RULES or any(f.title.startswith("Possibl") for f in group)
        tips.append(
            CoachingTip(
                id=f"tip:{key}",
                category=group[0].category,
                finding_ids=[f.id for f in group],
                action=action,
                practice=practice,
                based_on=quoted + (f" And {more} more like this." if more > 0 else ""),
                caution=(
                    None
                    if not weak
                    else "The evidence behind this is weak for this recording (see the findings' limitations). Check the recording quality before acting on it."
                    if len(weak) == len(group)
                    else f"{len(weak)} of the {len(group)} findings behind this have weak evidence; see their limitations before acting on it."
                ),
                certainty="uncertain" if weak or possible else "confirmed",
                reason=REASONS[key],
                evidence=[
                    TipEvidence(
                        finding_id=f.id,
                        start=f.start,
                        end=f.end,
                        feature=f.evidence[0].feature,
                        unit=f.evidence[0].unit,
                        participant_value=f.evidence[0].participant_value,
                        reference_value=f.evidence[0].reference_value,
                        difference=f.evidence[0].difference,
                        evidence_quality=f.evidence_quality,
                    )
                    for f in group
                ],
            )
        )
    return tips
