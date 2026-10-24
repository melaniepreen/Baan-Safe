"""Sapling policy adapter. Owner: Melanie.

Loads corpus rules by id and builds the (policy, evidence, claim) triple.
The checkpoint limit is 16,384 tokens. This adapter drops whole rules once
the next rule would pass that ceiling. It does not cut a rule in half.

Which ids are authoritative for the demo is policies.authoritative_set.
While that is TODO_HUMAN the verifier does not substitute the corpus for
memory text unless the case already names rule ids.
"""

from __future__ import annotations

import re

from config.settings import DecisionRequired, require_decision, unset_decisions
from contracts.models import CaseState
from policies.schema import NormalisedRule
from policies.service import PolicyError, get_service
from system2.sapling_client import MAX_INPUT_TOKENS, estimate_tokens

_RULE_TOKEN = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+")


def format_rule(rule: NormalisedRule) -> str:
    english = rule.languages["en"]
    thai = rule.languages["th"]
    lines = [
        f"[{rule.rule_id}]",
        f"source_id: {rule.source_id}",
        f"jurisdiction: {rule.jurisdiction}",
        f"domain: {rule.domain}",
        f"status: {rule.status}",
        f"verified: {'true' if rule.verified else 'false'}",
        f"topic: {rule.topic}",
        "checks: " + ", ".join(rule.checks),
        f"English: {english.text}",
    ]
    if thai.text:
        lines.append(f"Thai: {thai.text}")
    if rule.effective_stated:
        lines.append(f"Effective date stated by the instrument: {rule.effective_stated}")
    if rule.effective_note:
        lines.append(f"Effective-date note: {rule.effective_note}")
    if rule.caveat:
        lines.append(f"Caveat: {rule.caveat}")
    if rule.locator:
        lines.append(f"Locator: {rule.locator}")
    lines.append(f"Excerpt: {rule.source_excerpt}")
    lines.append(f"Source: {rule.source_url}")
    lines.append(f"Retrieved: {rule.retrieved}")
    lines.append(f"License: {rule.license}")
    return "\n".join(lines)


def _pack(included: list[NormalisedRule], omitted_ids: list[str], max_tokens: int) -> str:
    version = get_service().current().version
    parts = [f"corpus_version: {version}"]
    parts.extend(format_rule(rule) for rule in included)
    if omitted_ids:
        parts.append(
            "Omitted rule ids, because the next block did not fit in the "
            f"{max_tokens}-token input limit. Omitted text is not support "
            "for the claim: " + ", ".join(omitted_ids) + "."
        )
    policy = "\n\n".join(parts).strip()
    if policy:
        return policy
    return "No policy text fit in the input limit. Missing policy text is not support for the claim."


