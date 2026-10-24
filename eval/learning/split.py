"""Held-out versus correction split.

Assignment is by call group. Thai and English variants of one group always
land on the same side. Seeds are fixed in advance.
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
    """Shuffle group ids with this seed, then sort each side for the report.

    The shuffle starts from sorted ids, so the split depends on the set and
    the seed, not on the caller's order.
    """
    rng = random.Random(seed)
    order = sorted(group_ids)
    rng.shuffle(order)
    mid = len(order) // 2
    correction = tuple(sorted(order[:mid]))
    held_out = tuple(sorted(order[mid:]))
    return Split(seed=seed, correction=correction, held_out=held_out)
