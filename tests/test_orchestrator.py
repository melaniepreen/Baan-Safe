"""Nemotron orchestrator: parse, fallback, prompt contents, key hygiene."""

import httpx
import pytest

from contracts.models import Outcome, Priority, Route, System
from fixtures.load import load_case
from system2 import orchestrator
from system2.orchestrator import orchestrate, use_completer

GOOD = {
    "choices": [
        {
            "message": {
                "content": (
                    "<think>chain</think> "
                    '{"priority": "P2", "route": "rescue_coordination", '
                    '"needs": ["rescue"], "requires_human": true, '
                    '"missing_evidence": ["water_depth"], '
                    '"next_question": "Is the water still rising?", '
                    '"confidence": 0.7, "rationale": "Cannot reach the house.", '
                    '"plan": ["Call district rescue.", "Confirm water depth.", '
                    '"Ask a neighbour."]}'
                )
            }
        }
    ]
}


def _reply(payload):
    return {"choices": [{"message": {"content": payload}}]}


def test_parse_reasoned_recommendation():
    with use_completer(lambda *a, **k: GOOD):
        outcome = orchestrate(load_case("F10"))
    assert outcome.system is System.system_2
    assert outcome.outcome == "reasoned_recommendation"
    assert outcome.priority is Priority.P2
    assert outcome.route is Route.rescue_coordination
    assert outcome.escalate is False
    assert "Plan:" in (outcome.reasoning or "")


def test_malformed_reply_falls_back():
    bad = _reply("not json at all")
    with use_completer(lambda *a, **k: bad):
        outcome = orchestrate(load_case("F10"))
    assert outcome.system is System.system_2
    assert outcome.outcome == "escalate"
    assert outcome.missing_evidence == ["system2_unavailable"]
    assert outcome.requires_human is True
    assert outcome.route is Route.supervisor_escalation


def test_timeout_falls_back():
    def boom(*a, **k):
        raise httpx.TimeoutException("slow")

    with use_completer(boom):
        outcome = orchestrate(load_case("F10"))
    assert outcome.missing_evidence == ["system2_unavailable"]
    assert "TimeoutException" in outcome.reason


def test_handoff_and_recommendation_reach_the_prompt():
    seen = {}

    def capture(messages, **kwargs):
        seen["messages"] = messages
        return GOOD

    handoff = Outcome(
        system=System.system_1,
        outcome="escalate",
        priority=Priority.P2,
        needs=[],
        route=Route.supervisor_escalation,
        confidence=0.2,
        reason="No extracted needs for the fast path.",
        reasoning=None,
        missing_evidence=[],
        next_question=None,
        requires_human=False,
        escalate=True,
        latency_ms=1,
    )
    rec = {"priority": "P4", "route": "information_only", "count": 2}
    with use_completer(capture):
        orchestrate(load_case("F10"), handoff=handoff, recommendation=rec)
    user = seen["messages"][1]["content"]
    assert "s1_handoff" in user
    assert "No extracted needs" in user
    assert "learned_recommendation" in user
    assert "information_only" in user
    assert seen["messages"][0]["role"] == "system"


def test_unknown_needs_are_dropped_with_a_human_flag():
    reply = _reply(
        '{"priority": "P2", "route": "medical_response", '
        '"needs": ["medical_assessment", "water"], "requires_human": false,'
        ' "missing_evidence": [], "next_question": null, "confidence": 0.6,'
        ' "rationale": "Weak and dizzy.", "plan": []}'
    )
    with use_completer(lambda *a, **k: reply):
        outcome = orchestrate(load_case("F10"))
    assert [need.value for need in outcome.needs] == ["water"]
    assert outcome.requires_human is True
    assert "dropped unknown needs: medical_assessment" in (outcome.reasoning or "")


def test_bad_priority_or_route_still_falls_back():
    reply = _reply(
        '{"priority": "P9", "route": "medical_response", "needs": ["water"],'
        ' "requires_human": false, "missing_evidence": [], "next_question": null,'
        ' "confidence": 0.5, "rationale": "x", "plan": []}'
    )
    with use_completer(lambda *a, **k: reply):
        outcome = orchestrate(load_case("F10"))
    assert outcome.missing_evidence == ["system2_unavailable"]


def test_orchestrate_never_reads_the_openrouter_key(monkeypatch):
    monkeypatch.delenv("MUBIT_BASE_URL", raising=False)
    monkeypatch.delenv("MUBIT_API_KEY", raising=False)
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-should_not_appear")
    with pytest.raises(RuntimeError, match="Mubit") as caught:
        orchestrate(load_case("F10"))
    assert "sk-should_not_appear" not in str(caught.value)


def test_aid_flags_force_requires_human():
    case = load_case("F16")
    reply = _reply(
        '{"priority": "P3", "route": "shelter_placement", "needs": ["shelter"],'
        ' "requires_human": false, "missing_evidence": [], "next_question": null,'
        ' "confidence": 0.6, "rationale": "Shelter is enough.", "plan": []}'
    )
    with use_completer(lambda *a, **k: reply):
        outcome = orchestrate(case)
    assert outcome.requires_human is True
