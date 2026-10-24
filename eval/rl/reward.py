"""Reward for one scored episode. Off the live path."""

from __future__ import annotations

from dataclasses import dataclass, field

from contracts.models import Need, Outcome, Priority, Route, RouterDecision, System
from eval.rl.themes import Truth

RANK = {Priority.P1: 0, Priority.P2: 1, Priority.P3: 2, Priority.P4: 3}
SIM_NEED_ROUTE: dict[str, str] = {
    "rescue": "rescue_coordination",
    "medical": "medical_response",
    "water": "welfare_distribution",
    "food": "welfare_distribution",
    "shelter": "shelter_placement",
    "evacuation": "shelter_placement",
    "aid_payment": "aid_caseworker",
    "information": "information_only",
    "power": "information_only",
}

# Closed s1_triage labels, first match over the outcome's needs.
S1_LABELS: tuple[tuple[frozenset[str], str], ...] = (
    (frozenset({"rescue"}), "flood_trapped"),
    (frozenset({"medical"}), "medical"),
    (frozenset({"water"}), "sphere_water_short"),
    (frozenset({"shelter", "evacuation"}), "sphere_shelter_crowded"),
    (frozenset({"food"}), "sphere_food_short"),
    (frozenset({"information", "power"}), "niems_white_general"),
)


@dataclass(frozen=True)
class Score:
    reward: float
    correct: bool
    under_triage: bool
    critical_under: bool
    missed_human: bool
    d: int


def truth_from_expected(expected: dict) -> Truth:
    return Truth(
        priority=expected["priority"],
        routes=(expected["route"],),
        requires_human=bool(expected["requires_human"]),
        needs=tuple(expected["needs"]),
    )


def truth_for_sim(spec) -> Truth:
    persona = spec.persona
    first = persona.true_needs[0] if persona.true_needs else "information"
    return Truth(
        priority=persona.true_urgency,
        routes=(SIM_NEED_ROUTE.get(first, "information_only"),),
        requires_human=spec.critical,
        needs=tuple(persona.true_needs),
    )


def s1_label(needs: list[Need] | tuple[str, ...], priority: Priority | str) -> str | None:
    values = {need.value if isinstance(need, Need) else need for need in needs}
    rank = priority.value if isinstance(priority, Priority) else priority
    for wants, label in S1_LABELS:
        if values & wants:
            if label == "medical":
                return "niems_red_critical" if rank == "P1" else "niems_yellow_urgent"
            return label
    return None


def gold_outcome(case_truth: Truth) -> Outcome:
    return Outcome(
        system=System.system_2,
        outcome="reasoned_recommendation",
        priority=Priority(case_truth.priority),
        needs=[Need(need) for need in case_truth.needs],
        route=Route(case_truth.routes[0]),
        confidence=1.0,
        reason="Authored truth.",
        reasoning=None,
        missing_evidence=[],
        next_question=None,
        requires_human=case_truth.requires_human,
        escalate=False,
        latency_ms=0,
    )


def score(
    decision: RouterDecision,
    truth: Truth,
    systems_ran: set[System],
    s2_fell_back: bool,
) -> Score:
    pred = decision.final_priority
    d = RANK[pred] - RANK[Priority(truth.priority)]
    if d == 0:
        r_pri = 1.0
    elif d > 0:
        r_pri = -2.0 * d
    else:
        r_pri = -0.5 * abs(d)
    route_ok = decision.final_route.value in truth.routes or (
        decision.final_route is Route.supervisor_escalation and truth.requires_human
    )
    r_route = 0.5 if route_ok else 0.0
    pred_human = decision.requires_human
    missed_human = truth.requires_human and not pred_human
    if missed_human:
        r_human = -1.0
    elif pred_human and not truth.requires_human:
        r_human = -0.25
    else:
        r_human = 0.0
    r_cost = 0.0
    if System.system_1 in systems_ran:
        r_cost -= 0.05
    if System.system_2 in systems_ran:
        r_cost -= 0.30
        if s2_fell_back:
            r_cost -= 0.20
    reward = r_pri + r_route + r_human + r_cost
    return Score(
        reward=reward,
        correct=d == 0 and route_ok and not missed_human,
        under_triage=d > 0,
        critical_under=truth.priority == "P1" and d > 0,
        missed_human=missed_human,
        d=d,
    )
