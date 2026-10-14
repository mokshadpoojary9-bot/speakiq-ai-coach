"""The pitch reliability evaluation: how withheld recordings and false readings are counted."""

import pytest

from app.audio.evaluate_pitch import Reading, summarize, track_from_opening
from app.audio.pitch import pitch, track_pitch

from .audio_samples import SR
from .detection_fixtures import make_take


def test_a_reported_range_that_ignores_its_known_compression_is_a_false_reading():
    readings = [
        Reading("a", 1.0, 9.0, True),
        Reading("a", 1.0, 9.4, True),
        Reading("a", 1.0, 12.0, False),  # withheld: counted, never judged
        Reading("a", 0.5, 4.8, True),  # 9.2 x 0.5 = 4.6: fine
        Reading("a", 0.1, 6.6, True),  # should be about 0.9: false
    ]

    (summary,) = summarize(readings)

    assert (summary.recordings, summary.withheld, summary.false_readings) == (5, 1, 1)
    assert summary.expected_range == pytest.approx(9.2)


def test_without_a_reliable_pitch_preserving_reading_nothing_can_vouch_for_the_rest():
    (summary,) = summarize([Reading("b", 1.0, 7.0, False), Reading("b", 0.35, 3.0, True)])

    assert summary.expected_range is None
    assert (summary.withheld, summary.false_readings) == (1, 1)


def test_a_range_chosen_from_the_opening_seconds_misses_notes_the_speaker_reaches_later():
    """Why the tracker keeps using the whole recording: here the first 3 s sit in the upper half of the
    voice, so the search floor is set too high and the stability check rightly flags the result."""
    take = make_take(words=30, base_hz=140, swing_semitones=3.0)  # the pitch swing repeats every 4 s

    usual = pitch(track_pitch(take.audio, SR))
    whole = pitch(track_from_opening(take.audio, SR, 60.0))
    opening = pitch(track_from_opening(take.audio, SR, 3.0))

    assert usual.reliability == whole.reliability == "ok"
    assert whole.range_semitones == usual.range_semitones
    assert opening.tracking_floor_hz > usual.tracking_floor_hz
    assert opening.reliability == "low"
    assert opening.method == "range from the first 3 s"
