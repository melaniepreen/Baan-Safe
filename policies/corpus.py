"""Load policy rules and System 1 label hypotheses.

Rule text lives in policies/*.yaml. This module checks the shape and refuses
ReliefWeb and DDPM URLs. It does not decide which rules are authoritative.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime
from functools import lru_cache

import yaml

from paths import ROOT

CORPUS_DIR = ROOT / "policies"
LABELS_NAME = "system1_labels.yaml"
RULE_FILES = (
    "mof_relief.yaml",
    "sphere.yaml",
    "safeguarding.yaml",
    "triage.yaml",
)
REQUIRED = (
    "id",
    "status",
    "text_en",
    "source_url",
    "source_excerpt",
    "retrieved",
    "license_note",
    "topic",
    "checks",
)
BANNED_URL_PARTS = ("reliefweb.int", "reliefweb.org", "disaster.go.th", "ddpm.go.th")
RULE_ID = re.compile(r"^[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+$")
STATUSES = {"verified", "unverified"}


@dataclass(frozen=True)
class PolicyRule:
    id: str
    status: str
    text_en: str
    text_th: str
    source_url: str
    source_excerpt: str
    retrieved: str
    license_note: str
    topic: str
    checks: tuple[str, ...]
    caveat: str
    locator: str

    @property
    def verified(self) -> bool:
        return self.status == "verified"


@dataclass(frozen=True)
class TriageLabel:
    id: str
    status: str
    label_en: str
    label_th: str
    hypothesis_en: str
    hypothesis_th: str
    derived_from: tuple[str, ...]
    thai_is_quotation: bool


def _text(value: object, field: str, rule_id: str) -> str:
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10] if isinstance(value, datetime) else value.isoformat()
    if not isinstance(value, str):
        raise ValueError(f"{rule_id}: {field} must be a string.")
    return value.strip()


def _check_url(url: str, rule_id: str, status: str) -> None:
    lowered = url.lower()
    for part in BANNED_URL_PARTS:
        if part in lowered:
            raise ValueError(f"{rule_id}: source URL must not use {part}.")
    if status == "verified" and not url.startswith(("https://", "http://")):
        raise ValueError(f"{rule_id}: a verified rule needs an http(s) source URL.")
    if status == "unverified" and url != "TODO_HUMAN" and not url.startswith(("https://", "http://")):
        raise ValueError(f"{rule_id}: an unverified source URL must be TODO_HUMAN or http(s).")


def _rule_from_mapping(raw: object, source_name: str) -> PolicyRule:
    if not isinstance(raw, dict):
        raise ValueError(f"{source_name}: each rule must be a mapping.")
    rule_id = str(raw.get("id") or source_name)
    missing = [key for key in REQUIRED if key not in raw]
    if missing:
        raise ValueError(f"{rule_id}: missing {', '.join(missing)}.")
    status = _text(raw["status"], "status", rule_id)
    if status not in STATUSES:
        raise ValueError(f"{rule_id}: status must be verified or unverified.")
    if not RULE_ID.match(rule_id):
        raise ValueError(f"{rule_id}: id must be uppercase groups separated by hyphens.")
    text_en = _text(raw["text_en"], "text_en", rule_id)
    text_th = _text(raw.get("text_th") or "", "text_th", rule_id)
    excerpt = _text(raw["source_excerpt"], "source_excerpt", rule_id)
    url = _text(raw["source_url"], "source_url", rule_id)
    retrieved = _text(raw["retrieved"], "retrieved", rule_id)
    license_note = _text(raw["license_note"], "license_note", rule_id)
    topic = _text(raw["topic"], "topic", rule_id)
    caveat = _text(raw.get("caveat") or "", "caveat", rule_id)
    locator = _text(raw.get("locator") or "", "locator", rule_id)
    checks_raw = raw["checks"]
    if not isinstance(checks_raw, list) or not checks_raw:
        raise ValueError(f"{rule_id}: checks must be a non-empty list.")
    checks = tuple(_text(item, "checks", rule_id) for item in checks_raw)
    if not text_en or not excerpt or not license_note:
        raise ValueError(f"{rule_id}: text, excerpt, and licence note must be nonempty.")
    if status == "unverified" and "TODO_HUMAN" not in text_en:
        raise ValueError(f"{rule_id}: an unverified rule must say TODO_HUMAN in text_en.")
    if status == "verified" and "TODO_HUMAN" in text_en:
        raise ValueError(f"{rule_id}: verified text must not contain TODO_HUMAN.")
    _check_url(url, rule_id, status)
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", retrieved):
        raise ValueError(f"{rule_id}: retrieved must be YYYY-MM-DD.")
    return PolicyRule(
        id=rule_id,
        status=status,
        text_en=text_en,
        text_th=text_th,
        source_url=url,
        source_excerpt=excerpt,
        retrieved=retrieved,
        license_note=license_note,
        topic=topic,
        checks=checks,
        caveat=caveat,
        locator=locator,
    )


def parse_rule_document(text: str, source_name: str) -> list[PolicyRule]:
    """Parse one YAML document. The caller owns the bytes this text came from."""
    payload = yaml.safe_load(text)
    if not isinstance(payload, dict) or not isinstance(payload.get("rules"), list):
        raise ValueError(f"{source_name}: expected a mapping with a rules list.")
    rules: list[PolicyRule] = []
    seen: set[str] = set()
    for raw in payload["rules"]:
        rule = _rule_from_mapping(raw, source_name)
        if rule.id in seen:
            raise ValueError(f"Duplicate policy id {rule.id}.")
        seen.add(rule.id)
        rules.append(rule)
    return rules


@lru_cache(maxsize=1)
def load_rules() -> dict[str, PolicyRule]:
    found: dict[str, PolicyRule] = {}
    for name in RULE_FILES:
        text = (CORPUS_DIR / name).read_text(encoding="utf-8")
        for rule in parse_rule_document(text, name):
            if rule.id in found:
                raise ValueError(f"Duplicate policy id {rule.id}.")
            found[rule.id] = rule
    if not found:
        raise ValueError("The policy corpus is empty.")
    return found


def get_rule(rule_id: str) -> PolicyRule:
    rules = load_rules()
    try:
        return rules[rule_id]
    except KeyError:
        raise ValueError(f"Unknown policy rule {rule_id!r}.") from None


def corpus_counts() -> dict[str, int]:
    rules = load_rules().values()
    verified = sum(1 for rule in rules if rule.verified)
    total = len(load_rules())
    return {
        "rules": total,
        "verified": verified,
        "unverified": total - verified,
    }


def parse_labels_document(text: str, rules: dict[str, PolicyRule]) -> list[TriageLabel]:
    payload = yaml.safe_load(text)
    if not isinstance(payload, dict) or not isinstance(payload.get("labels"), list):
        raise ValueError("system1_labels.yaml needs a labels list.")
    labels: list[TriageLabel] = []
    seen: set[str] = set()
    for raw in payload["labels"]:
        if not isinstance(raw, dict):
            raise ValueError("Each System 1 label must be a mapping.")
        label_id = str(raw.get("id") or "")
        for key in (
            "id",
            "status",
            "label_en",
            "label_th",
            "hypothesis_en",
            "hypothesis_th",
            "derived_from",
        ):
            if key not in raw:
                raise ValueError(f"{label_id or 'label'}: missing {key}.")
        status = _text(raw["status"], "status", label_id)
        if status not in STATUSES:
            raise ValueError(f"{label_id}: status must be verified or unverified.")
        hypothesis_en = _text(raw["hypothesis_en"], "hypothesis_en", label_id)
        hypothesis_th = _text(raw["hypothesis_th"], "hypothesis_th", label_id)
        if status == "unverified" and "TODO_HUMAN" not in hypothesis_en:
            raise ValueError(f"{label_id}: an unverified hypothesis must say TODO_HUMAN.")
        derived_raw = raw["derived_from"]
        if not isinstance(derived_raw, list) or not derived_raw:
            raise ValueError(f"{label_id}: derived_from must name at least one rule.")
        derived = tuple(_text(item, "derived_from", label_id) for item in derived_raw)
        missing = [item for item in derived if item not in rules]
        if missing:
            raise ValueError(f"{label_id}: unknown rule ids {', '.join(missing)}.")
        if label_id in seen:
            raise ValueError(f"Duplicate System 1 label {label_id}.")
        seen.add(label_id)
        labels.append(
            TriageLabel(
                id=label_id,
                status=status,
                label_en=_text(raw["label_en"], "label_en", label_id),
                label_th=_text(raw["label_th"], "label_th", label_id),
                hypothesis_en=hypothesis_en,
                hypothesis_th=hypothesis_th,
                derived_from=derived,
                thai_is_quotation=bool(raw.get("thai_is_quotation", False)),
            )
        )
    return labels


@lru_cache(maxsize=1)
def load_labels() -> dict[str, TriageLabel]:
    text = (CORPUS_DIR / LABELS_NAME).read_text(encoding="utf-8")
    return {label.id: label for label in parse_labels_document(text, load_rules())}
