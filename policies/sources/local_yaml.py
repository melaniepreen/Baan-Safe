"""First live adapter: the checked-in YAML corpus.

File bytes are the payload. The version is their hash. Normalisation copies
fields that are already in those files. It does not translate missing Thai
and it does not turn a Buddhist-era date into a Gregorian ISO date.
"""

from __future__ import annotations

import hashlib

from policies.corpus import (
    LABELS_NAME,
    RULE_FILES,
    PolicyRule,
    TriageLabel,
    parse_labels_document,
    parse_rule_document,
)
from policies.schema import DOMAINS, LanguageText, NormalisedLabel, NormalisedRule
from paths import ROOT

CORPUS_DIR = ROOT / "policies"

# topic in the YAML is finer than the three service domains.
_DOMAIN = {
    "aid_eligibility": "aid_eligibility",
    "denial": "aid_eligibility",
    "safeguarding": "safeguarding",
    "triage": "triage",
    "wash": "aid_eligibility",
    "food": "aid_eligibility",
    "shelter": "aid_eligibility",
}
_JURISDICTION = {
    "mof_relief.yaml": "TH",
    "triage.yaml": "TH",
    "sphere.yaml": "intl",
    "safeguarding.yaml": "intl",
}
_FILES = (*RULE_FILES, LABELS_NAME)


def _thai(text: str) -> bool:
    return any("\u0e00" <= char <= "\u0e7f" for char in text)


def _languages(rule: PolicyRule) -> dict[str, LanguageText]:
    excerpt = rule.source_excerpt
    thai_excerpt = excerpt if _thai(excerpt) else ""
    en_excerpt = "" if _thai(excerpt) else excerpt
    return {
        "en": LanguageText(text=rule.text_en, excerpt=en_excerpt, quotation=False),
        "th": LanguageText(text=rule.text_th, excerpt=thai_excerpt, quotation=bool(rule.text_th)),
    }


def _effective(rule: PolicyRule) -> tuple[str | None, str]:
    """Clause 2 states the instrument date. Other clauses do not repeat it."""
    if not rule.id.startswith("MOF-2569"):
        return None, ""
    stated = "6 March B.E. 2569"
    if rule.id == "MOF-2569-EFFECTIVE":
        note = (
            "This rule is clause 2. The date numerals in the excerpt are clear. "
            "The verbs around them are damaged. The PDF does not print a Gregorian ISO date."
        )
    else:
        note = (
            "Clause 2 of the B.E. 2569 criteria states this instrument's date. "
            "This clause does not restate it. The PDF does not print a Gregorian ISO date."
        )
    return stated, note


def _rule(rule: PolicyRule, source_name: str, source_version: str) -> NormalisedRule:
    domain = _DOMAIN.get(rule.topic)
    if domain not in DOMAINS:
        raise ValueError(f"{rule.id}: topic {rule.topic!r} has no domain mapping.")
    jurisdiction = _JURISDICTION.get(source_name)
    if jurisdiction not in {"TH", "intl"}:
        raise ValueError(f"{source_name}: no jurisdiction mapping.")
    stated, note = _effective(rule)
    return NormalisedRule(
        rule_id=rule.id,
        jurisdiction=jurisdiction,
        domain=domain,
        languages=_languages(rule),
        effective_from=None,
        effective_to=None,
        effective_stated=stated,
        effective_note=note,
        source_url=rule.source_url,
        license=rule.license_note,
        verified=rule.verified,
        source_id="local_yaml",
        source_version=source_version,
        retrieved=rule.retrieved,
        status=rule.status,
        topic=rule.topic,
        checks=rule.checks,
        caveat=rule.caveat,
        locator=rule.locator,
        source_excerpt=rule.source_excerpt,
    )


def _label(label: TriageLabel, source_version: str) -> NormalisedLabel:
    return NormalisedLabel(
        label_id=label.id,
        status=label.status,
        verified=label.status == "verified",
        label_en=label.label_en,
        label_th=label.label_th,
        hypothesis_en=label.hypothesis_en,
        hypothesis_th=label.hypothesis_th,
        derived_from=label.derived_from,
        thai_is_quotation=label.thai_is_quotation,
        source_id="local_yaml",
        source_version=source_version,
    )


class LocalYamlAdapter:
    source_id = "local_yaml"

    def fetch(self) -> dict[str, object]:
        files = {
            name: (CORPUS_DIR / name).read_bytes()
            for name in _FILES
        }
        return {"files": files}

    def version(self, fetched: dict[str, object]) -> str:
        files = fetched.get("files")
        if not isinstance(files, dict):
            raise ValueError("local_yaml fetch did not return files.")
        digest = hashlib.sha256()
        for name in _FILES:
            blob = files.get(name)
            if not isinstance(blob, (bytes, bytearray)):
                raise ValueError(f"local_yaml is missing {name}.")
            digest.update(name.encode("utf-8"))
            digest.update(b"\0")
            digest.update(blob)
        return digest.hexdigest()

    def normalise(
        self,
        fetched: dict[str, object],
        *,
        source_version: str,
    ) -> tuple[list[NormalisedRule], list[NormalisedLabel]]:
        files = fetched.get("files")
        if not isinstance(files, dict):
            raise ValueError("local_yaml fetch did not return files.")
        rules: list[NormalisedRule] = []
        by_id: dict[str, PolicyRule] = {}
        for name in RULE_FILES:
            blob = files.get(name)
            if not isinstance(blob, (bytes, bytearray)):
                raise ValueError(f"local_yaml is missing {name}.")
            parsed = parse_rule_document(blob.decode("utf-8"), name)
            for rule in parsed:
                if rule.id in by_id:
                    raise ValueError(f"Duplicate policy id {rule.id}.")
                by_id[rule.id] = rule
                rules.append(_rule(rule, name, source_version))
        label_blob = files.get(LABELS_NAME)
        if not isinstance(label_blob, (bytes, bytearray)):
            raise ValueError(f"local_yaml is missing {LABELS_NAME}.")
        labels = [
            _label(label, source_version)
            for label in parse_labels_document(label_blob.decode("utf-8"), by_id)
        ]
        return rules, labels
