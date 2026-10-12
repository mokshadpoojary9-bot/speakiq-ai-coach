"""Download and load the configured transcription model once: `python -m app.speech.prefetch`."""

import sys

from ..config import get_settings
from .transcriber import FasterWhisperTranscriber, SpeechError


def main() -> int:
    settings = get_settings()
    print(f"Loading transcription model '{settings.whisper_model}' (downloads on first run)...")
    try:
        FasterWhisperTranscriber(settings)._get_model()
    except SpeechError as error:
        print(f"Failed [{error.code}]: {error.message}")
        return 1
    print("Model is ready.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
