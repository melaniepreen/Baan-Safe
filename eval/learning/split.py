"""Held-out versus correction split.

The split key is TrainingEvent.group_id. Thai, English, and paraphrases of
one call share that id and stay on one side. Do not split on case_id or
language. Seeds are fixed in advance.
"""

from __future__ import annotations

import random
from dataclasses import dataclass


SEEDS: tuple[int, ...] = (17, 29, 41)


@dataclass(frozen=True)
class Split:
    seed: int
    correction: tuple[str, ...]
    held_out: tuple[str, ...]


def split_groups(group_ids: list[str] | tuple[str, ...], seed: int) -> Split:
    """Shuffle group_id values with this seed, then sort each side for the report.

    Duplicate ids collapse first, so one group cannot land on both sides.
    The shuffle starts from the sorted set, so the split depends on the set
    and the seed, not on the caller's order.
    """
    rng = random.Random(seed)
    order = sorted(set(group_ids))
    rng.shuffle(order)
    mid = len(order) // 2
    correction = tuple(sorted(order[:mid]))
    held_out = tuple(sorted(order[mid:]))
    return Split(seed=seed, correction=correction, held_out=held_out)
