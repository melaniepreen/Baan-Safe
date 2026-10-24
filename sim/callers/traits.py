"""Flood-caller behaviour traits.

LLM-played users tend to be cooperative, explicit, and homogeneous.
These traits are mixed per caller. They are ideas from MIMESIS
(arXiv 2610.09484), not a copy of that paper's pattern list or code.
"""

from __future__ import annotations

N_TURNS = 4

TRAIT_IDS: tuple[str, ...] = (
    "panicked_fragmented",
    "omits_location",
    "contradicts",
    "under_reports",
    "over_reports",
    "code_switches",
    "proxy",
    "poor_line",
    "distrusts_authorities",
    "needs_repeating",
    "elderly_hearing",
)

# Public phrases that match the hidden urgency. The script adds the phrase
# only when the caller is not under-reporting or over-reporting.
URGENCY_CUE: dict[str, str] = {
    "P1": "people cannot leave",
    "P2": "need help within hours",
    "P3": "drinking water for the house",
    "P4": "this is only a question",
}
