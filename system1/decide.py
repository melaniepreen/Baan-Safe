"""System 1 entry point. Owner: Moly.

Deterministic rules over the extracted fields. Escalation triggers are the
same field precheck the gateway reads (`config/escalation.yaml`), re-checked
here as defence in depth. `system1.extraction_model` stays TODO_HUMAN: the
decided `system1.extraction_method` is `rules-only`, so no model is read.
"""

from __future__ import annotations

from time import perf_counter
from typing import TYPE_CHECKING

from config.settings import load_yaml
from contracts.models import CaseState, Need, Outcome, Priority, Route, System
from gateway.chooser import system_2_triggers

if TYPE_CHECKING:
    from gateway.overlay import Overlay

DUPLICATE_RELEVANCE = 0.9

NEEDS_TABLE: dict[Need, tuple[Route, Priority]] = {
    Need.water: (Route.welfare_distribution, Priority.P3),
    Need.food: (Route.welfare_distribution, Priority.P3),
    Need.shelter: (Route.shelter_placement, Priority.P3),
    Need.evacuation: (Route.shelter_placement, Priority.P2),
    Need.power: (Route.information_only, Priority.P3),
    Need.information: (Route.information_only, Priority.P4),
}

_PRIORITY_ORDER = {
    Priority.P1: 0,
    Priority.P2: 1,
    Priority.P3: 2,
    Priority.P4: 3,
}


def _escalate(reason: str, confidence: float = 0.0, latency_ms: int = 0) -> Outcome:
    return Outcome(
        system=System.system_1,
        outcome="escalate",
        priority=Priority.P2,
        needs=[],
        route=Route.supervisor_escalation,
        confidence=confidence,
        reason=reason,
        reasoning=None,
        missing_evidence=[],
        next_question=None,
        requires_human=False,
        escalate=True,
        latency_ms=latency_ms,
    )


def decide(case: CaseState, overlay: Overlay | None = None) -> Outcome:
    started = perf_counter()
    latency_ms = lambda: int((perf_counter() - started) * 1000)  # noqa: E731
    fields = case.fields

    if overlay is not None:
        from gateway.overlay import coarse_signature, narrow_signature

        coarse = coarse_signature(case)
        if coarse in overlay.demoted:
            return _escalate(
                "Learned demotion: this pattern under-triaged on the fast path.",
                latency_ms=latency_ms(),
            )
        narrow = narrow_signature(case)
    else:
        narrow = None

    triggers = system_2_triggers(case)
    if triggers:
        return _escalate(
            "System 2 triggers fired: " + ", ".join(triggers) + ".",
            latency_ms=latency_ms(),
        )

    for item in case.memory_context:
        if (
            item.kind == "similar_case"
            and item.source_case_id
            and item.relevance >= DUPLICATE_RELEVANCE
        ):
            route, priority = _needs_route(fields.needs)
            return Outcome(
                system=System.system_1,
                outcome="fast_route",
                priority=priority or Priority.P3,
                needs=fields.needs,
                route=Route.duplicate_merge,
                confidence=fields.location_confidence or 0.0,
                reason=(
                    f"Memory lists an open similar case {item.source_case_id}; "
                    "this call is the same household's request again."
                ),
                reasoning=None,
                missing_evidence=[],
                next_question=None,
                requires_human=False,
                escalate=False,
                latency_ms=latency_ms(),
            )

    unmatched = [need.value for need in fields.needs if need not in NEEDS_TABLE]
    if not fields.needs or unmatched:
        if not fields.needs:
            graduated = _graduated(case, overlay, narrow)
            if graduated is not None:
                return graduated
        reason = (
            "No extracted needs for the fast path."
            if not fields.needs
            else "Needs outside the System 1 table: " + ", ".join(unmatched) + "."
        )
        return _escalate(reason, latency_ms=latency_ms())

    route, priority = _needs_route(fields.needs)
    confidence = fields.location_confidence
    minimum = float(load_yaml("escalation.yaml").get("system_1_min_confidence") or 0.8)
    if confidence is None or confidence < minimum:
        graduated = _graduated(case, overlay, narrow)
        if graduated is not None:
            return graduated
        return _escalate(
            f"Location confidence {confidence} is below system_1_min_confidence "
            f"{minimum}.",
            confidence=confidence or 0.0,
            latency_ms=latency_ms(),
        )

    if fields.people_count is None:
        return Outcome(
            system=System.system_1,
            outcome="fast_route",
            priority=priority,
            needs=fields.needs,
            route=route,
            confidence=confidence,
            reason="Needs are clear but the household size is missing.",
            reasoning=None,
            missing_evidence=["people_count"],
            next_question="How many people are with you?",
            requires_human=False,
            escalate=False,
            latency_ms=latency_ms(),
        )

    return Outcome(
        system=System.system_1,
        outcome="fast_route",
        priority=priority,
        needs=fields.needs,
        route=route,
        confidence=confidence,
        reason="Clear fast-path request with a confident location.",
        reasoning=None,
        missing_evidence=[],
        next_question=None,
        requires_human=False,
        escalate=False,
        latency_ms=latency_ms(),
    )


def _graduated(
    case: CaseState,
    overlay: Overlay | None,
    narrow: str | None,
) -> Outcome | None:
    """A learned System 1 rule for this narrow signature, or None."""
    if overlay is None or narrow is None:
        return None
    rule = overlay.graduated.get(narrow)
    if rule is None:
        return None
    confidence = case.fields.location_confidence
    if confidence is None:
        confidence = float(
            load_yaml("escalation.yaml").get("system_1_min_confidence") or 0.8
        )
    return Outcome(
        system=System.system_1,
        outcome="fast_route",
        priority=Priority(rule["priority"]),
        needs=[Need(need) for need in rule["needs"]],
        route=Route(rule["route"]),
        confidence=confidence,
        reason=(
            "Graduated pattern: System 2 decided this the same way "
            f"{rule.get('wins', 0)} times."
        ),
        reasoning=None,
        missing_evidence=[],
        next_question=None,
        requires_human=bool(rule["requires_human"]),
        escalate=False,
        latency_ms=0,
    )


def _needs_route(needs: list[Need]) -> tuple[Route | None, Priority | None]:
    """Highest priority wins; on a tie the first need in `needs` order wins."""
    best: tuple[Route | None, Priority | None] = (None, None)
    best_rank = len(_PRIORITY_ORDER)
    for need in needs:
        entry = NEEDS_TABLE.get(need)
        if entry is None:
            continue
        rank = _PRIORITY_ORDER[entry[1]]
        if rank < best_rank:
            best = entry
            best_rank = rank
    return best
