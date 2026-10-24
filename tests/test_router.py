"""router.merge next-action rules and dispatch fan-out."""

from __future__ import annotations

from datetime import datetime, timezone

from contracts.models import (
    CaseState,
    ExtractedFields,
    Need,
    NextAction,
    Outcome,
    Priority,
    Route,
    System,
)
from mocks.loader import ResourcesSnapshot
from router.merge import merge


def _case(
    location: str | None = "Mae Mo District, Lampang",
    needs: list[Need] | None = None,
    flags: list[str] | None = None,
) -> CaseState:
    return CaseState(
        case_id="router-test",
        caller_id_hash="synthetic:router-test",
        transcript=[],
        fields=ExtractedFields(
            location=location,
            location_confidence=0.9,
            people_count=2,
            needs=needs or [Need.water],
        ),
        policy_flags=flags or [],
        received_at=datetime(2026, 10, 24, tzinfo=timezone.utc),
    )


def _outcome(
    route: Route = Route.welfare_distribution,
    needs: list[Need] | None = None,
    escalate: bool = False,
    requires_human: bool = False,
    missing_evidence: list[str] | None = None,
    next_question: str | None = None,
    priority: Priority = Priority.P3,
) -> Outcome:
    return Outcome(
        system=System.system_1,
        outcome="escalate" if escalate else "fast_route",
        priority=priority,
        needs=needs if needs is not None else [Need.water],
        route=route,
        confidence=0.9,
        reason="test outcome",
        missing_evidence=missing_evidence or [],
        next_question=next_question,
        requires_human=requires_human,
        escalate=escalate,
        latency_ms=1,
    )


def test_supervisor_route_escalates():
    decision = merge(_case(), _outcome(route=Route.supervisor_escalation))
    assert decision.next_action is NextAction.escalate_to_supervisor
    assert decision.requires_human is True


def test_safeguarding_flag_escalates():
    decision = merge(_case(flags=["safeguarding"]), _outcome())
    assert decision.next_action is NextAction.escalate_to_supervisor
    assert decision.requires_human is True


def test_aid_caseworker_escalates():
    decision = merge(_case(), _outcome(route=Route.aid_caseworker))
    assert decision.next_action is NextAction.escalate_to_supervisor
    assert decision.requires_human is True


def test_outcome_escalate_escalates():
    decision = merge(_case(), _outcome(escalate=True))
    assert decision.next_action is NextAction.escalate_to_supervisor


def test_duplicate_merge_finalizes():
    decision = merge(_case(), _outcome(route=Route.duplicate_merge))
    assert decision.next_action is NextAction.finalize_case
    assert decision.dispatches == []


def test_missing_evidence_asks_next_question():
    decision = merge(_case(), _outcome(missing_evidence=["people_count"]))
    assert decision.next_action is NextAction.ask_next_question
    assert decision.dispatches == []


def test_next_question_asks_next_question():
    decision = merge(_case(), _outcome(next_question="How many people?"))
    assert decision.next_action is NextAction.ask_next_question


def test_missing_location_asks_next_question():
    decision = merge(_case(location=None), _outcome())
    assert decision.next_action is NextAction.ask_next_question
    assert decision.dispatches == []


def test_information_only_finalizes():
    decision = merge(
        _case(needs=[Need.information]),
        _outcome(route=Route.information_only, needs=[Need.information]),
    )
    assert decision.next_action is NextAction.finalize_case
    assert decision.dispatches == []


def test_multi_need_dispatch_fans_out():
    case = _case(needs=[Need.water, Need.shelter])
    outcome = _outcome(needs=[Need.water, Need.shelter])
    decision = merge(case, outcome)
    assert decision.next_action is NextAction.create_provisional_dispatch
    assert [d.need for d in decision.dispatches] == [Need.water, Need.shelter]
    kinds = {d.need: d.resource_kind for d in decision.dispatches}
    assert kinds == {Need.water: "welfare_point", Need.shelter: "shelter"}
    water = decision.dispatches[0]
    assert water.status == "provisional"
    assert water.resource_id == "welfare-fictional-01"
    assert water.same_district is True
    shelter = decision.dispatches[1]
    assert shelter.same_district is False


def test_same_district_is_preferred():
    case = _case(location="Mae Mo District, Lampang")
    decision = merge(case, _outcome())
    assert decision.dispatches[0].resource_id == "welfare-fictional-01"
    assert decision.dispatches[0].same_district is True


def test_unfilled_when_no_stock_requires_human():
    empty = ResourcesSnapshot()
    decision = merge(_case(), _outcome(), resources=empty)
    assert decision.next_action is NextAction.create_provisional_dispatch
    assert decision.dispatches[0].status == "unfilled"
    assert decision.dispatches[0].resource_id is None
    assert decision.requires_human is True


def test_p1_with_missing_evidence_asks_first():
    outcome = _outcome(
        route=Route.rescue_coordination,
        needs=[Need.rescue],
        priority=Priority.P1,
        missing_evidence=["water_depth"],
    )
    decision = merge(_case(needs=[Need.rescue]), outcome)
    assert decision.next_action is NextAction.ask_next_question
    assert decision.dispatches == []


def _medical_case(case_id: str, location: str = "Mueang Phrae District, Phrae") -> CaseState:
    case = _case(location=location, needs=[Need.medical])
    return case.model_copy(update={"case_id": case_id})


def _medical_outcome() -> Outcome:
    return _outcome(route=Route.medical_response, needs=[Need.medical])


def test_second_case_gets_unfilled_when_stock_is_reserved():
    first = merge(_medical_case("case-a"), _medical_outcome())
    assert first.dispatches[0].status == "provisional"
    assert first.dispatches[0].resource_id == "amb-fictional-01"
    second = merge(_medical_case("case-b"), _medical_outcome())
    assert second.dispatches[0].status == "unfilled"
    assert second.requires_human is True


def test_same_case_twice_holds_one_reservation():
    case = _medical_case("case-a")
    first = merge(case, _medical_outcome())
    again = merge(case, _medical_outcome())
    assert again.dispatches[0].resource_id == first.dispatches[0].resource_id
    other = merge(_medical_case("case-c"), _medical_outcome())
    assert other.dispatches[0].status == "unfilled"


def test_redesision_without_the_need_releases_stock():
    case = _medical_case("case-a")
    merge(case, _medical_outcome())
    merge(case, _outcome(route=Route.information_only, needs=[Need.information]))
    other = merge(_medical_case("case-b"), _medical_outcome())
    assert other.dispatches[0].status == "provisional"
