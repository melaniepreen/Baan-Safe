"""Nemotron orchestrator. Owner: Melanie.

Nemotron is the System 2 orchestrator. It is not part of Mubit.
system2.hosting is openrouter via the Mubit gateway, so the model call goes
through `llm.client.complete`, which only talks to Mubit and refuses any
other host. There is no OpenRouter client and this module never reads
OPENROUTER_API_KEY.

`orchestrate(case, handoff, recommendation)` prompts Nemotron with the case,
the fired precheck triggers, memory summaries, resource availability, the
System 1 handoff when this turn cascaded, and the learned recommendation when
the overlay carries one. The reply is one JSON object that becomes a
`reasoned_recommendation` Outcome. A timeout, an HTTP error, an empty reply,
or a parse or enum failure falls back to a safe supervisor-escalation
Outcome. Config errors from `llm.complete` (missing URL, key, or host)
propagate unchanged; the key never appears in text.

`use_completer(fn)` swaps the model call for tests and the RL loop. The
default is `llm.client.complete`.

use_banyan_sapling is already true. The verifier does not run here. decide()
runs it on the outcome this function returns, and the gateway then builds the
Decision Router result.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from contextlib import contextmanager
from time import perf_counter
from typing import Any, Iterator

import httpx

from config.settings import load_yaml, require_decision, unset_decisions
from contracts.models import CaseState, Need, Outcome, Priority, Route, System
from gateway.chooser import system_2_triggers
from llm.client import complete as _llm_complete

_DECISIONS = [
    "system2.orchestrator_model",
    "system2.hosting",
    "system2.use_banyan_sapling",
    "system2.max_latency_ms",
]

Completer = Callable[..., dict[str, Any]]
_completer: Completer = _llm_complete

# Nemotron spends its whole completion budget on <think> without this.
_REASONING: dict | None = {"enabled": False}
_MAX_TOKENS = 700


@contextmanager
def use_completer(fn: Completer) -> Iterator[None]:
    """Install a process-level completer. Tests and the RL loop use this."""
    global _completer
    previous = _completer
    _completer = fn
    try:
        yield
    finally:
        _completer = previous


_AID_FLAGS = {"safeguarding", "aid_exception", "aid_eligibility", "aid_denial"}
_THINK = re.compile(r"<think>.*?</think>", re.DOTALL)
_OBJECT = re.compile(r"\{.*\}", re.DOTALL)

REPLY_KEYS = (
    "priority",
    "route",
    "needs",
    "requires_human",
    "missing_evidence",
    "next_question",
    "confidence",
    "rationale",
    "plan",
)


def orchestrate(
    case: CaseState,
    handoff: Outcome | None = None,
    recommendation: dict | None = None,
) -> Outcome:
    missing = unset_decisions(_DECISIONS)
    if missing:
        raise NotImplementedError(
            "not implemented yet — owner: Melanie. "
            "Unset TODO_HUMAN: " + ", ".join(missing) + "."
        )
    model = require_decision("system2.orchestrator_model")
    timeout = float(require_decision("system2.max_latency_ms")) / 1000
    started = perf_counter()
    latency_ms = lambda: int((perf_counter() - started) * 1000)  # noqa: E731
    try:
        reply = _completer(
            _messages(case, handoff, recommendation),
            model=model,
            max_tokens=_MAX_TOKENS,
            timeout=timeout,
            temperature=0,
            seed=7,
            reasoning=_REASONING,
        )
        outcome = _outcome_from_reply(reply, latency_ms)
    except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
        return _unavailable(exc, latency_ms())
    return _post_rules(case, outcome)


def _unavailable(exc: Exception, latency_ms: int) -> Outcome:
    return Outcome(
        system=System.system_2,
        outcome="escalate",
        priority=Priority.P2,
        needs=[],
        route=Route.supervisor_escalation,
        confidence=0.0,
        reason=f"System 2 unavailable: {type(exc).__name__}.",
        reasoning=None,
        missing_evidence=["system2_unavailable"],
        next_question=None,
        requires_human=True,
        escalate=False,
        latency_ms=latency_ms,
    )


def _post_rules(case: CaseState, outcome: Outcome) -> Outcome:
    flags = set(case.policy_flags)
    aid = outcome.route is Route.aid_caseworker or Need.aid_payment in (
        set(outcome.needs) | set(case.fields.needs)
    )
    if "safeguarding" in flags or aid or flags & _AID_FLAGS:
        if not outcome.requires_human:
            return outcome.model_copy(update={"requires_human": True})
    return outcome


def _outcome_from_reply(reply: dict[str, Any], latency_ms) -> Outcome:
    content = (
        (reply.get("choices") or [{}])[0].get("message", {}).get("content") or ""
    )
    text = _THINK.sub("", content)
    match = _OBJECT.search(text)
    if not match:
        raise ValueError("System 2 reply carried no JSON object")
    data = json.loads(match.group(0))
    priority = Priority(data["priority"])
    route = Route(data["route"])
    known = {need.value for need in Need}
    raw_needs = [str(need) for need in data.get("needs") or []]
    dropped = [need for need in raw_needs if need not in known]
    needs = [Need(need) for need in raw_needs if need in known]
    plan = [str(item) for item in data.get("plan") or []][:3]
    reasoning = str(data.get("rationale") or "")
    if plan:
        steps = " ".join(f"{index}) {item}" for index, item in enumerate(plan, 1))
        reasoning = (reasoning + " Plan: " + steps).strip()
    if dropped:
        reasoning = (reasoning + f" dropped unknown needs: {', '.join(dropped)}").strip()
    return Outcome(
        system=System.system_2,
        outcome="reasoned_recommendation",
        priority=priority,
        needs=needs,
        route=route,
        confidence=float(data.get("confidence") or 0.0),
        reason=str(data.get("rationale") or "Nemotron reasoned over the case.")[:400]
        or "Nemotron reasoned over the case.",
        reasoning=reasoning or None,
        missing_evidence=[str(item) for item in data.get("missing_evidence") or []],
        next_question=data.get("next_question") or None,
        requires_human=bool(data.get("requires_human")) or bool(dropped),
        escalate=False,
        latency_ms=latency_ms(),
    )


def _messages(
    case: CaseState,
    handoff: Outcome | None,
    recommendation: dict | None,
) -> list[dict[str, str]]:
    priorities = load_yaml("priorities.yaml").get("priorities") or {}
    priority_lines = "; ".join(
        f"{name}: {body.get('definition', '')}" for name, body in priorities.items()
    )
    system = (
        "You are Nemotron, the System 2 orchestrator for a flood call-triage "
        "line. The caller and case are synthetic. "
        f"Priority: {priority_lines} "
        "Route: rescue_coordination, medical_response, welfare_distribution, "
        "shelter_placement, aid_caseworker, information_only, duplicate_merge, "
        "supervisor_escalation. "
        "Needs: rescue, medical, water, food, shelter, evacuation, power, "
        "information, aid_payment. "
        "Humans keep authority over denials, safeguarding, and irreversible "
        "actions; set requires_human for those. Never state a baht amount. "
        "priority must be exactly one of P1, P2, P3, P4. route must be exactly "
        "one of the Route values above. Every item in needs must be exactly "
        "one of the Needs values above; do not invent need names. "
        "Reply with one JSON object only, keys: "
        + ", ".join(REPLY_KEYS)
        + ". plan is at most 3 strings."
    )
    payload = {
        "case_id": case.case_id,
        "transcript": [
            {"speaker": turn.speaker, "text": turn.text}
            for turn in case.transcript
        ],
        "fields": case.fields.model_dump(mode="json"),
        "policy_flags": list(case.policy_flags),
        "fired_triggers": system_2_triggers(case),
        "memory": [item.summary for item in case.memory_context],
        "resources": _resource_summary(),
        "s1_handoff": (
            {
                "priority": handoff.priority.value,
                "route": handoff.route.value,
                "confidence": handoff.confidence,
                "reason": handoff.reason,
            }
            if handoff is not None
            else None
        ),
        "learned_recommendation": recommendation,
    }
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def _resource_summary() -> dict[str, int]:
    from mocks.loader import load_resources

    snapshot = load_resources()
    summary: dict[str, int] = {}
    for kind in ("boats", "ambulances", "shelters", "welfare_points"):
        units = getattr(snapshot, kind)
        summary[kind] = sum(
            (unit.available or 0)
            for unit in units
            if unit.status in {"available", "open"}
        )
    return summary
