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
    assert case.fields.location == "Song District, Phrae Province"
    assert case.fields.location_confidence == 0.85


def test_danger_regex_families():
    fields, _ = extract(
        _turns(("caller", "It is reaching the doorway. Water is coming into the room.")),
        districts=DISTRICTS,
    )
    assert "rising_water" in fields.danger


def test_danger_negative():
    fields, _ = extract(
        _turns(("caller", "The door is open and the floor is dry. We need food.")),
        districts=DISTRICTS,
    )
    assert fields.danger == []


def test_immobile_regex_family():
    fields, _ = extract(
        _turns(("caller", "My neighbour is unable to stand. She cannot get out of bed.")),
        districts=DISTRICTS,
    )
    assert "immobile" in fields.vulnerable


def test_immobile_negative():
    fields, _ = extract(
        _turns(("caller", "Nobody is immobile. We can all walk to the road.")),
        districts=DISTRICTS,
    )
    assert "immobile" not in fields.vulnerable


def test_child_unaccompanied_flags_safeguarding():
    _, flags = extract(
        _turns(("caller", "A child turned up at our gate without a parent.")),
        districts=DISTRICTS,
    )
    assert "safeguarding" in flags


def test_child_with_adult_no_safeguarding():
    _, flags = extract(
        _turns(("caller", "My son is here with me. We need food.")),
        districts=DISTRICTS,
    )
    assert "safeguarding" not in flags


def test_aid_phrases_are_negation_exempt():
    fields, flags = extract(
        _turns(("caller", "They told us we cannot get the payment.")),
        districts=DISTRICTS,
    )
    assert Need.aid_payment in fields.needs
    assert "aid_exception" in flags


def test_aid_negative():
    fields, flags = extract(
        _turns(("caller", "I already said the food arrived. We are fine.")),
        districts=DISTRICTS,
    )
    assert Need.aid_payment not in fields.needs
    assert "aid_exception" not in flags


def test_minimising_with_vulnerable_flags_conflict():
    _, flags = extract(
        _turns(("caller", "It's nothing, do not make a fuss. My mother is elderly.")),
        districts=DISTRICTS,
    )
    assert "conflicting_evidence" in flags


def test_minimising_without_harm_no_flag():
    _, flags = extract(
        _turns(("caller", "It's fine. We only want to know when the power returns.")),
        districts=DISTRICTS,
    )
    assert "conflicting_evidence" not in flags


def test_rescue_inferred_from_door_water_and_elderly():
    fields, _ = extract(
        _turns(("caller", "The water is at the door. My grandmother is inside.")),
        districts=DISTRICTS,
    )
    assert Need.rescue in fields.needs


def test_evacuation_suppresses_rescue_without_vulnerable():
    fields, _ = extract(
        _turns(("caller", "The water is up to the steps. We should leave for the shelter.")),
        districts=DISTRICTS,
    )
    assert Need.evacuation in fields.needs
    assert Need.rescue not in fields.needs


def test_people_count_new_phrasings():
    fields, _ = extract(
        _turns(
            ("caller", "We are a family of six upstairs."),
            ("caller", "There are six of us waiting."),
        ),
        districts=DISTRICTS,
    )
    assert fields.people_count == 6

    fields, _ = extract(
        _turns(("caller", "It is me and my sister in the house.")),
        districts=DISTRICTS,
    )
    assert fields.people_count == 2

    fields, _ = extract(
        _turns(
            ("operator", "How many people?"),
            ("caller", "Four."),
        ),
        districts=DISTRICTS,
    )
    assert fields.people_count == 4


def test_medical_new_keywords_and_negation():
    fields, _ = extract(
        _turns(("caller", "He is unconscious and his breathing is slow.")),
        districts=DISTRICTS,
    )
    assert Need.medical in fields.needs
    assert fields.medical is True

    fields, _ = extract(
        _turns(("caller", "No injury. Nobody is sick. We need food.")),
        districts=DISTRICTS,
    )
    assert fields.medical is False
    assert Need.medical not in fields.needs
