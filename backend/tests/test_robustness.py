"""Regression tests for pitch tracking, pause detection in noise, and clipping detection.

Expected values come from the parameters the test signals were generated with, never from
numbers copied out of the implementation.
"""

import io

import numpy as np
import pytest
import soundfile as sf

from app.audio import extract_features, load_audio
from app.audio import pitch as pitch_module
from app.audio.features import PauseSettings
from app.audio.loading import measure_clipping
from app.audio.pitch import octave_jump_fraction, speaker_range

from .audio_samples import SR, encode, loaded, silence, syllables, tone


def voice(f0_hz, duration_sec: float, *, harmonics=(1.0, 0.5, 0.33, 0.25, 0.2), amplitude: float = 0.2) -> np.ndarray:
    """A harmonic 'voice'. `f0_hz` is a number or an array giving the pitch at every sample."""
    n = int(duration_sec * SR)
    f0 = np.full(n, f0_hz, dtype=np.float64) if np.isscalar(f0_hz) else np.asarray(f0_hz, dtype=np.float64)
    phase = 2 * np.pi * np.cumsum(f0) / SR
    wave = sum(a * np.sin(k * phase) for k, a in enumerate(harmonics, start=1))
    return (amplitude * wave / max(harmonics)).astype(np.float32)


def noise(n: int, amplitude: float, seed: int = 0) -> np.ndarray:
    return (amplitude * np.random.default_rng(seed).standard_normal(n)).astype(np.float32)


def semitones(a: float, b: float) -> float:
    return 12 * np.log2(a / b)


# --- Pitch -----------------------------------------------------------------------------------

LOW_TO_HIGH = [60, 70, 85, 100, 130, 180, 240, 320, 420]


@pytest.mark.parametrize("f0", LOW_TO_HIGH)
def test_steady_voices_from_very_low_to_high_are_tracked_at_their_true_pitch(f0):
    result = extract_features(loaded(voice(f0, 2.0))).pitch

    assert result.status == "measured"
    assert abs(semitones(result.median_hz, f0)) < 0.3
    assert result.range_semitones < 0.5
    assert result.voiced_fraction > 0.9
    assert result.octave_jump_fraction == 0
    assert result.tracking_floor_hz < f0 < result.tracking_ceiling_hz
    assert result.reliability == "ok"


@pytest.mark.parametrize("f0", [70, 85, 110, 200])
def test_a_weak_fundamental_does_not_cause_an_octave_error(f0):
    """Most of the energy is in the second and third harmonics, which tempts a tracker to report double the pitch."""
    result = extract_features(loaded(voice(f0, 2.0, harmonics=(0.15, 1.0, 0.8, 0.4)))).pitch

    assert abs(semitones(result.median_hz, f0)) < 0.5
    assert result.octave_jump_fraction < 0.01


@pytest.mark.parametrize(("low", "high"), [(70, 105), (90, 150), (150, 260), (220, 400)])
def test_pitch_range_matches_the_generated_contour_for_low_and_high_speakers(low, high):
    contour = np.exp(np.linspace(np.log(low), np.log(high), 3 * SR))
    result = extract_features(loaded(voice(contour, 3.0))).pitch

    # The glide is linear in semitones, so the 5th-95th percentile range is 90% of the full span.
    assert result.range_semitones == pytest.approx(0.9 * semitones(high, low), abs=0.6)
    assert abs(semitones(result.median_hz, np.sqrt(low * high))) < 0.5
    assert result.min_hz >= low * 0.97 and result.max_hz <= high * 1.03
    assert result.reliability == "ok"


def test_the_same_contour_gives_the_same_semitone_range_for_a_low_and_a_high_speaker():
    """Speaker normalisation: ranges in semitones are comparable across speakers; Hz are not."""
    shape = np.linspace(-3, 3, 3 * SR)  # semitones around each speaker's centre
    low = extract_features(loaded(voice(80 * 2 ** (shape / 12), 3.0))).pitch
    high = extract_features(loaded(voice(220 * 2 ** (shape / 12), 3.0))).pitch

    assert low.range_semitones == pytest.approx(high.range_semitones, abs=0.4)
    assert low.iqr_semitones == pytest.approx(high.iqr_semitones, abs=0.4)
    assert (high.max_hz - high.min_hz) > 2 * (low.max_hz - low.min_hz)


