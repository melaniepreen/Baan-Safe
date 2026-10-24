"""Normalised policy records. Adapters fill these. They do not invent text."""

from __future__ import annotations

from dataclasses import dataclass

DOMAINS = frozenset({"aid_eligibility", "safeguarding", "triage"})
JURISDICTIONS = frozenset({"TH", "intl"})
LANGS = frozenset({"en", "th"})


@dataclass(frozen=True)
class LanguageText:
    text: str
    excerpt: str
    quotation: bool

    def public(self) -> dict[str, object]:
        return {
            "text": self.text,
            "excerpt": self.excerpt,
            "quotation": self.quotation,
        }


@dataclass(frozen=True)
class NormalisedRule:
    rule_id: str
    jurisdiction: str
    domain: str
    languages: dict[str, LanguageText]
    effective_from: str | None
    effective_to: str | None
    effective_stated: str | None
    effective_note: str
    source_url: str
    license: str
    verified: bool
    source_id: str
    source_version: str
    retrieved: str
    status: str
    topic: str
    checks: tuple[str, ...]
    caveat: str
    locator: str
    source_excerpt: str

    @property
    def id(self) -> str:
        return self.rule_id

    def public(self, lang: str = "en") -> dict[str, object]:
        chosen = self.languages[lang]
        return {
            "rule_id": self.rule_id,
            "jurisdiction": self.jurisdiction,
            "domain": self.domain,
            "topic": self.topic,
            "languages": {code: item.public() for code, item in self.languages.items()},
            "text": chosen.text,
            "language": lang,
            "language_available": bool(chosen.text),
            "effective_from": self.effective_from,
            "effective_to": self.effective_to,
            "effective_stated": self.effective_stated,
            "effective_note": self.effective_note,
            "source_url": self.source_url,
            "license": self.license,
            "verified": self.verified,
            "status": self.status,
            "source_id": self.source_id,
            "source_version": self.source_version,
            "retrieved": self.retrieved,
            "checks": list(self.checks),
            "caveat": self.caveat,
            "locator": self.locator,
            "source_excerpt": self.source_excerpt,
        }


@dataclass(frozen=True)
class NormalisedLabel:
    label_id: str
    status: str
    verified: bool
    label_en: str
    label_th: str
    hypothesis_en: str
    hypothesis_th: str
    derived_from: tuple[str, ...]
    thai_is_quotation: bool
    source_id: str
    source_version: str

    def public(self, lang: str = "en") -> dict[str, object]:
        hypothesis = self.hypothesis_th if lang == "th" else self.hypothesis_en
        label = self.label_th if lang == "th" else self.label_en
        return {
            "id": self.label_id,
            "status": self.status,
            "verified": self.verified,
            "language": lang,
            "label": label,
            "hypothesis": hypothesis,
            "languages": {
                "en": {"label": self.label_en, "hypothesis": self.hypothesis_en},
                "th": {
                    "label": self.label_th,
                    "hypothesis": self.hypothesis_th,
                    "quotation": self.thai_is_quotation,
                },
            },
            "derived_from": list(self.derived_from),
            "thai_is_quotation": self.thai_is_quotation,
            "source_id": self.source_id,
            "source_version": self.source_version,
        }
