"""Real System 1 rules against the fixtures, through the gateway."""

from __future__ import annotations

import pytest

from contracts.models import NextAction
from fixtures.load import load_case, load_fixture
from gateway.route import handle
from system1.decide import decide

S1_IDS = [f"F{n:02d}" for n in range(1, 10)]


def test_real_system1_matches_expected_labels(monkeypatch):
    monkeypatch.setenv("S1_IMPL", "real")
    for fixture_id in S1_IDS:
        decision = handle(load_case(fixture_id), use_stubs=True)
        expected = load_fixture(fixture_id)["expected"]
        outcome = decision.source_outcomes[0]
        assert outcome.system.value == "system_1", fixture_id
        assert outcome.priority.value == expected["priority"], fixture_id
        assert outcome.route.value == expected["route"], fixture_id
        assert [need.value for need in outcome.needs] == expected["needs"], fixture_id
        assert outcome.requires_human == expected["requires_human"], fixture_id


def test_decide_escalates_on_system_2_triggers():
    outcome = decide(load_case("F10"))
    assert outcome.outcome == "escalate"
    assert outcome.escalate is True
    for name in ("medical", "vulnerable:oxygen_dependent", "need:rescue"):
        assert name in outcome.reason


def test_decide_escalates_below_min_confidence():
    case = load_case("F01")
    case.fields = case.fields.model_copy(update={"location_confidence": 0.75})
    outcome = decide(case)
    assert outcome.outcome == "escalate"
    assert outcome.escalate is True
    assert "0.75" in outcome.reason


def test_missing_people_count_asks_next_question():
    case = load_case("F01")
    case.fields = case.fields.model_copy(update={"people_count": None})
    outcome = decide(case)
    assert outcome.next_question == "How many people are with you?"
    assert outcome.missing_evidence == ["people_count"]

    decision = handle(case, use_stubs=False)
    assert decision.next_action is NextAction.ask_next_question
    assert decision.dispatches == []
