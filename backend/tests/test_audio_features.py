import math

import numpy as np
import pytest
from pydantic import ValidationError

from app.audio import AudioError, extract_features, load_audio
from app.audio import pitch as pitch_module
from app.audio.schemas import Interval

from .audio_samples import SR, encode, loaded, silence, syllables, tone


def test_reports_duration_sample_rate_and_channels_of_the_original_file():
    stereo = np.stack([tone(220, 2.0, sample_rate=44_100)] * 2, axis=1)

    result = extract_features(loaded(stereo, sample_rate=44_100))

    assert result.is_demo is False
    assert result.audio.duration_sec == pytest.approx(2.0, abs=0.005)
    assert result.audio.sample_rate_hz == 44_100
    assert result.audio.channels == 2
    assert result.audio.analysis_sample_rate_hz == SR


def test_waveform_and_energy_match_a_known_amplitude():
    result = extract_features(loaded(tone(220, 2.0, amplitude=0.5)))

    assert len(result.waveform.peaks) == 1000
    assert max(result.waveform.peaks) == pytest.approx(0.5, abs=0.01)
    assert result.audio.peak_amplitude == pytest.approx(0.5, abs=0.01)
    # RMS of a sine is amplitude / sqrt(2).
    assert result.energy.max_db == pytest.approx(20 * math.log10(0.5 / math.sqrt(2)), abs=0.3)
    assert result.energy.series.unit == "dBFS"
    assert result.energy.series.hop_sec == pytest.approx(0.01)
    assert len(result.energy.series.values) == pytest.approx(200, abs=2)


def test_pitch_of_a_pure_tone_is_its_frequency():
    result = extract_features(loaded(tone(220, 2.0)))

    assert result.pitch.status == "measured"
    assert "Praat" in result.pitch.method
    assert result.pitch.median_hz == pytest.approx(220, abs=2)
    assert result.pitch.voiced_fraction > 0.9
    assert result.pitch.range_semitones == pytest.approx(0, abs=0.2)


def test_pitch_range_reflects_a_rising_contour():
    t = np.arange(2 * SR) / SR
    glide = 0.5 * np.sin(2 * np.pi * np.cumsum(np.linspace(150, 300, len(t))) / SR)

    result = extract_features(loaded(glide.astype(np.float32)))

    assert result.pitch.min_hz < 165
    assert result.pitch.max_hz > 280
    # A full octave is 12 semitones; the 5th-95th percentile range is a little narrower.
    assert 9 < result.pitch.range_semitones < 12


def test_pitch_falls_back_to_pyin_when_praat_fails(monkeypatch):
    def broken(*_):
        raise RuntimeError("praat missing")

    monkeypatch.setattr(pitch_module, "_praat_track", broken)

    result = extract_features(loaded(tone(220, 1.0)))

    assert result.pitch.status == "measured"
    assert "pYIN" in result.pitch.method
    assert result.pitch.median_hz == pytest.approx(220, abs=3)


def test_pitch_is_unavailable_not_invented_when_no_tracker_works(monkeypatch):
    def broken(*_):
        raise RuntimeError("no tracker")

    monkeypatch.setattr(pitch_module, "_praat_track", broken)
    monkeypatch.setattr(pitch_module, "_pyin_track", broken)

    result = extract_features(loaded(syllables(8)))

    assert result.pitch.status == "unavailable"
    assert result.pitch.series is None
    assert result.pitch.median_hz is None
    # Other features still work, and the rate estimate says what it could not check.
    assert result.energy.status == "measured"
    assert result.speaking_rate.status == "estimated"
    assert any("Without pitch" in text for text in result.speaking_rate.limitations)


def test_detects_an_internal_pause_at_the_right_time():
    signal = np.concatenate([tone(200, 1.0), silence(0.8), tone(200, 1.0)])

    result = extract_features(loaded(signal))

    assert result.pauses.status == "measured"
    assert result.pauses.internal_pause_count == 1
    (pause,) = result.pauses.intervals
    assert pause.position == "internal"
    assert pause.start == pytest.approx(1.0, abs=0.04)
    assert pause.end == pytest.approx(1.8, abs=0.04)
    assert result.pauses.total_internal_pause_sec == pytest.approx(0.8, abs=0.06)
    assert result.pauses.speech_sec == pytest.approx(2.0, abs=0.06)


def test_classifies_leading_and_trailing_silence_and_ignores_short_gaps():
    signal = np.concatenate([silence(0.5), tone(200, 1.0), silence(0.1), tone(200, 1.0), silence(0.6)])

    result = extract_features(loaded(signal))

    assert [p.position for p in result.pauses.intervals] == ["leading", "trailing"]
    assert result.pauses.internal_pause_count == 0
    assert result.pauses.intervals[-1].end <= result.audio.duration_sec


