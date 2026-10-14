"""Transcript verification workflow.

Transcripts start as unedited speech-recognition output and stay labelled unverified until a
person who has listened to the audio records a review here. Nothing in this module can mark a
transcript verified without a named reviewer and an explicit statement that they listened.
"""

import json
import os
import subprocess
import sys
import textwrap
from collections.abc import Callable
from datetime import date
from pathlib import Path

from .schema import SourceRecording, TranscriptReview


class ReviewError(ValueError):
    pass


def load_registry(registry_path: Path) -> dict:
    return json.loads(registry_path.read_text(encoding="utf-8"))


def review_status(registry_path: Path) -> list[SourceRecording]:
    return [SourceRecording.model_validate(item) for item in load_registry(registry_path)["sources"]]


def review_sheet(registry_path: Path) -> str:
    """A plain-text checklist a reviewer can work through while listening."""
    lines = ["TRANSCRIPT REVIEW SHEET", "Listen to each file and compare it with the text. Do not rely on the text alone.", ""]
    for source in review_status(registry_path):
        lines += [
            f"Source:     {source.source_id}",
            f"Audio file: {registry_path.parent / source.audio_path}",
            f"Status:     {source.transcript_review.status} ({source.transcript_provenance})",
            f"Described as: {source.description}" + ("" if source.description_verified else "  [description not verified]"),
            "Current transcript:",
            f"  {source.transcript}",
            "",
        ]
    lines.append("Record a review with:  python -m app.dataset transcripts verify SOURCE_ID --reviewer NAME --listened [--text-file FILE]")
    return "\n".join(lines)


def verify_transcript(
    registry_path: Path,
    source_id: str,
    *,
    reviewer: str,
    listened: bool,
    corrected_text: str | None = None,
    notes: str = "",
    today: date | None = None,
) -> SourceRecording:
    """Record that `reviewer` listened to the audio and confirmed or corrected the transcript."""
    if not reviewer.strip():
        raise ReviewError("A reviewer name is required.")
    if not listened:
        raise ReviewError("Verification requires confirming that the reviewer listened to the audio (--listened).")
    if corrected_text is not None and not corrected_text.strip():
        raise ReviewError("The corrected transcript is empty.")

    registry = load_registry(registry_path)
    for item in registry["sources"]:
        if item["source_id"] == source_id:
            break
    else:
        known = ", ".join(s["source_id"] for s in registry["sources"])
        raise ReviewError(f"Unknown source '{source_id}'. Known sources: {known}")

    source = SourceRecording.model_validate(item)
    previous = source.transcript_review
    machine_text = previous.asr_transcript or source.transcript
    new_text = corrected_text.strip() if corrected_text is not None else source.transcript
    item["transcript"] = new_text
    item["transcript_provenance"] = "manual_verified"
    item["transcript_review"] = TranscriptReview(
        status="verified",
        reviewer=reviewer.strip(),
        reviewed_on=(today or date.today()).isoformat(),
        method="Listened to the audio and compared it with the transcript.",
        asr_transcript=machine_text,
        changed=new_text != machine_text,
        notes=notes.strip(),
    ).model_dump()
    verified = SourceRecording.model_validate(item)
    registry_path.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n")
    return verified


def play_audio(path: Path) -> None:
    """Open the clip in the computer's default audio player, without waiting for it to finish."""
    if sys.platform == "win32":
        os.startfile(path)  # type: ignore[attr-defined]
    elif sys.platform == "darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])


YES = {"y", "yes"}
MENU = "[c] the text is correct  [e] edit it  [p] play again  [s] skip  [q] quit"


def interactive_review(
    registry_path: Path,
    *,
    reviewer: str,
    ask: Callable[[str], str] = input,
    say: Callable[[str], None] = print,
    play: Callable[[Path], None] | None = play_audio,
    include_verified: bool = False,
    today: date | None = None,
) -> dict[str, int]:
    """Walk a person through each unverified transcript: play the clip, show the text, record the decision.

    A transcript is only recorded as verified after the reviewer explicitly confirms they listened to
    the whole clip. Skipping or quitting records nothing.
    """
    if not reviewer.strip():
        raise ReviewError("A reviewer name is required.")
    sources = [s for s in review_status(registry_path) if include_verified or s.transcript_review.status != "verified"]
    counts = {"confirmed": 0, "corrected": 0, "skipped": 0}
    if not sources:
        say("Every transcript has already been reviewed.")
        return counts

    def listened() -> bool:
        return ask("Did you listen to the whole clip, and is this exactly what is said? (yes/no) ").strip().lower() in YES

    for number, source in enumerate(sources, start=1):
        audio = registry_path.parent / source.audio_path
        say("")
        say(f"[{number}/{len(sources)}] {source.source_id}   ({audio})")
        say(f"Described as: {source.description}")
        say("Transcript:")
        say(textwrap.fill(source.transcript, width=88, initial_indent="  ", subsequent_indent="  "))
        if play:
            play(audio)
        while True:
            choice = ask(f"{MENU}\n> ").strip().lower()
            if choice == "p" and play:
                play(audio)
            elif choice == "c":
                if listened():
                    verify_transcript(registry_path, source.source_id, reviewer=reviewer, listened=True, today=today)
                    counts["confirmed"] += 1
                    say("Recorded as verified.")
                    break
                say("Not recorded. Play the clip and listen to all of it first.")
            elif choice == "e":
                text = ask("Type the corrected transcript on one line (leave empty to cancel):\n> ").strip()
                if not text:
                    say("Cancelled; nothing recorded.")
                    continue
                if listened():
                    verify_transcript(
                        registry_path, source.source_id, reviewer=reviewer, listened=True, corrected_text=text, today=today
                    )
                    counts["corrected"] += 1
                    say("Recorded the corrected transcript as verified. The original machine transcript is kept.")
                    break
                say("Not recorded. Play the clip and listen to all of it first.")
            elif choice == "s":
                counts["skipped"] += 1
                break
            elif choice == "q":
                counts["skipped"] += len(sources) - number + 1
                return counts
            else:
                say("Please type c, e, p, s or q.")
    return counts
