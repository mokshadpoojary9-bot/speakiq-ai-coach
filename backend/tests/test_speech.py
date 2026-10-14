import pytest

from app.config import Settings
from app.speech import FasterWhisperTranscriber, SpeechError, align_transcript
from app.speech.alignment import normalize
from app.speech.schemas import RecognizedWord

from .audio_samples import SR, tone
from .speech_fakes import FakeModel, FakeSegment, FakeWord, segment, transcriber_failing_to_load, transcriber_with

AUDIO = tone(200, 2.0)
SECRET = "hf_test_secret_value_123"


def heard(text: str, step: float = 0.5) -> list[RecognizedWord]:
    return [
        RecognizedWord(word=token, start=i * step, end=i * step + 0.4, probability=0.9)
        for i, token in enumerate(text.split())
    ]


# --- Transcription -----------------------------------------------------------------------------


def test_transcription_maps_model_output_to_words_and_segments():
    model = FakeModel([segment("Good morning everyone.", 0.1)])

    result = transcriber_with(model).transcribe(AUDIO, SR, language="en")

    assert result.status == "completed"
    assert result.text == "Good morning everyone."
    assert result.language == "en"
    assert result.language_probability == 0.988
    assert result.duration_sec == 2.0
    assert result.engine == "faster-whisper"
    assert result.word_timestamps == "available"
    assert [w.word for w in result.words] == ["Good", "morning", "everyone."]
    assert result.words[0].start == 0.1
    assert result.words[0].probability == 0.9
    assert model.calls[0]["word_timestamps"] is True
    assert model.calls[0]["language"] == "en"


def test_transcription_clamps_times_to_the_recording():
    model = FakeModel([FakeSegment(" late", 1.5, 9.0, [FakeWord(" late", 1.5, 9.0)])])

    result = transcriber_with(model).transcribe(AUDIO, SR)

    assert result.words[0].end == 2.0
    assert result.segments[0].end == 2.0


def test_no_speech_is_reported_rather_than_invented():
    result = transcriber_with(FakeModel([])).transcribe(AUDIO, SR)

    assert result.status == "no_speech"
    assert result.text == ""
    assert result.words == []
    assert result.word_timestamps == "unavailable"


def test_missing_word_timestamps_are_reported_as_unavailable():
    model = FakeModel([FakeSegment(" Hello there", 0.0, 1.0, None)])

    result = transcriber_with(model).transcribe(AUDIO, SR)

    assert result.text == "Hello there"
    assert result.words == []
    assert result.word_timestamps == "unavailable"
    assert "without word-level timestamps" in result.limitations[0]


def test_model_is_loaded_once_and_reused():
    loads = []
    model = FakeModel([segment("hello", 0.0)])
    transcriber = FasterWhisperTranscriber(Settings(), model_loader=lambda s: loads.append(s) or model)

    assert transcriber.status().model_loaded is False
    transcriber.transcribe(AUDIO, SR)
    transcriber.transcribe(AUDIO, SR)

    assert len(loads) == 1
    assert transcriber.status().model_loaded is True


def test_missing_dependency_gives_install_instructions():
    transcriber = transcriber_failing_to_load(ImportError("No module named 'faster_whisper'"))

    with pytest.raises(SpeechError) as error:
        transcriber.transcribe(AUDIO, SR)

    assert error.value.code == "missing_dependency"
    assert error.value.status_code == 503
    assert "pip install -r requirements.txt" in error.value.message


def test_gated_model_without_token_explains_how_to_configure_it():
    settings = Settings(whisper_model="private-org/gated-model", hf_token=None)
    transcriber = transcriber_failing_to_load(RuntimeError("401 Client Error: Unauthorized"), settings)

    with pytest.raises(SpeechError) as error:
        transcriber.transcribe(AUDIO, SR)

    assert error.value.code == "hf_auth_required"
    assert "HF_TOKEN" in error.value.message
    assert "backend/.env" in error.value.message
    assert "public model" in error.value.message


def test_rejected_token_is_reported_without_revealing_it():
    settings = Settings(whisper_model="private-org/gated-model", hf_token=SECRET)
    transcriber = transcriber_failing_to_load(RuntimeError(f"403 Forbidden for token {SECRET}"), settings)

    with pytest.raises(SpeechError) as error:
        transcriber.transcribe(AUDIO, SR)

    assert error.value.code == "hf_auth_rejected"
    assert SECRET not in error.value.message
    assert error.value.__cause__ is None  # the original error text is not chained into responses or logs
    assert SECRET not in repr(settings)
    assert transcriber.status().hf_token_configured is True


