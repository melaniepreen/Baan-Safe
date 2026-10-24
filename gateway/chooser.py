"""Field precheck that picks System 1 or System 2. Owner: Moly.

This is the decided `gateway.route_chooser` (`field precheck`). It evaluates
the structured triggers in `config/escalation.yaml` (`route_to_system_2_if_any`)
against the case's extracted fields and policy flags. An empty trigger list
means System 1. Signed off by Moly, 24 Oct 2026.
"""

from __future__ import annotations

from config.settings import load_yaml
from contracts.models import CaseState, System


def _triggers_config() -> dict:
    return load_yaml("escalation.yaml").get("route_to_system_2_if_any") or {}


def system_2_triggers(case: CaseState) -> list[str]:
    """Human-readable names of the System 2 triggers that fired, in config order."""
    config = _triggers_config()
    fields = case.fields
    found: list[str] = []
    if config.get("medical") and fields.medical:
        found.append("medical")
    for tag in config.get("vulnerable_any") or []:
        if tag in fields.vulnerable:
            found.append(f"vulnerable:{tag}")
    threshold = config.get("location_confidence_below")
    if threshold is not None:
        if fields.location is None or fields.location_confidence is None:
            found.append("location_missing")
        elif fields.location_confidence < float(threshold):
            found.append(f"location_confidence<{threshold}")
    flags = set(case.policy_flags)
    for flag in config.get("policy_flags_any") or []:
        if flag in flags:
            found.append(f"flag:{flag}")
    needs = {need.value for need in fields.needs}
    for need in config.get("needs_any") or []:
        if need in needs:
            found.append(f"need:{need}")
    return found


def choose(case: CaseState) -> tuple[System, list[str]]:
    """Pick the exclusive system and return the triggers behind the choice."""
    triggers = system_2_triggers(case)
    if triggers:
        return System.system_2, triggers
    return System.system_1, triggers