def test_range_is_stable_when_only_timing_changes():
    """The Milestone 5 symptom: a low voice measured very different ranges after timing-only edits."""
    contour = 85 * 2 ** (2.5 * np.sin(np.linspace(0, 6 * np.pi, 4 * SR)) / 12)
    speech = voice(contour, 4.0)
    with_pause = np.concatenate([speech[: 2 * SR], silence(1.5), speech[2 * SR :]])
    muffled = speech + noise(len(speech), 0.002)

    ranges = [extract_features(loaded(v)).pitch.range_semitones for v in (speech, with_pause, muffled)]

    assert max(ranges) - min(ranges) < 0.5


def test_the_search_range_adapts_to_the_speaker_and_is_reported():
    low = extract_features(loaded(voice(80, 2.0))).pitch
    high = extract_features(loaded(voice(300, 2.0))).pitch

    assert low.tracking_ceiling_hz < high.tracking_floor_hz
    assert "second pass limited to this speaker's range" in low.method


def test_speaker_range_follows_the_quartiles_and_needs_enough_voicing():
    f0 = np.concatenate([np.full(50, 100.0), np.full(50, 200.0)])

    floor, ceiling = speaker_range(f0)

    assert (floor, ceiling) == (pitch_module.FLOOR_FACTOR * 100, pitch_module.CEILING_FACTOR * 200)
    assert speaker_range(np.full(5, 120.0)) is None
    assert speaker_range(np.full(100, np.nan)) is None


def test_octave_jumps_are_counted_and_flagged_as_low_reliability(monkeypatch):
    clean = np.full(200, 100.0)
    jumpy = clean.copy()
    jumpy[::10] = 200.0  # every tenth frame reported an octave too high

    assert octave_jump_fraction(clean) == 0
    # 20 wrong frames; each has a jump on both sides except the first, which has no left neighbour.
    assert octave_jump_fraction(jumpy) == pytest.approx(39 / 199)
    assert octave_jump_fraction(np.array([100.0, np.nan, 200.0])) == 0  # a gap is not a jump

    monkeypatch.setattr(pitch_module, "_praat_pass", lambda *args: (jumpy.copy(), 0.0))
    result = extract_features(loaded(voice(100, 2.0))).pitch

    assert result.reliability == "low"
    assert result.limitations[0].startswith("Low reliability:")
    assert "leap more than 8 semitones" in result.limitations[0]


def test_too_little_voicing_is_reported_as_low_reliability_not_as_a_confident_number():
    brief = np.concatenate([silence(1.0), voice(120, 0.12), silence(1.0)])

    result = extract_features(loaded(brief)).pitch

    assert result.status == "measured"
    if result.median_hz is not None:
        assert result.reliability == "low"
        assert "too little voiced speech" in result.limitations[0]


def test_noise_alone_yields_no_pitch_statistics():
    result = extract_features(loaded(noise(3 * SR, 0.1))).pitch

    assert result.voiced_fraction < 0.1
    assert result.reliability != "ok" or result.median_hz is None


# --- Pauses ----------------------------------------------------------------------------------

SPEECH = np.concatenate([syllables(8), silence(1.0), syllables(8)])  # one 1.0 s pause starting at 2.0 s


def speech_rms() -> float:
    return float(np.sqrt(np.mean(syllables(8) ** 2)))


def with_noise(snr_db: float, seed: int = 1) -> np.ndarray:
    return SPEECH + noise(len(SPEECH), speech_rms() / 10 ** (snr_db / 20), seed)


def test_clean_speech_uses_the_relative_threshold():
    result = extract_features(loaded(SPEECH)).pauses

    assert (result.status, result.threshold_rule, result.reliability) == ("measured", "relative_to_speech", "ok")
    assert result.internal_pause_count == 1
    assert result.intervals[0].start == pytest.approx(2.0, abs=0.05)
    assert result.intervals[0].end == pytest.approx(3.0, abs=0.05)
    assert result.threshold_db == pytest.approx(result.speech_level_db - 25, abs=0.01)


