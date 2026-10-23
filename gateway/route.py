"""Stub gateway.

use_stubs=True retrieves mock memory, loads stub outcomes, and copies the
selected stub into a RouterDecision. It does not evaluate escalation rules
and it does not call System 1 or System 2.

Enrichment may attach flood and rain flags from public data. Those flags do
not change priority or route.
"""

from __future__ import annotations

from datetime import datetime, timezone

from config.settings import load_yaml
from contracts.models import CaseState, NextAction, Outcome, Priority, Route, RouterDecision, System
from enrich.context import location_context
from mocks.loader import has_s1_stub, has_s2_stub, load_memory, load_s1_stub, load_s2_stub
from trace import emit
from contracts.models import TraceEvent


def handle(case: CaseState, use_stubs: bool = True) -> RouterDecision:
    if not use_stubs:
        raise NotImplementedError(
            "not implemented yet — owner: Moly. "
            "Pass use_stubs=True until system1, system2, and router.merge exist."
        )
    started = _now()
    _enrich(case)
    case.memory_context = load_memory(case.case_id)
    emit(
        TraceEvent(
            case_id=case.case_id,
            stage="gateway",
            started_at=started,
            latency_ms=0,
            notes="stub gateway: memory retrieved from mocks",
        )
    )

    s1_started = _now()
    if has_s1_stub(case.case_id):
        system_1 = load_s1_stub(case.case_id)
    else:
        system_1 = _fallback_outcome(case.case_id)
    emit(
        TraceEvent(
            case_id=case.case_id,
            stage="system_1",
            started_at=s1_started,
            latency_ms=system_1.latency_ms or 0,
            model=None,
            notes="stub outcome",
        )
    )
    outcomes = [system_1]
    chosen = system_1
    if system_1.escalate:
        s2_started = _now()
        if has_s2_stub(case.case_id):
            system_2 = load_s2_stub(case.case_id)
        else:
            system_2 = _fallback_outcome(case.case_id, system=System.system_2)
        outcomes.append(system_2)
        chosen = system_2
        emit(
            TraceEvent(
                case_id=case.case_id,
                stage="system_2",
                started_at=s2_started,
                latency_ms=system_2.latency_ms or 0,
                model=None,
                notes="stub outcome",
            )
        )

    router_started = _now()
    decision = _assemble(case, outcomes, chosen)
    emit(
        TraceEvent(
            case_id=case.case_id,
            stage="router",
            started_at=router_started,
            latency_ms=0,
            notes="stub copy of selected outcome; router.merge was not called",
        )
    )
    return decision


def _enrich(case: CaseState) -> None:
    import os

    from ingest.db import db_exists

    mode = os.environ.get("ENRICH_IMPL", "").strip().lower()
    if not mode:
        mode = "data" if db_exists() else "off"
    if mode == "off":
        return
    ctx = location_context(case.fields.location, None, None)
    case.resources = {**case.resources, "location_context": ctx}
    thresholds = load_yaml("escalation.yaml").get("enrichment_flags") or {}
    flags = list(case.policy_flags)
    if ctx.get("in_flood_extent_1d") or ctx.get("in_flood_extent_7d"):
        _add(flags, "in_active_flood_extent")
    if ctx.get("repeat_flood_area"):
        _add(flags, "repeat_flood_area")
    forecast = ctx.get("rainfall_forecast_24h_mm")
    limit = thresholds.get("heavy_rain_forecast_mm_24h")
    if forecast is not None and limit is not None and forecast >= float(limit):
        _add(flags, "heavy_rain_forecast")
    observed = ctx.get("rainfall_last_24h_mm")
    observed_limit = thresholds.get("heavy_rain_observed_mm_24h")
    if observed is not None and observed_limit is not None and observed >= float(observed_limit):
        _add(flags, "heavy_rain_observed")
    case.policy_flags = flags


def _add(flags: list[str], flag: str) -> None:
    if flag not in flags:
        flags.append(flag)


def _assemble(case: CaseState, outcomes: list[Outcome], chosen: Outcome) -> RouterDecision:
    order = load_yaml("escalation.yaml").get("stub_next_action_order") or []
    action = NextAction.create_provisional_dispatch
    for rule in order:
        when = rule.get("when")
        if when == "requires_human" and chosen.requires_human:
            action = NextAction(rule["action"])
            break
        if when == "missing_evidence_or_next_question" and (
            chosen.missing_evidence or chosen.next_question
        ):
            action = NextAction(rule["action"])
            break
        if when == "escalate" and chosen.escalate:
            action = NextAction(rule["action"])
            break
        if when == "default":
            action = NextAction(rule["action"])
            break
    notes = [
        f"stub gateway selected {chosen.system.value}",
        f"memory items: {len(case.memory_context)}",
    ]
    for item in case.memory_context:
        if item.kind == "correction":
            notes.append(f"retrieved correction memory: {item.summary}")
    for flag in case.policy_flags:
        notes.append(f"policy flag: {flag}")
    return RouterDecision(
        case_id=case.case_id,
        next_action=action,
        final_priority=chosen.priority,
        final_route=chosen.route,
        requires_human=chosen.requires_human,
        source_outcomes=outcomes,
        policy_notes=notes,
    )


def _fallback_outcome(case_id: str, system: System = System.system_1) -> Outcome:
    return Outcome(
        system=system,
        outcome="escalate",
        priority=Priority.P2,
        needs=[],
        route=Route.supervisor_escalation,
        confidence=0.0,
        reason=(
            f"No stub outcome for {case_id}. "
            "Human decision logic is not implemented."
        ),
        reasoning=None,
        missing_evidence=["fixture_stub"],
        next_question=None,
        requires_human=True,
        escalate=system is System.system_1,
        latency_ms=0,
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)
