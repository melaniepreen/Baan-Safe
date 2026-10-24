"""Gold system, priority, and route for a synthetic call.

System 1 is whatever ``system1.decide`` returns, including ``duplicate_merge``
when the call carries a ``similar_case`` memory at relevance >= 0.9.
System 2 is the hand table below. It follows ``config/escalation.yaml`` and
the signed-off fixtures: ``rescue`` is ``rescue_coordination`` on System 2,
safeguarding is a supervisor, and a missing location with no other trigger
keeps the needs-table route.
"""

from __future__ import annotations

from contracts.models import CaseState, MemoryItem, Need, Priority, Route, System
from gateway.chooser import choose
from system1.decide import NEEDS_TABLE, decide

COLOUR_TO_LABEL = {
    "red": "niems_red_critical",
    "yellow": "niems_yellow_urgent",
    "green": "niems_green_not_severe",
    "white": "niems_white_general",
    "black": "niems_black_not_a_patient",
}

# The five NIEMS colours are one choice question. Everything else is noul.
NOUL_LABELS = (
    "niems_not_conscious_or_breathing",
    "sphere_water_short",
    "sphere_food_short",
    "sphere_shelter_crowded",
    "safeguarding_child",
    "safeguarding_older_person",
    "safeguarding_disability",
    "safeguarding_serious_health",
    "safeguarding_protection_referral",
    "flood_water_depth",
    "flood_trapped",
)

_PRIORITY_RANK = {"P1": 0, "P2": 1, "P3": 2, "P4": 3}


def needs_route(needs: list[str]) -> tuple[str, str]:
    """Same tie rule as System 1: higher priority wins, then earlier need."""

    best_route = "information_only"
    best_priority = "P4"
    best_rank = 99
    for need_name in needs:
        try:
            need = Need(need_name)
        except ValueError:
            continue
        entry = NEEDS_TABLE.get(need)
        if entry is None:
            continue
        route, priority = entry
        rank = _PRIORITY_RANK[priority.value]
        if rank < best_rank:
            best_route = route.value
            best_priority = priority.value
            best_rank = rank
    return best_route, best_priority


def next_action(
    route: str,
    flags: list[str],
    missing: list[str],
    location,
    question: str | None,
) -> str:
    """``router.merge`` first-match, without dispatch fill or the ledger."""

    if route == Route.supervisor_escalation.value or "safeguarding" in flags:
        return "escalate_to_supervisor"
    if route == Route.aid_caseworker.value:
        return "escalate_to_supervisor"
    if route == Route.duplicate_merge.value:
        return "finalize_case"
    if missing or question or location is None:
        return "ask_next_question"
    if route == Route.information_only.value:
        return "finalize_case"
    return "create_provisional_dispatch"


def _location_gap(case: CaseState) -> tuple[list[str], str | None]:
    fields = case.fields
    if fields.location is None or fields.location_confidence is None:
        return ["location"], "Which district are you in?"
    if fields.location_confidence < 0.7:
        return ["precise_location"], "Which district or road are you near?"
    return [], None


def _system_2(case: CaseState, colour: str, labels: set[str]) -> dict:
    fields = case.fields
    needs = [need.value for need in fields.needs]
    flags = list(case.policy_flags)
    vulnerable = set(fields.vulnerable)
    missing, question = _location_gap(case)
    critical = (
        colour == "red"
        or "flood_trapped" in labels
        or "niems_not_conscious_or_breathing" in labels
    )

    if "rescue" in needs:
        route, priority, human = "rescue_coordination", ("P1" if critical else "P2"), True
    elif fields.medical or "medical" in needs:
        if critical:
            priority = "P1"
        elif colour == "green":
            priority = "P3"
        else:
            priority = "P2"
        route, human = "medical_response", True
    elif "safeguarding" in flags:
        route, priority, human = "supervisor_escalation", "P2", True
        if not missing:
            missing = ["guardian_contact_status"]
            question = "Is a named guardian expected, or should a supervisor take this now?"
    elif "aid_exception" in flags or "aid_payment" in needs:
        route, priority, human = "aid_caseworker", "P3", True
        if not missing:
            missing = ["eligibility_rule"]
            question = "Do you want a caseworker to review this exception?"
    elif "conflicting_evidence" in flags:
        route, priority, human = "supervisor_escalation", "P2", True
    elif "oxygen_dependent" in vulnerable or "immobile" in vulnerable:
        route = "medical_response" if "oxygen_dependent" in vulnerable else needs_route(needs)[0]
        priority, human = "P2", True
    else:
        route, priority = needs_route(needs)
        human = False

    if "safeguarding" in flags:
        human = True
    action = next_action(route, flags, missing, fields.location, question)
    return {
        "system": System.system_2.value,
        "priority": priority,
        "route": route,
        "needs": needs,
        "requires_human": human,
        "missing_evidence": missing,
        "acceptable_next_questions": [question] if question else [],
        "action": action,
    }


def derive_expected(
    case: CaseState,
    memory: list[MemoryItem],
    *,
    colour: str,
    labels: list[str],
) -> dict:
    """Expected block for one call. ``labels`` includes the colour label."""

    system, _triggers = choose(case)
    label_set = set(labels)
    if system is System.system_1:
        scored = case.model_copy(update={"memory_context": list(memory)})
        outcome = decide(scored)
        flags = list(case.policy_flags)
        question = outcome.next_question
        missing = list(outcome.missing_evidence)
        route = outcome.route.value
        human = (
            outcome.requires_human
            or route in {Route.supervisor_escalation.value, Route.aid_caseworker.value}
            or "safeguarding" in flags
        )
        return {
            "system": System.system_1.value,
            "priority": outcome.priority.value,
            "route": route,
            "needs": [need.value for need in outcome.needs],
            "requires_human": human,
            "missing_evidence": missing,
            "acceptable_next_questions": [question] if question else [],
            "action": next_action(route, flags, missing, case.fields.location, question),
        }
    return _system_2(case, colour, label_set)


def assert_rescue(expected: dict, needs: list[str]) -> None:
    if "rescue" in needs:
        if expected["system"] != "system_2" or expected["route"] != "rescue_coordination":
            raise RuntimeError(
                f"rescue must route to system_2 rescue_coordination, got {expected}"
            )