def build_sapling_input(
    rule_ids: list[str],
    evidence: str,
    claim: str,
    *,
    max_tokens: int = MAX_INPUT_TOKENS,
) -> dict[str, object]:
    """Return policy, evidence, and claim, plus which rule ids were kept."""
    if not isinstance(evidence, str) or not evidence.strip():
        raise ValueError("evidence must be a nonempty string.")
    if not isinstance(claim, str) or not claim.strip():
        raise ValueError("claim must be a nonempty string.")
    if not rule_ids:
        raise ValueError("rule_ids must name at least one policy.")
    if max_tokens < 1:
        raise ValueError("max_tokens must be at least 1.")
    evidence = evidence.strip()
    claim = claim.strip()
    rules: list[NormalisedRule] = []
    seen: set[str] = set()
    service = get_service()
    for rule_id in rule_ids:
        if rule_id in seen:
            continue
        seen.add(rule_id)
        try:
            rules.append(service.require_rule(rule_id))
        except PolicyError as exc:
            raise ValueError(str(exc)) from exc

    included: list[PolicyRule] = []
    for index, rule in enumerate(rules):
        rest = [item.id for item in rules[index + 1 :]]
        trial = _pack(included + [rule], rest, max_tokens)
        if estimate_tokens(trial, evidence, claim) <= max_tokens:
            included.append(rule)
            continue
        omitted = [item.id for item in rules[index:]]
        policy = _pack(included, omitted, max_tokens)
        while included and estimate_tokens(policy, evidence, claim) > max_tokens:
            omitted.insert(0, included[-1].id)
            included.pop()
            policy = _pack(included, omitted, max_tokens)
        if estimate_tokens(policy, evidence, claim) > max_tokens:
            raise ValueError(
                f"Input is about {estimate_tokens(policy, evidence, claim)} tokens. "
                f"Sapling's limit is {MAX_INPUT_TOKENS} encoded tokens, "
                "and the checkpoint does not truncate."
            )
        return _result(policy, evidence, claim, included, omitted)

    policy = _pack(included, [], max_tokens)
    if estimate_tokens(policy, evidence, claim) > max_tokens:
        raise ValueError(
            f"Input is about {estimate_tokens(policy, evidence, claim)} tokens. "
            f"Sapling's limit is {MAX_INPUT_TOKENS} encoded tokens, "
            "and the checkpoint does not truncate."
        )
    return _result(policy, evidence, claim, included, [])


def _result(
    policy: str,
    evidence: str,
    claim: str,
    included: list[NormalisedRule],
    omitted: list[str],
) -> dict[str, object]:
    return {
        "policy": policy,
        "evidence": evidence,
        "claim": claim,
        "corpus_version": get_service().current().version,
        "included_rule_ids": [rule.id for rule in included],
        "omitted_rule_ids": list(omitted),
        "estimated_tokens": estimate_tokens(policy, evidence, claim),
    }


def rule_ids_from_case(case: CaseState) -> list[str]:
    """Rule ids the case already names. Unknown flags are left alone."""
    known = get_service().known_ids()
    found: list[str] = []
    for flag in case.policy_flags:
        if flag in known and flag not in found:
            found.append(flag)
    for item in case.memory_context:
        if item.kind != "policy":
            continue
        for token in _RULE_TOKEN.findall(item.summary):
            if token in known and token not in found:
                found.append(token)
    return found


def configured_authoritative_ids() -> list[str] | None:
    """None while a human has not chosen the demo set."""
    if unset_decisions(["policies.authoritative_set"]):
        return None
    raw = require_decision("policies.authoritative_set")
    if isinstance(raw, str):
        return [part.strip() for part in raw.split(",") if part.strip()]
    if isinstance(raw, list):
        return [str(part).strip() for part in raw if str(part).strip()]
    raise DecisionRequired(
        "config/decisions.yaml:policies.authoritative_set must be a string or a list of rule ids."
    )


def require_authoritative_ids() -> list[str]:
    """Raise while policies.authoritative_set is still TODO_HUMAN."""
    if unset_decisions(["policies.authoritative_set"]):
        raise DecisionRequired(
            "config/decisions.yaml:policies.authoritative_set is TODO_HUMAN. "
            "A human must choose which rule ids are authoritative for the demo. "
            "The corpus can still be loaded by rule id."
        )
    ids = configured_authoritative_ids()
    if not ids:
        raise DecisionRequired(
            "config/decisions.yaml:policies.authoritative_set is empty. "
            "A human must name at least one rule id."
        )
    return ids


def policy_text_for_case(case: CaseState, evidence: str, claim: str) -> str | None:
    """Corpus text for this case, or None to keep the memory-summary path."""
    rule_ids = rule_ids_from_case(case)
    if not rule_ids:
        rule_ids = configured_authoritative_ids() or []
    if not rule_ids:
        return None
    built = build_sapling_input(rule_ids, evidence, claim)
    policy = built["policy"]
    if not isinstance(policy, str) or not policy.strip():
        raise ValueError("policy must be a nonempty string.")
    return policy