@pytest.mark.parametrize("snr_db", [40, 30, 20, 15, 10, 5])
def test_the_pause_is_still_found_in_background_noise(snr_db):
    result = extract_features(loaded(with_noise(snr_db))).pauses

    assert result.status == "measured"
    pause = max(result.intervals, key=lambda i: i.end - i.start)
    assert pause.start == pytest.approx(2.0, abs=0.12)
    assert pause.end == pytest.approx(3.0, abs=0.12)
    assert result.noise_floor_db < result.threshold_db < result.speech_level_db


def test_noise_switches_the_rule_and_reports_measured_levels():
    quiet = extract_features(loaded(SPEECH)).pauses
    noisy = extract_features(loaded(with_noise(10))).pauses

    assert noisy.threshold_rule == "noise_floor"
    assert noisy.threshold_db == pytest.approx(noisy.noise_floor_db + 3, abs=0.01)
    assert noisy.noise_floor_db > quiet.noise_floor_db + 40
    assert noisy.dynamic_range_db == pytest.approx(noisy.speech_level_db - noisy.noise_floor_db, abs=0.01)
    assert "Background noise detected" in noisy.method


def test_very_noisy_speech_is_flagged_as_low_confidence():
    result = extract_features(loaded(with_noise(5))).pauses

    assert result.reliability == "low"
    assert result.limitations[0].startswith("Low confidence:")
    assert extract_features(loaded(with_noise(30))).pauses.reliability == "ok"


def test_steady_noise_and_silence_report_pauses_as_unavailable_with_the_reason():
    steady = extract_features(loaded(noise(3 * SR, 0.1))).pauses
    quiet = extract_features(loaded(silence(2.0))).pauses

    assert steady.status == quiet.status == "unavailable"
    assert steady.intervals == quiet.intervals == []
    assert "barely changes" in steady.limitations[0]
    assert "too quiet" in quiet.limitations[0]
    assert steady.dynamic_range_db < 6


@pytest.mark.parametrize(("gap_sec", "expected"), [(0.05, 0), (0.12, 0), (0.2, 0), (0.3, 1), (0.5, 1)])
def test_gaps_shorter_than_the_minimum_are_not_pauses(gap_sec, expected):
    signal = np.concatenate([syllables(8), silence(gap_sec), syllables(8)])

    result = extract_features(loaded(signal)).pauses

    assert result.internal_pause_count == expected
    if expected:
        # The syllables fade in and out, so the detected silence is slightly longer than the gap.
        assert result.total_internal_pause_sec == pytest.approx(gap_sec, abs=0.06)


def test_thresholds_are_configurable():
    # Loud speech, a 0.15 s gap, 1.5 s of speech 34 dB quieter, then loud speech again.
    signal = np.concatenate([syllables(8), silence(0.15), 0.02 * syllables(6), syllables(8)])
    audio = loaded(signal)

    default = extract_features(audio).pauses
    deeper = extract_features(audio, pause_settings=PauseSettings(silence_below_speech_db=45)).pauses
    deeper_short = extract_features(
        audio, pause_settings=PauseSettings(silence_below_speech_db=45, min_pause_sec=0.1)
    ).pauses

    # By default the quiet stretch is more than 25 dB down, so it and the gap read as one long silence.
    assert default.internal_pause_count == 1
    assert default.total_internal_pause_sec == pytest.approx(1.65, abs=0.1)
    # At 45 dB the quiet stretch is speech, and the 0.15 s gap is below the default minimum pause...
    assert deeper.internal_pause_count == 0
    assert deeper.threshold_db == pytest.approx(deeper.speech_level_db - 45, abs=0.01)
    # ...until the minimum pause is lowered too.
    assert deeper_short.min_pause_sec == 0.1
    assert deeper_short.internal_pause_count >= 1
    assert deeper_short.intervals[0].start == pytest.approx(2.0, abs=0.05)


