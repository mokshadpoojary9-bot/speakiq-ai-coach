"""Maps the words of a transcript onto recognised words that carry timestamps."""

import re
import unicodedata
from difflib import SequenceMatcher

from .schemas import AlignedWord, Alignment, RecognizedWord
from .transcriber import SpeechError

METHOD = (
    "Transcript-to-recognition alignment: the recording is transcribed with word timestamps, then the transcript "
    "words are matched in order to the recognised words (longest matching runs, ignoring case and punctuation). "
    "This is not phoneme-level acoustic forced alignment."
)

LIMITATIONS = [
    "A transcript word only gets a time if the recogniser heard a word at that position; words it misheard or missed are left without times.",
    "Times for 'substituted' words belong to the word that was recognised instead.",
    "Different spellings of the same speech, such as '3' and 'three', do not match.",
    "Timing accuracy is that of the recogniser's word timestamps, around a tenth of a second.",
]


def normalize(word: str) -> str:
    """Lowercase and drop punctuation so 'Hello,' matches 'hello'. Returns '' for pure punctuation."""
    folded = unicodedata.normalize("NFKC", word).casefold().replace("’", "'")
    return re.sub(r"[^\w']|_", "", folded).strip("'")


def align_transcript(
    transcript: str, recognized: list[RecognizedWord], *, source: str = "supplied"
) -> Alignment:
    """Align `transcript` to `recognized`. Raises SpeechError when there is nothing to align."""
    tokens = [(token, normalize(token)) for token in transcript.split()]
    tokens = [(token, key) for token, key in tokens if key]
    if not tokens:
        raise SpeechError("empty_transcript", "The transcript contains no words to align.", 422)
    if not recognized:
        raise SpeechError(
            "no_word_timestamps",
            "No words with timestamps were recognised in the recording, so the transcript cannot be aligned.",
            422,
        )

    heard = [normalize(word.word) for word in recognized]
    words = [AlignedWord(index=i, word=token, status="unaligned") for i, (token, _) in enumerate(tokens)]
    unmatched: list[RecognizedWord] = []

    def place(index: int, source_word: RecognizedWord, status: str) -> None:
        words[index] = words[index].model_copy(
            update={
                "status": status,
                "start": source_word.start,
                "end": source_word.end,
                "probability": source_word.probability,
                "recognized_as": source_word.word if status == "substituted" else None,
            }
        )

    matcher = SequenceMatcher(a=[key for _, key in tokens], b=heard, autojunk=False)
    for tag, a1, a2, b1, b2 in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(a2 - a1):
                place(a1 + offset, recognized[b1 + offset], "aligned")
        elif tag == "replace" and (a2 - a1) == (b2 - b1):
            # Same number of words on both sides: each transcript word was heard as something else.
            for offset in range(a2 - a1):
                place(a1 + offset, recognized[b1 + offset], "substituted")
        else:
            # Unequal replace, or words only the recogniser heard: there is no word-for-word mapping.
            unmatched.extend(recognized[b1:b2])

    aligned = sum(word.status == "aligned" for word in words)
    substituted = sum(word.status == "substituted" for word in words)
    return Alignment(
        status="aligned" if aligned == len(words) else "partial" if aligned else "failed",
        transcript_source=source,
        method=METHOD,
        word_count=len(words),
        aligned_count=aligned,
        substituted_count=substituted,
        unaligned_count=len(words) - aligned - substituted,
        coverage=round(aligned / len(words), 3),
        words=words,
        unmatched_recognized=unmatched,
        limitations=LIMITATIONS,
    )
