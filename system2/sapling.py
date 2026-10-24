"""Sapling verifier step. Owner: Melanie.

Runs after System 2 reasoning and before the Decision Router. It runs only
when the outcome is a System 2 aid-eligibility or denial check. System 1
returns unchanged, and the client is not called.

supported lets the proposed action stand. violation blocks it. unsure,
missing, and contradicted become a human handoff.
"""

from __future__ import annotations

from config.settings import DecisionRequired, require_decision
from contracts.models import CaseState, Need, Outcome, Route, System
from system2.sapling_client import (
    CHECKS,
    PUBLISHED_MODEL_ID,
    SaplingVerdict,
    client_mode,
    make_verdict,
    verify,
)

__all__ = [
    "SaplingVerdict",
    "apply_verdict",
    "detect_check",
    "sapling_enabled",
    "scope_set",
    "verify_before_router",
]


def sapling_enabled() -> bool:
    try:
        return require_decision("system2.use_banyan_sapling") is True
    except DecisionRequired:
        return False


def scope_set() -> set[str]:
    try:
        raw = require_decision("system2.sapling_scope")
    except DecisionRequired:
        return set()
    if not isinstance(raw, str):
        return set()
    return {part.strip() for part in raw.split(",") if part.strip()}


def detect_check(case: CaseState, outcome: Outcome) -> str | None:
    """Name the high-stakes check, or return None when Sapling must not run."""
    if outcome.system is not System.system_2 or not sapling_enabled():
        return None
    flags = set(case.policy_flags)
    needs = {_need(item) for item in [*outcome.needs, *case.fields.needs]}
    aid = (
        outcome.route is Route.aid_caseworker
        or Need.aid_payment.value in needs
        or "aid_eligibility" in flags
        or "aid_exception" in flags
        or "aid_denial" in flags
    )
    if not aid:
        return None
    if "aid_denial" in flags:
        return "denial"
    return "aid_eligibility"


def apply_verdict(outcome: Outcome, verdict: SaplingVerdict) -> Outcome:
    note = f"sapling_verdict={verdict.verdict} sapling_action={verdict.action}"
    if verdict.check:
        note = f"{note} sapling_check={verdict.check}"
    reasoning = ((outcome.reasoning or "") + " " + note).strip()
    if verdict.action == "proceed":
        return outcome.model_copy(update={"reasoning": reasoning})
    if verdict.action == "block":
        return outcome.model_copy(
            update={
                "reasoning": reasoning,
                "requires_human": True,
                "route": Route.supervisor_escalation,
                "reason": "Sapling blocked this action. " + outcome.reason,
            }
        )
    missing = list(outcome.missing_evidence)
    token = f"sapling_{verdict.verdict}"
    if token not in missing:
        missing.append(token)
    return outcome.model_copy(
        update={
            "reasoning": reasoning,
            "requires_human": True,
            "missing_evidence": missing,
            "reason": "Sapling handed this to a human. " + outcome.reason,
        }
    )


def verify_before_router(
    case: CaseState,
    outcome: Outcome,
    *,
    check: str | None = None,
) -> Outcome:
    """Verify a high-stakes System 2 outcome. Leave every other outcome as it is."""
    if outcome.system is not System.system_2:
        return outcome
    kind = check if check is not None else detect_check(case, outcome)
    if kind is None or kind not in scope_set() or kind not in CHECKS:
        return outcome
    request = _request_from_case(case, outcome, kind)
    try:
        verdict = verify(
            request["policy"],
            request["evidence"],
            request["claim"],
            check=kind,
        )
    except ValueError as exc:
        verdict = make_verdict(
            "unsure",
            check=kind,
            stub=client_mode() != "live",
            model_id=PUBLISHED_MODEL_ID,
            notes=str(exc),
        )
    return apply_verdict(outcome, verdict)


def _request_from_case(case: CaseState, outcome: Outcome, check: str) -> dict[str, str]:
    policies = [item.summary for item in case.memory_context if item.kind == "policy"]
    if policies:
        policy = "\n".join(policies)
    else:
        policy = (
            "No policy text was retrieved. "
            f"The check is {check}. Missing policy text is not support for the claim."
        )
    parts: list[str] = []
    if case.fields.location:
        parts.append(f"Location label: {case.fields.location}.")
    if case.fields.people_count is not None:
        parts.append(f"People count: {case.fields.people_count}.")
    for turn in case.transcript:
        parts.append(f"{turn.speaker}: {turn.text}")
    evidence = "\n".join(parts) if parts else "No evidence text was retrieved."
    claim = outcome.reason.strip() or f"The {check.replace('_', ' ')} claim is ready to act on."
    return {"policy": policy, "evidence": evidence, "claim": claim}


def _need(item: Need | str) -> str:
    return item.value if isinstance(item, Need) else str(item)
