"""Cascade routing: an S1 escalate continues to S2 in the same turn."""

import pytest

from contracts.models import CaseState, ExtractedFields, Outcome, Priority, Route, System
from eval.rl.themes import THEMES, variant_case
from fixtures.load import load_case
from gateway.route import handle
from system2 import orchestrator

S2_REPLY = {
    "choices": [
        {
            "message": {
                "content": (
                    '{"priority": "P2", "route": "rescue_coordination", '
                    '"needs": ["rescue"], "requires_human": true, '
                    '"missing_evidence": [], "next_question": null, '
                    '"confidence": 0.8, "rationale": "Unsafe to wait.", '
                    '"plan": ["Send a boat."]}'
                )
            }
        }
    ]
}


def _fake(messages, **_kwargs):
    return S2_REPLY


def _theme(theme_id, index=0):
    theme = next(item for item in THEMES if item.theme_id == theme_id)
    return variant_case(theme, theme.variants[index])


def test_confident_s1_stays_single():
    decision = handle(load_case("F01"), use_stubs=True)
    assert [o.system.value for o in decision.source_outcomes] == ["system_1"]


def test_no_needs_cascades_and_orders_deciding_first():
    with orchestrator.use_completer(_fake):
        decision = handle(_theme("road-info"), use_stubs=False)
    systems = [o.system.value for o in decision.source_outcomes]
    assert systems == ["system_2", "system_1"]
    assert decision.final_route.value == "rescue_coordination"
    assert any(
        note.startswith("cascade: system_1 handed off to system_2")
        for note in decision.policy_notes
    )


def test_hard_trigger_goes_to_system_2_only():
    with orchestrator.use_completer(_fake):
        decision = handle(_theme("fine-but-door"), use_stubs=False)
    assert [o.system.value for o in decision.source_outcomes] == ["system_2"]


def test_exclusive_mode_does_not_cascade(monkeypatch):
    monkeypatch.setattr("gateway.route._mode", lambda: "exclusive")
    with orchestrator.use_completer(_fake):
        decision = handle(_theme("road-info"), use_stubs=False)
    assert [o.system.value for o in decision.source_outcomes] == ["system_1"]
    assert decision.source_outcomes[0].escalate is True


def test_fixture_stub_fallback_never_cascades():
    case = load_case("F01")
    case = case.model_copy(update={"case_id": "case-no-stub"})
    decision = handle(case, use_stubs=True)
    assert [o.system.value for o in decision.source_outcomes] == ["system_1"]
    assert decision.source_outcomes[0].missing_evidence == ["fixture_stub"]


def test_stub_cascade_uses_the_s2_stub(monkeypatch):
    s1 = Outcome(
        system=System.system_1,
        outcome="escalate",
        priority=Priority.P2,
        needs=[],
        route=Route.supervisor_escalation,
        confidence=0.0,
        reason="Not confident.",
        reasoning=None,
        missing_evidence=[],
        next_question=None,
        requires_human=False,
        escalate=True,
        latency_ms=1,
    )
    s2 = s1.model_copy(
        update={
            "system": System.system_2,
            "outcome": "reasoned_recommendation",
            "escalate": False,
            "reason": "S2 stub.",
        }
    )
    monkeypatch.setattr("gateway.route.has_s1_stub", lambda _id: True)
    monkeypatch.setattr("gateway.route.load_s1_stub", lambda _id: s1)
    monkeypatch.setattr("gateway.route.has_s2_stub", lambda _id: True)
    monkeypatch.setattr("gateway.route.load_s2_stub", lambda _id: s2)
    decision = handle(load_case("F01"), use_stubs=True)
    assert [o.system.value for o in decision.source_outcomes] == [
        "system_2",
        "system_1",
    ]
    assert decision.source_outcomes[0].reason == "S2 stub."
