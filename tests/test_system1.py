"""Real System 1 rules against the fixtures, through the gateway."""

from __future__ import annotations

import pytest

from contracts.models import MemoryItem, NextAction, Route
from fixtures.load import load_case, load_fixture
from gateway.route import handle
from system1.decide import DUPLICATE_RELEVANCE, decide

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


def _similar(source_case_id: str | None, relevance: float) -> MemoryItem:
    return MemoryItem(
        memory_id=f"mem-{source_case_id or 'none'}",
        kind="similar_case",
        summary=f"Case {source_case_id}: needs=water; route=welfare_distribution",
        relevance=relevance,
        source_case_id=source_case_id,
    )


def test_similar_case_from_another_case_duplicate_merges():
    """A retrieved case record (as memory.mubit maps a baansafe-case fact)
    for a different case at high relevance is a duplicate."""
    case = load_case("F01")
    case.memory_context = [_similar("case-earlier", 0.95)]
    outcome = decide(case)
    assert outcome.route is Route.duplicate_merge
    assert outcome.outcome == "fast_route"
    assert outcome.escalate is False
    assert "case-earlier" in outcome.reason
    assert outcome.needs == case.fields.needs
    # The full turn (handle replaces memory_context from the adapter) is
    # covered in tests/test_memory_write.py with a mocked control plane.


def test_similar_case_needs_source_and_relevance_to_merge():
    base = load_case("F01")
    below = base.model_copy(deep=True)
    below.memory_context = [_similar("case-earlier", DUPLICATE_RELEVANCE - 0.01)]
    assert decide(below).route is not Route.duplicate_merge

    unsourced = base.model_copy(deep=True)
    unsourced.memory_context = [_similar(None, 0.99)]
    assert decide(unsourced).route is not Route.duplicate_merge
