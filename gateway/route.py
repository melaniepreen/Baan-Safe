"""Mubit gateway stub. Owner: Moly.

One turn retrieves memory, records a policy pre-check, and routes to System 1
or System 2. It does not call both. Mubit does not reason: this module does
not evaluate escalation rules and it does not choose a priority.

use_stubs=True loads the stub for the chosen system. The live chooser is
gateway.route_chooser and stays TODO_HUMAN. For a fixture id only, the harness
reads expected.system. That lookup is not a product rule.

use_stubs=False, or S1_IMPL=real / S2_IMPL=real on the chosen system, calls
that system's decide() and lets the NotImplementedError through.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

from config.settings import DecisionRequired, load_yaml, require_decision
from contracts.models import (
    CaseState,
    NextAction,
    Outcome,
    Priority,
    Route,
    RouterDecision,
    System,
    TraceEvent,
)
from enrich.context import location_context
from fixtures.load import load_fixture
from gateway.auth import status as auth_status
from gateway.policy import precheck_notes
from memory.adapter import retrieve
from mocks.loader import has_s1_stub, has_s2_stub, load_s1_stub, load_s2_stub
from system1 import decide as system1
from system2 import decide as system2
from trace import emit


def handle(case: CaseState, use_stubs: bool = True) -> RouterDecision:
    started = _now()
    _enrich(case)
    case.memory_context = retrieve(case)
    system = choose_system(case)
    notes = [auth_status(), *precheck_notes()]
    emit(
        TraceEvent(
            case_id=case.case_id,
            stage="gateway",
            started_at=started,
            latency_ms=0,
            notes=(
                "mubit gateway stub: "
                + "; ".join(notes)
                + f"; memory via adapter; exclusive route {system.value}"
            ),
        )
    )
    outcome = _run(case, system, use_stubs=use_stubs)
    system_started = _now()
    emit(
        TraceEvent(
            case_id=case.case_id,
            stage=system.value,
            started_at=system_started,
            latency_ms=outcome.latency_ms or 0,
            model=None,
            outcome=outcome,
            notes="stub outcome" if use_stubs else "real interface",
        )
    )
    router_started = _now()
    decision = _assemble(case, [outcome], outcome, notes)
    emit(
        TraceEvent(
            case_id=case.case_id,
            stage="router",
            started_at=router_started,
            latency_ms=0,
            notes="stub copy of the single selected outcome; router.merge was not called",
        )
    )
    return decision


def choose_system(case: CaseState) -> System:
    """Pick System 1 or System 2. Never both.

    Fixture ids use expected.system as a harness stand-in. Any other case
    needs gateway.route_chooser, which is TODO_HUMAN and raises.
    """
    mode = load_yaml("routing.yaml").get("mode")
    if mode != "exclusive":
        raise RuntimeError(
            f"config/routing.yaml mode is {mode!r}. "
            "The stub gateway only implements exclusive routing "
            "(System 1 or System 2, not System 1 then System 2)."
        )
    try:
        expected = load_fixture(case.case_id)["expected"]["system"]
    except KeyError:
        require_decision("gateway.route_chooser")
        raise DecisionRequired(
            "config/decisions.yaml:gateway.route_chooser did not name a system."
        )
    return System(expected)


def _run(case: CaseState, system: System, use_stubs: bool) -> Outcome:
    real = (system is System.system_1 and _impl("S1_IMPL") == "real") or (
        system is System.system_2 and _impl("S2_IMPL") == "real"
    )
    if real or not use_stubs:
        if system is System.system_1:
            return system1.decide(case)
        return system2.decide(case)
    if system is System.system_1:
        if has_s1_stub(case.case_id):
            return load_s1_stub(case.case_id)
        return _fallback_outcome(case.case_id, System.system_1)
    if has_s2_stub(case.case_id):
        return load_s2_stub(case.case_id)
    return _fallback_outcome(case.case_id, System.system_2)


def _impl(name: str) -> str:
    return os.environ.get(name, "stub").strip().lower() or "stub"


def _enrich(case: CaseState) -> None:
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


def _assemble(
    case: CaseState,
    outcomes: list[Outcome],
    chosen: Outcome,
    extra_notes: list[str],
) -> RouterDecision:
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
        f"stub gateway selected {chosen.system.value} exclusively",
        f"memory items: {len(case.memory_context)}",
        *extra_notes,
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
