"""Authored learning-loop themes. Truth is settled; do not change it here.

Each theme has variants that differ only in district or numbers, a full
transcript, and truth (priority, routes with the first canonical,
requires_human, needs). The extraction path of every theme is asserted in
tests and in `eval.rl.run`.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from contracts.models import CaseState, ExtractedFields, TranscriptTurn

RECEIVED_AT = datetime(2026, 10, 24, tzinfo=timezone.utc)


@dataclass(frozen=True)
class Truth:
    priority: str
    routes: tuple[str, ...]
    requires_human: bool
    needs: tuple[str, ...]


@dataclass(frozen=True)
class Variant:
    case_id: str
    caller_texts: tuple[str, ...]


@dataclass(frozen=True)
class Theme:
    theme_id: str
    intent: str
    truth: Truth
    variants: tuple[Variant, ...]


THEMES: tuple[Theme, ...] = (
    Theme(
        "road-info",
        "cascade -> graduates",
        Truth("P4", ("information_only",), False, ("information",)),
        (
            Variant(
                "RL-ROAD-1",
                (
                    "Hello, we live in Mueang Nan District. "
                    "The main road to the market looks closed. "
                    "Which way can we drive into town?",
                ),
            ),
            Variant(
                "RL-ROAD-2",
                (
                    "Hello, we live in Mueang Phrae District. "
                    "The main road to the market looks closed. "
                    "Which way can we drive into town?",
                ),
            ),
            Variant(
                "RL-ROAD-3",
                (
                    "Hello, we live in Mueang Lampang District. "
                    "The main road to the market looks closed. "
                    "Which way can we drive into town?",
                ),
            ),
        ),
    ),
    Theme(
        "cold-hall",
        "cascade -> graduates",
        Truth("P3", ("welfare_distribution", "shelter_placement"), False, ("shelter",)),
        (
            Variant(
                "RL-COLD-1",
                (
                    "We are at the temple hall in Mueang Phayao District. "
                    "There are five of us. "
                    "We have no blankets and the night is cold.",
                ),
            ),
            Variant(
                "RL-COLD-2",
                (
                    "We are at the temple hall in Mueang Nan District. "
                    "There are four of us. "
                    "We have no blankets and the night is cold.",
                ),
            ),
        ),
    ),
    Theme(
        "quiet-grandmother",
        "cascade -> complex -> recommendation",
        Truth("P2", ("rescue_coordination", "supervisor_escalation"), True, ("rescue",)),
        (
            Variant(
                "RL-GRAN-1",
                (
                    "My grandmother lives alone in Mueang Phrae District. "
                    "She has not answered her phone since this morning "
                    "and the street is under water.",
                ),
            ),
            Variant(
                "RL-GRAN-2",
                (
                    "My grandmother lives alone in Mueang Lampang District. "
                    "She has not answered her phone since this morning "
                    "and the street is under water.",
                ),
            ),
        ),
    ),
    Theme(
        "upstairs-water",
        "cascade -> P1 -> recommendation",
        Truth("P1", ("rescue_coordination",), True, ("rescue",)),
        (
            Variant(
                "RL-UP-1",
                (
                    "The water has come up to the second floor in Mueang Nan District. "
                    "Three of us are upstairs with my father.",
                ),
            ),
            Variant(
                "RL-UP-2",
                (
                    "The water has come up to the second floor in Mueang Phayao District. "
                    "Three of us are upstairs with my father.",
                ),
            ),
        ),
    ),
    Theme(
        "weak-grandfather-water",
        "S1 confident -> under-triage -> demote",
        Truth("P2", ("medical_response",), False, ("medical", "water")),
        (
            Variant(
                "RL-WEAK-1",
                (
                    "We need drinking water in Mueang Lampang District. "
                    "There are three of us. "
                    "My grandfather has not had anything to drink since yesterday "
                    "and he is very weak and dizzy.",
                ),
            ),
            Variant(
                "RL-WEAK-2",
                (
                    "We need drinking water in Mueang Phrae District. "
                    "There are three of us. "
                    "My grandfather has not had anything to drink since yesterday "
                    "and he is very weak and dizzy.",
                ),
            ),
        ),
    ),
    Theme(
        "rice",
        "S1 confident, stays S1 (control)",
        Truth("P3", ("welfare_distribution",), False, ("food",)),
        (
            Variant(
                "RL-RICE-1",
                (
                    "Our rice is finished. We are four people in Mueang Phayao District. "
                    "Can someone bring food today?",
                ),
            ),
            Variant(
                "RL-RICE-2",
                (
                    "Our rice is finished. We are four people in Mueang Nan District. "
                    "Can someone bring food today?",
                ),
            ),
        ),
    ),
    Theme(
        "aid-list",
        "direct S2 + Sapling, never graduates",
        Truth("P3", ("aid_caseworker",), True, ("aid_payment",)),
        (
            Variant(
                "RL-AID-1",
                (
                    "We are not on the household list for the flood payment "
                    "in Mueang Nan District. Two of us. Can we get an exception?",
                ),
            ),
            Variant(
                "RL-AID-2",
                (
                    "We are not on the household list for the flood payment "
                    "in Mueang Phrae District. Two of us. Can we get an exception?",
                ),
            ),
        ),
    ),
    Theme(
        "fine-but-door",
        "direct S2 (conflicting evidence)",
        Truth("P1", ("rescue_coordination",), True, ("rescue",)),
        (
            Variant(
                "RL-DOOR-1",
                (
                    "We're fine, really, no need to send anyone. "
                    "Water is at the door. We are in Mueang Phrae District. "
                    "Just me and my son.",
                ),
            ),
            Variant(
                "RL-DOOR-2",
                (
                    "We're fine, really, no need to send anyone. "
                    "Water is at the door. We are in Mueang Lampang District. "
                    "Just me and my son.",
                ),
            ),
        ),
    ),
)


def variant_case(theme: Theme, variant: Variant) -> CaseState:
    transcript: list[TranscriptTurn] = []
    for index, text in enumerate(variant.caller_texts):
        transcript.append(
            TranscriptTurn(t_ms=index * 2000, speaker="caller", text=text)
        )
        transcript.append(
            TranscriptTurn(
                t_ms=index * 2000 + 1000,
                speaker="operator",
                text="Please hold the line.",
            )
        )
    return CaseState(
        case_id=variant.case_id,
        caller_id_hash=f"synthetic:{variant.case_id}",
        transcript=transcript,
        fields=ExtractedFields(),
        received_at=RECEIVED_AT,
    )


def lookup_by_text() -> dict[str, Truth]:
    """Normalized caller text -> truth, for the fake completer."""
    table: dict[str, Truth] = {}
    for theme in THEMES:
        for variant in theme.variants:
            for text in variant.caller_texts:
                table[" ".join(text.lower().split())] = theme.truth
    return table
