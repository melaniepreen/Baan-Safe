"""Decision router. Owner: Moly.

Turns the one selected system's Outcome into a RouterDecision: a next action,
policy notes, and — only when the action is create_provisional_dispatch — one
provisional Dispatch per dispatchable need. Dispatches never decrement or
reserve stock; a policy note says so. Signed off by Moly, 24 Oct 2026.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from contracts.models import (
    CaseState,
    Dispatch,
    Need,
    NextAction,
    Outcome,
    Route,
    RouterDecision,
)
from mocks.loader import ResourcesSnapshot, ResourceUnit, load_resources

NEED_RESOURCE_KIND: dict[Need, Literal["boat", "ambulance", "shelter", "welfare_point"]] = {
    Need.rescue: "boat",
    Need.medical: "ambulance",
    Need.water: "welfare_point",
    Need.food: "welfare_point",
    Need.shelter: "shelter",
    Need.evacuation: "shelter",
}

_KIND_ATTR = {
    "boat": "boats",
    "ambulance": "ambulances",
    "shelter": "shelters",
    "welfare_point": "welfare_points",
}

HUMAN_ROUTES = {Route.supervisor_escalation, Route.aid_caseworker}


def merge(
    case: CaseState,
    outcome: Outcome,
    extra_notes: Sequence[str] = (),
    resources: ResourcesSnapshot | None = None,
) -> RouterDecision:
    snapshot = resources if resources is not None else load_resources()
    action = _next_action(case, outcome)
    dispatches: list[Dispatch] = []
    if action is NextAction.create_provisional_dispatch:
        dispatches = _fan_out(case, outcome, snapshot)

    notes = [
        f"gateway selected {outcome.system.value} exclusively",
        f"memory items: {len(case.memory_context)}",
        *extra_notes,
    ]
    for item in case.memory_context:
        if item.kind == "correction":
            notes.append(f"retrieved correction memory: {item.summary}")
    for flag in case.policy_flags:
        notes.append(f"policy flag: {flag}")
    if dispatches:
        notes.append(
            "dispatches are provisional; stock was not decremented or reserved"
        )
    for dispatch in dispatches:
        if dispatch.note:
            notes.append(dispatch.note)

    requires_human = (
        outcome.requires_human
        or outcome.route in HUMAN_ROUTES
        or "safeguarding" in case.policy_flags
        or any(dispatch.status == "unfilled" for dispatch in dispatches)
    )
    return RouterDecision(
        case_id=case.case_id,
        next_action=action,
        final_priority=outcome.priority,
        final_route=outcome.route,
        requires_human=requires_human,
        source_outcomes=[outcome],
        policy_notes=notes,
        dispatches=dispatches,
    )


def _next_action(case: CaseState, outcome: Outcome) -> NextAction:
    """First match wins."""
    if outcome.route is Route.supervisor_escalation or "safeguarding" in case.policy_flags:
        return NextAction.escalate_to_supervisor
    if outcome.route is Route.aid_caseworker:
        return NextAction.escalate_to_supervisor
    if outcome.escalate:
        return NextAction.escalate_to_supervisor
    if outcome.route is Route.duplicate_merge:
        return NextAction.finalize_case
    if outcome.missing_evidence or outcome.next_question or case.fields.location is None:
        return NextAction.ask_next_question
    if outcome.route is Route.information_only:
        return NextAction.finalize_case
    return NextAction.create_provisional_dispatch


def _fan_out(
    case: CaseState, outcome: Outcome, snapshot: ResourcesSnapshot
) -> list[Dispatch]:
    dispatches: list[Dispatch] = []
    location = (case.fields.location or "").lower()
    for need in outcome.needs:
        kind = NEED_RESOURCE_KIND.get(need)
        if kind is None:
            continue
        units = [
            unit
            for unit in getattr(snapshot, _KIND_ATTR[kind])
            if _usable(unit)
        ]
        same_district = [
            unit
            for unit in units
            if unit.district and unit.district.lower() in location
        ]
        if same_district:
            dispatches.append(
                Dispatch(
                    need=need,
                    resource_kind=kind,
                    resource_id=same_district[0].id,
                    status="provisional",
                    same_district=True,
                )
            )
        elif units:
            dispatches.append(
                Dispatch(
                    need=need,
                    resource_kind=kind,
                    resource_id=units[0].id,
                    status="provisional",
                    same_district=False,
                )
            )
        else:
            dispatches.append(
                Dispatch(
                    need=need,
                    resource_kind=kind,
                    resource_id=None,
                    status="unfilled",
                    same_district=False,
                    note=f"no {kind} available for need {need.value}",
                )
            )
    return dispatches


def _usable(unit: ResourceUnit) -> bool:
    return (unit.available or 0) > 0 and unit.status in {"available", "open"}
