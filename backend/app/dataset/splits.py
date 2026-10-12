"""Reproducible train/validation/test splits that never put one speaker in two splits."""

import random

SPLIT_NAMES = ("train", "validation", "test")


def split_speakers(speaker_ids: list[str], seed: int) -> dict[str, list[str]]:
    """Assign whole speakers to splits, deterministically for a given seed.

    With three or more speakers each split gets at least one, and the rest go to train. With
    fewer than three, held-out splits cannot be formed without leakage, so everything is train.
    """
    speakers = sorted(set(speaker_ids))
    random.Random(seed).shuffle(speakers)
    splits: dict[str, list[str]] = {name: [] for name in SPLIT_NAMES}
    if len(speakers) < 3:
        splits["train"] = sorted(speakers)
        return splits
    splits["test"] = [speakers[0]]
    splits["validation"] = [speakers[1]]
    splits["train"] = sorted(speakers[2:])
    return splits
