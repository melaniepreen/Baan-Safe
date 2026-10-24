"""Keyword extraction: caller-only, negation, district match, flag hints."""

from __future__ import annotations

from contracts.models import (
    CaseState,
    ExtractedFields,
    Need,
    TranscriptTurn,
)
from datetime import datetime, timezone
from fixtures.load import load_case
from gateway.route import handle
from system1.extract import extract

DISTRICTS = ["Mae Mo District", "Song District", "Den Chai District"]


def _turns(*lines: tuple[str, str]) -> list[TranscriptTurn]:
    return [
        TranscriptTurn(t_ms=i * 1000, speaker=speaker, text=text)
        for i, (speaker, text) in enumerate(lines)
    ]


def _case(transcript: list[TranscriptTurn], case_id: str = "extract-test") -> CaseState:
    return CaseState(
        case_id=case_id,
        caller_id_hash="synthetic:extract-test",
        transcript=transcript,
        fields=ExtractedFields(),
        received_at=datetime(2026, 10, 24, tzinfo=timezone.utc),
    )


def test_f01_transcript_extracts_water_people_and_district():
    case = load_case("F01")
    fields, flags = extract(case.transcript, districts=DISTRICTS)
    assert fields.needs == [Need.water]
    assert fields.people_count == 4
    assert fields.location == "Mae Mo District"
    assert fields.location_confidence == 0.85
    assert fields.medical is False
    assert fields.danger == []
    assert flags == []


def test_negated_medical_is_not_extracted():
    fields, flags = extract(
        _turns(("caller", "No, nobody is hurt. We need drinking water.")),
        districts=DISTRICTS,
    )
    assert fields.medical is False
    assert Need.medical not in fields.needs
    assert Need.water in fields.needs


def test_landmark_only_leaves_location_empty():
    fields, _ = extract(
        _turns(("caller", "We are near the blue temple.")),
        districts=DISTRICTS,
    )
    assert fields.location is None
    assert fields.location_confidence is None


def test_minimising_plus_danger_flags_conflicting_evidence():
    fields, flags = extract(
        _turns(("caller", "We're fine, it's fine. Water is at the door but nothing serious.")),
        districts=DISTRICTS,
    )
    assert "rising_water" in fields.danger
    assert "conflicting_evidence" in flags


def test_child_alone_flags_safeguarding():
    _, flags = extract(
        _turns(("caller", "I am a kid and I am alone. I can't find my mum.")),
        districts=DISTRICTS,
    )
    assert "safeguarding" in flags


def test_operator_turns_are_ignored():
    fields, _ = extract(
        _turns(
            ("operator", "Is anyone on oxygen or trapped on the roof?"),
            ("caller", "No. We just need drinking water."),
        ),
        districts=DISTRICTS,
    )
    assert fields.medical is False
    assert "oxygen_dependent" not in fields.vulnerable
    assert Need.rescue not in fields.needs
    assert Need.medical not in fields.needs


def test_gateway_reextracts_on_a_later_turn():
    case = _case(
        _turns(
            ("caller", "We need drinking water."),
            ("operator", "Which district?"),
        )
    )
    decision = handle(case, use_stubs=True)
    assert "keyword_extraction" in case.policy_flags
    assert case.fields.needs == [Need.water]

    case.transcript.append(
        TranscriptTurn(t_ms=5000, speaker="caller", text="Song District, four people.")
    )
    handle(case, use_stubs=True)
    assert case.fields.people_count == 4
    assert case.fields.location == "Song District"
    assert case.fields.location_confidence == 0.85
