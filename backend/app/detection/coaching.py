"""Deterministic, rule-based coaching text built only from findings that were actually reported.

There is no language model here. Each tip is a fixed template chosen by the rule that produced
the findings, with the measured values quoted from those findings. Nothing is said about why a
difference happened, and no tip exists without a finding behind it.
"""

from pydantic import BaseModel, Field

from .schemas import Finding, FindingCategory


class CoachingTip(BaseModel):
    id: str
    category: FindingCategory
    finding_ids: list[str] = Field(description="The findings this tip is based on.")
    action: str
    practice: str
    based_on: str = Field(description="The measured evidence, quoted from the findings.")
    caution: str | None = Field(default=None, description="Present when the evidence behind the tip is weak.")
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
        "Pick the words you want to stress, raise or lower your pitch on them, then re-record and compare your pitch range with the reference.",
    ),
    "pitch_range:pitch_monotony": (
        "Try varying your pitch more, if a livelier delivery suits the text.",
        "Pick the words you want to stress, raise or lower your pitch on them, then re-record and compare the pitch range with this take.",
    ),
}

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
            )
        )
    return tips