@pytest.mark.parametrize(
    ("error", "code"),
    [
        (ConnectionError("Failed to establish a new connection: getaddrinfo failed"), "model_download_failed"),
        (ValueError("Requested int8 compute type, but the target device does not support it"), "model_load_failed"),
    ],
    ids=["offline", "bad-settings"],
)
def test_other_load_failures_are_classified(error, code):
    with pytest.raises(SpeechError) as raised:
        transcriber_failing_to_load(error).transcribe(AUDIO, SR)

    assert raised.value.code == code
    assert raised.value.status_code == 503


def test_a_failed_load_is_retried_on_the_next_request():
    attempts = []

    def loader(_):
        attempts.append(1)
        if len(attempts) == 1:
            raise ConnectionError("offline")
        return FakeModel([segment("hello", 0.0)])

    transcriber = FasterWhisperTranscriber(Settings(), model_loader=loader)

    with pytest.raises(SpeechError):
        transcriber.transcribe(AUDIO, SR)
    assert transcriber.transcribe(AUDIO, SR).text == "hello"


def test_model_failure_during_decoding_is_a_transcription_failure():
    transcriber = transcriber_with(FakeModel(error=RuntimeError("decoder exploded")))

    with pytest.raises(SpeechError) as error:
        transcriber.transcribe(AUDIO, SR)

    assert error.value.code == "transcription_failed"
    assert error.value.status_code == 500


def test_empty_hf_token_placeholder_counts_as_not_configured(monkeypatch):
    monkeypatch.setenv("HF_TOKEN", "")
    assert Settings().hf_token is None
    monkeypatch.setenv("HF_TOKEN", "  ")
    assert Settings().hf_token is None


# --- Alignment ---------------------------------------------------------------------------------


def test_aligns_every_word_ignoring_case_and_punctuation():
    result = align_transcript("Good morning, everyone!", heard("good morning everyone"))

    assert result.status == "aligned"
    assert result.coverage == 1.0
    assert result.transcript_source == "supplied"
    assert [(w.word, w.status, w.start, w.end) for w in result.words] == [
        ("Good", "aligned", 0.0, 0.4),
        ("morning,", "aligned", 0.5, 0.9),
        ("everyone!", "aligned", 1.0, 1.4),
    ]
    assert result.unmatched_recognized == []


def test_a_misheard_word_is_marked_substituted_with_what_was_heard():
    result = align_transcript("we chose the simplest one", heard("we chose the simple one"))

    assert result.status == "partial"
    word = result.words[3]
    assert (word.word, word.status, word.recognized_as) == ("simplest", "substituted", "simple")
    assert (word.start, word.end) == (1.5, 1.9)
    assert (result.aligned_count, result.substituted_count, result.unaligned_count) == (4, 1, 0)


def test_a_skipped_word_gets_no_times():
    result = align_transcript("good morning to everyone here", heard("good morning everyone here"))

    assert result.status == "partial"
    skipped = result.words[2]
    assert (skipped.word, skipped.status, skipped.start, skipped.end) == ("to", "unaligned", None, None)
    assert result.unaligned_count == 1
    assert result.words[3].start == 1.0  # later words keep their real times


def test_extra_spoken_words_are_listed_separately():
    result = align_transcript("good morning everyone", heard("good um morning everyone"))

    assert result.status == "aligned"
    assert [w.word for w in result.unmatched_recognized] == ["um"]
    assert result.unmatched_recognized[0].start == 0.5


def test_alignment_fails_when_nothing_matches():
    result = align_transcript("alpha beta gamma delta", heard("one two three"))

    assert result.status == "failed"
    assert result.coverage == 0
    assert all(w.status == "unaligned" and w.start is None for w in result.words)
    assert len(result.unmatched_recognized) == 3


def test_alignment_errors_when_there_is_nothing_to_align():
    with pytest.raises(SpeechError) as no_words:
        align_transcript("  ...  ", heard("hello"))
    assert no_words.value.code == "empty_transcript"

    with pytest.raises(SpeechError) as no_audio_words:
        align_transcript("hello there", [])
    assert no_audio_words.value.code == "no_word_timestamps"
    assert no_audio_words.value.status_code == 422


def test_normalize():
    assert normalize("Hello,") == "hello"
    assert normalize("It’s") == "it's"
    assert normalize("'quoted'") == "quoted"
    assert normalize("well-known") == "wellknown"
    assert normalize("—") == ""


def test_an_initial_prompt_is_passed_only_when_configured():
    plain, prompted = FakeModel([segment("hello", 0.1)]), FakeModel([segment("hello", 0.1)])

    transcriber_with(plain).transcribe(AUDIO, SR)
    transcriber_with(prompted, Settings(whisper_initial_prompt="Um, uh, like, you know.")).transcribe(AUDIO, SR)

    assert "initial_prompt" not in plain.calls[0]
    assert prompted.calls[0]["initial_prompt"] == "Um, uh, like, you know."
    assert prompted.calls[0]["word_timestamps"] is True