def test_speaking_rate_estimate_counts_evenly_spaced_syllables():
    signal = np.concatenate([syllables(8, rate_per_sec=4), silence(1.0), syllables(8, rate_per_sec=4)])

    result = extract_features(loaded(signal))

    rate = result.speaking_rate
    assert rate.status == "estimated"
    assert rate.syllable_nuclei == 16
    assert rate.speech_rate_syll_per_sec == pytest.approx(16 / 5.0, abs=0.1)
    # Excluding the pause, the rate is higher than over the whole recording.
    assert rate.articulation_rate_syll_per_sec > rate.speech_rate_syll_per_sec
    assert all(0 <= t <= result.audio.duration_sec for t in rate.syllable_times_sec)
    assert not any(1.95 < t < 3.05 for t in rate.syllable_times_sec)


def test_spectral_centroid_tracks_frequency_content():
    low = extract_features(loaded(tone(1000, 1.0)))
    high = extract_features(loaded(tone(3000, 1.0)))

    assert low.spectral.status == "measured"
    assert low.spectral.mean_centroid_hz == pytest.approx(1000, abs=60)
    assert high.spectral.mean_centroid_hz == pytest.approx(3000, abs=60)
    assert high.spectral.mean_rolloff_hz > low.spectral.mean_rolloff_hz
    assert high.spectral.mean_zero_crossing_rate > low.spectral.mean_zero_crossing_rate


def test_mfcc_summary_has_thirteen_finite_coefficients_that_depend_on_the_signal():
    a = extract_features(loaded(tone(300, 1.0))).mfcc
    b = extract_features(loaded(syllables(4))).mfcc

    assert a.n_mfcc == 13
    assert len(a.mean) == len(a.std) == 13
    assert all(math.isfinite(v) for v in a.mean + a.std)
    assert a.mean != b.mean


def test_near_silent_recording_reports_timing_as_unavailable():
    result = extract_features(loaded(silence(1.0)))

    assert result.energy.status == "measured"
    assert result.pauses.status == "unavailable"
    assert result.pauses.intervals == []
    assert result.speaking_rate.status == "unavailable"
    assert result.speaking_rate.syllable_nuclei is None
    assert result.pitch.voiced_fraction == 0
    assert result.pitch.median_hz is None


def test_transcript_rate_needs_a_transcript_and_is_labelled_an_estimate():
    audio = loaded(tone(200, 2.0))

    without = extract_features(audio).transcript_rate
    with_text = extract_features(audio, "Good morning everyone, it's a well-known fact.").transcript_rate

    assert without.status == "unavailable"
    assert without.words_per_minute is None
    assert with_text.status == "estimated"
    assert with_text.word_count == 7
    assert with_text.words_per_minute == pytest.approx(210, abs=1)
    assert any("not checked" in text for text in with_text.limitations)


def test_long_series_are_thinned_and_report_their_real_hop():
    result = extract_features(loaded(tone(200, 45.0)))

    assert len(result.energy.series.values) <= 3000
    assert result.energy.series.hop_sec == pytest.approx(0.02)
    assert len(result.energy.series.values) * result.energy.series.hop_sec == pytest.approx(45.0, abs=0.1)


def test_every_metric_states_its_status_and_method():
    result = extract_features(loaded(syllables(8)))

    for name in ("waveform", "energy", "spectral", "mfcc", "pitch", "pauses", "speaking_rate", "transcript_rate"):
        metric = getattr(result, name)
        assert metric.status in ("measured", "estimated", "unavailable"), name
        assert metric.method, name
    assert result.limitations


def test_interval_rejects_end_not_after_start():
    with pytest.raises(ValidationError):
        Interval(start=2.0, end=2.0)
    with pytest.raises(ValidationError):
        Interval(start=-1.0, end=2.0)


@pytest.mark.parametrize(
    ("data", "filename", "status"),
    [
        (b"not audio at all", "talk.wav", 415),
        (encode(tone(200, 1.0)), "talk.txt", 415),
        (encode(tone(200, 1.0)), "talk", 415),
        (b"", "talk.wav", 400),
        (encode(tone(200, 0.1)), "talk.wav", 400),
        (encode(tone(200, 3.0)), "talk.wav", 413),
    ],
    ids=["not-audio", "wrong-extension", "no-extension", "empty", "too-short", "too-long"],
)
def test_load_audio_rejects_bad_input(data, filename, status):
    with pytest.raises(AudioError) as error:
        load_audio(data, filename, max_duration_sec=2.0)

    assert error.value.status_code == status


def test_load_audio_strips_directories_from_the_filename():
    audio = load_audio(encode(tone(200, 1.0)), "../../secret/talk.wav", max_duration_sec=10)

    assert audio.filename == "talk.wav"