def test_a_single_click_does_not_move_the_threshold():
    clicked = SPEECH.copy()
    clicked[SR // 2] = 1.0  # one full-scale sample

    result = extract_features(loaded(clicked)).pauses

    assert result.internal_pause_count == 1
    assert result.threshold_db == pytest.approx(extract_features(loaded(SPEECH)).pauses.threshold_db, abs=0.5)


# --- Clipping --------------------------------------------------------------------------------


def clipped_tone(gain: float = 3.0, limit: float = 1.0) -> np.ndarray:
    return np.clip(gain * tone(220, 1.0, amplitude=0.5), -limit, limit).astype(np.float32)


def test_hard_clipping_is_detected():
    result = extract_features(loaded(clipped_tone())).clipping

    assert (result.status, result.verdict) == ("measured", "detected")
    assert result.flat_top_runs > 100  # two flat tops per cycle of a 220 Hz tone for one second
    assert result.longest_flat_run_samples >= 3
    assert result.flat_top_sample_fraction > 0.3
    assert result.peak_amplitude == pytest.approx(1.0, abs=0.001)


def test_clean_audio_is_not_flagged():
    for signal in (tone(220, 1.0, amplitude=0.5), syllables(8), voice(90, 1.0)):
        result = extract_features(loaded(signal)).clipping

        assert result.verdict == "not_detected"
        assert result.flat_top_runs == 0


def test_clipping_below_full_scale_is_still_detected():
    """Clipped, then turned down: the flat tops remain even though nothing is near full scale."""
    result = extract_features(loaded(0.4 * clipped_tone())).clipping

    assert result.verdict == "detected"
    assert result.peak_amplitude == pytest.approx(0.4, abs=0.001)
    assert result.near_full_scale_fraction == 0


def test_a_clean_signal_at_full_scale_is_uncertain_not_detected():
    result = extract_features(loaded(tone(220, 1.0, amplitude=0.9999))).clipping

    assert result.verdict == "uncertain"
    assert result.flat_top_runs == 0
    assert "reaches full scale but its peaks are not flat" in result.limitations[0]


def test_slow_waves_at_a_high_sample_rate_are_not_mistaken_for_clipping():
    """Near its peak a 50 Hz wave at 96 kHz repeats the same 16-bit value several times without being clipped."""
    rate = 96_000
    slow = 0.5 * np.sin(2 * np.pi * 50 * np.arange(rate) / rate).astype(np.float32)

    stats = load_audio(encode(slow, sample_rate=rate), "slow.wav", max_duration_sec=10).clipping

    assert stats.flat_top_runs == 0


def test_a_few_flat_peaks_are_uncertain():
    signal = tone(220, 1.0, amplitude=0.5)
    signal[4000:4006] = 0.8  # one short flat burst

    result = extract_features(loaded(signal)).clipping

    assert result.verdict == "uncertain"
    assert result.flat_top_runs == 1
    assert "too few to be sure" in result.limitations[0]


def test_clipping_in_one_stereo_channel_is_found_before_mixing_to_mono():
    stereo = np.stack([clipped_tone(), tone(330, 1.0, amplitude=0.1)], axis=1)
    audio = loaded(stereo)

    assert extract_features(audio).clipping.verdict == "detected"
    # The mono mix that the other features use no longer has flat tops.
    assert measure_clipping(audio.samples[:, None]).flat_top_runs == 0


def test_clipping_is_measured_before_resampling():
    rate = 44_100
    clipped = np.clip(3 * tone(220, 1.0, amplitude=0.5, sample_rate=rate), -1, 1)

    assert extract_features(loaded(clipped, sample_rate=rate)).clipping.verdict == "detected"


def test_lossy_formats_never_claim_a_clean_result_at_high_level():
    buffer = io.BytesIO()
    sf.write(buffer, clipped_tone(), SR, format="MP3")
    result = extract_features(load_audio(buffer.getvalue(), "clipped.mp3", max_duration_sec=10)).clipping

    assert result.verdict in ("detected", "uncertain")
    assert any("lossily encoded" in text for text in result.limitations)


def test_silence_has_no_clipping_and_does_not_divide_by_zero():
    result = extract_features(loaded(silence(1.0))).clipping

    assert (result.verdict, result.flat_top_runs, result.peak_amplitude) == ("not_detected", 0, 0)


# --- Configurable pitch range and the stability check (Milestone 5.2) -------------------------


def test_the_pitch_search_range_is_configurable():
    from app.audio.pitch import PitchSettings

    very_low = loaded(voice(45, 2.0))

    default = extract_features(very_low).pitch
    widened = extract_features(very_low, pitch_settings=PitchSettings(min_hz=35)).pitch
    narrowed = extract_features(loaded(voice(80, 2.0)), pitch_settings=PitchSettings(min_hz=120, max_hz=400)).pitch

    # Below the default 50 Hz floor the true pitch cannot be reported; lowering the floor makes it trackable.
    assert default.median_hz is None or abs(semitones(default.median_hz, 45)) > 3
    assert abs(semitones(widened.median_hz, 45)) < 0.5
    assert "First pass 35-600 Hz" in widened.method
    # A floor above the voice cannot produce the true pitch either, and never reports a value below the floor.
    assert narrowed.min_hz is None or narrowed.min_hz >= 120


@pytest.mark.parametrize("bounds", [(0, 600), (300, 200), (50, 5000), (10, 100)])
def test_invalid_pitch_ranges_are_rejected(bounds):
    from app.audio.pitch import PitchSettings

    with pytest.raises(ValueError, match="pitch range"):
        PitchSettings(min_hz=bounds[0], max_hz=bounds[1])


@pytest.mark.parametrize("f0", [60, 85, 150, 300])
def test_steady_voices_pass_the_stability_check(f0):
    result = extract_features(loaded(voice(f0, 2.0))).pitch

    assert result.range_sensitivity_semitones is not None
    assert result.range_sensitivity_semitones < 0.3
    assert result.reliability == "ok"


def test_pitch_range_settings_come_from_the_environment(monkeypatch):
    from app.config import Settings

    monkeypatch.setenv("PITCH_MIN_HZ", "40")
    monkeypatch.setenv("PITCH_MAX_HZ", "450")

    settings = Settings().pitch_settings

    assert (settings.min_hz, settings.max_hz) == (40, 450)


# --- The real low-pitched, creaky voice in the committed examples (limitations fix) -----------


def example_features():
    """Pitch results for the committed example recordings of LibriSpeech speaker 5703 (median about 80 Hz)."""
    import json

    from app.dataset.__main__ import EXAMPLES_DIR

    manifest = json.loads((EXAMPLES_DIR / "manifest.json").read_text(encoding="utf-8"))
    results = {}
    for sample in manifest["samples"]:
        path = EXAMPLES_DIR / sample["audio_path"]
        audio = load_audio(path.read_bytes(), path.name, max_duration_sec=600)
        results[sample["flaw_category"] or "reference"] = extract_features(audio)
    return results


def test_the_real_low_voice_is_measured_and_flagged_rather_than_discarded_or_trusted():
    features = example_features()
    reference = features["reference"].pitch

    # The low pitch is reported, not thrown away for being under 75 Hz.
    assert reference.status == "measured"
    assert 60 < reference.median_hz < 100
    assert reference.tracking_floor_hz < 75
    # But this recording's range moves when the tracker's limit is nudged, so it is marked unreliable.
    assert reference.reliability == "low"
    assert reference.range_sensitivity_semitones > 1 or "voiced frames by" in reference.limitations[0]
    assert "changes when the tracker's lower limit is nudged" in reference.limitations[0]


def test_recordings_of_that_voice_judged_reliable_agree_with_each_other():
    """Only timing was changed in these samples, so their pitch range should match. The ones the stability
    check accepts do agree; the ones that would disagree are the ones it rejects."""
    features = example_features()
    timing_only = ("rushed_delivery", "slow_delivery", "uneven_pacing", "excessive_pauses")
    accepted = [features[c].pitch.range_semitones for c in timing_only if features[c].pitch.reliability == "ok"]

    assert len(accepted) >= 2
    assert max(accepted) - min(accepted) < 1.5
    assert all(features[c].pitch.range_sensitivity_semitones < 1 for c in timing_only if features[c].pitch.reliability == "ok")


def test_pitch_findings_are_withheld_for_the_unreliable_real_recording():
    from app.comparison.schemas import DeliveryAnalysis
    from app.detection import run_detection

    result = run_detection(DeliveryAnalysis(features=example_features()["reference"]))

    report = next(r for r in result.rules if r.category == "pitch_monotony")
    assert report.status == "withheld"
    assert "not reliable for this recording" in report.reason
    assert not any(f.category == "pitch_monotony" for f in result.findings)
