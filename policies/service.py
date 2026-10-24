"""Policy service. Adapters in, one cached corpus out.

The authoritative demo set stays a human decision. This service can load
every normalised rule by id. It does not choose which of them bind the demo.

An eval run pins the corpus version. Later reads with that version or run id
replay the stored snapshot, including after the process restarts, as long as
the pin file is still on disk.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path

from paths import ROOT
from policies.schema import LANGS, LanguageText, NormalisedLabel, NormalisedRule
from policies.sources.base import PolicySourceAdapter
from policies.sources.candidates import CANDIDATES
from policies.sources.local_yaml import LocalYamlAdapter

_VERSION = re.compile(r"^[a-f0-9]{64}$")
_RUN = re.compile(r"^[A-Za-z0-9._-]{1,80}$")
_TOKEN = re.compile(r"[a-z0-9]{4,}")
_RULE_ID = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+")
_STOP = frozenset(
    {
        "that",
        "this",
        "with",
        "from",
        "they",
        "them",
        "their",
        "than",
        "then",
        "into",
        "under",
        "does",
        "have",
        "been",
        "were",
        "will",
        "your",
        "about",
        "after",
        "before",
        "which",
        "when",
        "where",
        "more",
        "must",
        "only",
        "such",
        "also",
        "each",
        "other",
        "over",
        "rule",
        "rules",
    }
)
_MATCH_LIMIT = 8


class PolicyError(Exception):
    status = 400

    def __init__(self, detail: object):
        super().__init__(str(detail))
        self.detail = detail


class UnknownRule(PolicyError):
    status = 404


class UnknownPin(PolicyError):
    status = 404


class VersionMismatch(PolicyError):
    status = 409


@dataclass
class Snapshot:
    version: str
    rules: dict[str, NormalisedRule]
    labels: dict[str, NormalisedLabel]
    adapters: dict[str, str]
    origin: str

    def public_meta(self) -> dict[str, object]:
        verified = sum(1 for rule in self.rules.values() if rule.verified)
        return {
            "version": self.version,
            "origin": self.origin,
            "rules": len(self.rules),
            "verified": verified,
            "unverified": len(self.rules) - verified,
            "labels": len(self.labels),
            "adapters": [
                {"source_id": source_id, "version": version}
                for source_id, version in self.adapters.items()
            ],
        }


def _canonical_rule(rule: NormalisedRule) -> dict[str, object]:
    return {
        "rule_id": rule.rule_id,
        "jurisdiction": rule.jurisdiction,
        "domain": rule.domain,
        "languages": {
            code: {"text": item.text, "excerpt": item.excerpt, "quotation": item.quotation}
            for code, item in sorted(rule.languages.items())
        },
        "effective_from": rule.effective_from,
        "effective_to": rule.effective_to,
        "effective_stated": rule.effective_stated,
        "effective_note": rule.effective_note,
        "source_url": rule.source_url,
        "license": rule.license,
        "verified": rule.verified,
        "source_id": rule.source_id,
        "retrieved": rule.retrieved,
        "status": rule.status,
        "topic": rule.topic,
        "checks": list(rule.checks),
        "caveat": rule.caveat,
        "locator": rule.locator,
        "source_excerpt": rule.source_excerpt,
    }


def _canonical_label(label: NormalisedLabel) -> dict[str, object]:
    return {
        "id": label.label_id,
        "status": label.status,
        "hypothesis_en": label.hypothesis_en,
        "hypothesis_th": label.hypothesis_th,
        "label_en": label.label_en,
        "label_th": label.label_th,
        "derived_from": list(label.derived_from),
        "thai_is_quotation": label.thai_is_quotation,
        "source_id": label.source_id,
    }


def _hash_snapshot(
    rules: list[NormalisedRule],
    labels: list[NormalisedLabel],
    adapters: dict[str, str],
) -> str:
    payload = {
        "adapters": adapters,
        "rules": [_canonical_rule(rule) for rule in rules],
        "labels": [_canonical_label(label) for label in labels],
    }
    blob = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _check_version(version: str | None) -> None:
    if version is not None and not _VERSION.fullmatch(version):
        raise PolicyError("version must be a 64-character sha256 hex digest.")


def _check_run(run_id: str | None) -> None:
    if run_id is not None and not _RUN.fullmatch(run_id):
        raise PolicyError("run_id must be 1-80 characters of letters, digits, dot, underscore, or hyphen.")


def _check_lang(lang: str) -> None:
    if lang not in LANGS:
        raise PolicyError("lang must be en or th.")


def _check_scope(jurisdiction: str | None, domain: str | None) -> None:
    if jurisdiction is not None and jurisdiction not in {"TH", "intl"}:
        raise PolicyError("jurisdiction must be TH or intl.")
    if domain is not None and domain not in {"aid_eligibility", "safeguarding", "triage"}:
        raise PolicyError("domain must be aid_eligibility, safeguarding, or triage.")


def _terms(text: str) -> set[str]:
    found: set[str] = set()
    for token in _TOKEN.findall(text.lower()):
        if token in _STOP or token.isdigit():
            continue
        if token.endswith("s") and len(token) > 4:
            found.add(token[:-1])
        found.add(token)
    return found


class PolicyService:
    def __init__(
        self,
        adapters: list[PolicySourceAdapter] | None = None,
        pin_dir: Path | None = None,
    ) -> None:
        self.adapters = [LocalYamlAdapter()] if adapters is None else list(adapters)
        self.pin_dir = pin_dir if pin_dir is not None else ROOT / "var" / "policy-pins"
        self._memory: dict[str, Snapshot] = {}
        self._runs: dict[str, str] = {}
        self._current: Snapshot | None = None
        self._list_cache: dict[tuple, dict[str, object]] = {}

    def current(self) -> Snapshot:
        if self._current is None:
            self._current = self._build("live")
            self._memory[self._current.version] = self._current
            self._write_snapshot(self._current)
        return self._current

    def pin_run(self, run_id: str) -> dict[str, object]:
        """Store the current corpus under an eval run id."""
        _check_run(run_id)
        if run_id is None:
            raise PolicyError("run_id is required.")
        snap = self.current()
        self._runs[run_id] = snap.version
        self.pin_dir.mkdir(parents=True, exist_ok=True)
        (self.pin_dir / "runs").mkdir(parents=True, exist_ok=True)
        (self.pin_dir / "runs" / f"{run_id}.json").write_text(
            json.dumps({"run_id": run_id, "version": snap.version}, sort_keys=True),
            encoding="utf-8",
        )
        self._write_snapshot(snap)
        return {"run_id": run_id, "version": snap.version, "origin": "pin"}

    def list_rules(
        self,
        *,
        jurisdiction: str | None = None,
        domain: str | None = None,
        lang: str = "en",
        version: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, object]:
        _check_lang(lang)
        _check_scope(jurisdiction, domain)
        snap = self._resolve(version, run_id)
        key = (snap.version, snap.origin, jurisdiction, domain, lang, "list")
        cached = self._list_cache.get(key)
        if cached is not None:
            return cached
        chosen = [
            rule
            for rule in snap.rules.values()
            if (jurisdiction is None or rule.jurisdiction == jurisdiction)
            and (domain is None or rule.domain == domain)
        ]
        chosen.sort(key=lambda rule: rule.rule_id)
        body = {
            **snap.public_meta(),
            "origin": snap.origin,
            "jurisdiction": jurisdiction,
            "domain": domain,
            "lang": lang,
            "count": len(chosen),
            "rules": [rule.public(lang) for rule in chosen],
        }
        self._remember(key, body)
        return body

    def get_rule(
        self,
        rule_id: str,
        *,
        lang: str = "en",
        version: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, object]:
        _check_lang(lang)
        snap = self._resolve(version, run_id)
        rule = snap.rules.get(rule_id)
        if rule is None:
            raise UnknownRule(f"Unknown policy rule {rule_id!r}.")
        return {**snap.public_meta(), "origin": snap.origin, "rule": rule.public(lang)}

    def require_rule(self, rule_id: str, *, version: str | None = None) -> NormalisedRule:
        snap = self._resolve(version, None)
        rule = snap.rules.get(rule_id)
        if rule is None:
            raise UnknownRule(f"Unknown policy rule {rule_id!r}.")
        return rule

    def known_ids(self) -> dict[str, NormalisedRule]:
        return self.current().rules

    def labels(
        self,
        *,
        lang: str = "en",
        version: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, object]:
        _check_lang(lang)
        snap = self._resolve(version, run_id)
        key = (snap.version, snap.origin, lang, "labels")
        cached = self._list_cache.get(key)
        if cached is not None:
            return cached
        rows = [label.public(lang) for label in snap.labels.values()]
        rows.sort(key=lambda item: str(item["id"]))
        body = {
            **snap.public_meta(),
            "origin": snap.origin,
            "lang": lang,
            "count": len(rows),
            "labels": rows,
        }
        self._remember(key, body)
        return body

    def match(
        self,
        *,
        evidence: str = "",
        claim: str = "",
        jurisdiction: str | None = None,
        domain: str | None = None,
        lang: str = "en",
        version: str | None = None,
        run_id: str | None = None,
    ) -> dict[str, object]:
        """Candidate rules for a later Sapling call. Not a verdict."""
        _check_lang(lang)
        _check_scope(jurisdiction, domain)
        evidence = evidence.strip()
        claim = claim.strip()
        if not evidence and not claim:
            raise PolicyError("evidence or claim is required.")
        snap = self._resolve(version, run_id)
        cache_key = (snap.version, snap.origin, jurisdiction, domain, lang, evidence, claim, "match")
        cached = self._list_cache.get(cache_key)
        if cached is not None:
            return cached
        blob = f"{evidence}\n{claim}"
        named = [token for token in _RULE_ID.findall(blob) if token in snap.rules]
        terms = _terms(blob)
        ranked: list[tuple[int, str, list[str], NormalisedRule]] = []
        for rule in snap.rules.values():
            if jurisdiction is not None and rule.jurisdiction != jurisdiction:
                continue
            if domain is not None and rule.domain != domain:
                continue
            score = 0
            matched: list[str] = []
            if rule.rule_id in named:
                score += 100
                matched.append(rule.rule_id)
            hay = _terms(
                " ".join(
                    (
                        rule.languages["en"].text,
                        rule.languages["th"].text,
                        rule.source_excerpt,
                    )
                )
            )
            overlap = sorted(terms & hay)
            if overlap:
                score += len(overlap)
                matched.extend(overlap)
            if score <= 0:
                continue
            ranked.append((score, rule.rule_id, matched, rule))
        ranked.sort(key=lambda item: (-item[0], item[1]))
        kept = ranked[:_MATCH_LIMIT]
        omitted = [item[1] for item in ranked[_MATCH_LIMIT:]]
        body = {
            **snap.public_meta(),
            "origin": snap.origin,
            "lang": lang,
            "jurisdiction": jurisdiction,
            "domain": domain,
            "count": len(kept),
            "omitted_rule_ids": omitted,
            "note": (
                "Candidates are term overlap for a Sapling check. "
                "Overlap is not support, and an empty list is not a denial. "
                "policies.authoritative_set is still a human decision."
            ),
            "candidates": [
                {
                    "rule_id": rule.rule_id,
                    "score": score,
                    "matched_terms": matched[:12],
                    "verified": rule.verified,
                    "jurisdiction": rule.jurisdiction,
                    "domain": rule.domain,
                    "rule": rule.public(lang),
                }
                for score, _rule_id, matched, rule in kept
            ],
        }
        self._remember(cache_key, body)
        return body

    def sources(self) -> dict[str, object]:
        snap = self.current()
        live = []
        for source_id, version in snap.adapters.items():
            count = sum(1 for rule in snap.rules.values() if rule.source_id == source_id)
            live.append(
                {
                    "source_id": source_id,
                    "version": version,
                    "rules": count,
                    "status": "live",
                }
            )
        candidates = []
        for row in CANDIDATES:
            candidates.append({**row, "status": "candidate", "todo": "TODO_HUMAN"})
        return {
            "version": snap.version,
            "live": live,
            "candidates": candidates,
        }

    def _resolve(self, version: str | None, run_id: str | None) -> Snapshot:
        _check_version(version)
        _check_run(run_id)
        if run_id is not None:
            pinned = self._run_version(run_id)
            if version is not None and version != pinned:
                raise VersionMismatch(
                    {
                        "message": "run_id is pinned to a different corpus version.",
                        "loaded_version": pinned,
                    }
                )
            return self._load_version(pinned, origin="pin")
        if version is None:
            return self.current()
        current = self.current()
        if version == current.version:
            return current
        try:
            return self._load_version(version, origin="pin")
        except UnknownPin:
            raise VersionMismatch(
                {
                    "message": "Corpus version does not match the loaded or pinned snapshot.",
                    "loaded_version": current.version,
                }
            ) from None

    def _run_version(self, run_id: str) -> str:
        cached = self._runs.get(run_id)
        if cached:
            return cached
        path = self.pin_dir / "runs" / f"{run_id}.json"
        if not path.is_file():
            raise UnknownPin(f"Unknown policy pin {run_id!r}.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        version = str(payload.get("version") or "")
        if not _VERSION.fullmatch(version):
            raise PolicyError(f"Pin file for {run_id} has no corpus version.")
        self._runs[run_id] = version
        return version

    def _load_version(self, version: str, *, origin: str) -> Snapshot:
        cached = self._memory.get(version)
        if cached is not None:
            if cached.origin == origin:
                return cached
            return Snapshot(
                version=cached.version,
                rules=cached.rules,
                labels=cached.labels,
                adapters=cached.adapters,
                origin=origin,
            )
        path = self.pin_dir / f"{version}.json"
        if not path.is_file():
            raise UnknownPin(f"Unknown corpus version {version}.")
        payload = json.loads(path.read_text(encoding="utf-8"))
        snap = _snapshot_from_json(payload, origin=origin)
        if snap.version != version:
            raise PolicyError("Pinned snapshot hash does not match its filename.")
        self._memory[version] = snap
        return snap

    def _build(self, origin: str) -> Snapshot:
        rules: list[NormalisedRule] = []
        labels: list[NormalisedLabel] = []
        adapters: dict[str, str] = {}
        seen_rules: set[str] = set()
        seen_labels: set[str] = set()
        for adapter in self.adapters:
            fetched = adapter.fetch()
            source_version = adapter.version(fetched)
            if adapter.source_id in adapters:
                raise ValueError(f"Duplicate policy source {adapter.source_id}.")
            adapters[adapter.source_id] = source_version
            got_rules, got_labels = adapter.normalise(fetched, source_version=source_version)
            for rule in got_rules:
                if rule.rule_id in seen_rules:
                    raise ValueError(f"Duplicate policy id {rule.rule_id}.")
                seen_rules.add(rule.rule_id)
                rules.append(rule)
            for label in got_labels:
                if label.label_id in seen_labels:
                    raise ValueError(f"Duplicate System 1 label {label.label_id}.")
                seen_labels.add(label.label_id)
                labels.append(label)
        if not rules:
            raise ValueError("The policy corpus is empty.")
        version = _hash_snapshot(rules, labels, adapters)
        return Snapshot(
            version=version,
            rules={rule.rule_id: rule for rule in rules},
            labels={label.label_id: label for label in labels},
            adapters=adapters,
            origin=origin,
        )

    def _write_snapshot(self, snap: Snapshot) -> None:
        self.pin_dir.mkdir(parents=True, exist_ok=True)
        path = self.pin_dir / f"{snap.version}.json"
        if path.is_file():
            return
        payload = {
            "version": snap.version,
            "adapters": snap.adapters,
            "rules": [_canonical_rule(rule) for rule in snap.rules.values()],
            "labels": [_canonical_label(label) for label in snap.labels.values()],
        }
        path.write_text(
            json.dumps(payload, ensure_ascii=False, sort_keys=True),
            encoding="utf-8",
        )

    def _remember(self, key: tuple, body: dict[str, object]) -> None:
        if len(self._list_cache) > 64:
            self._list_cache.clear()
        self._list_cache[key] = body


def _language(raw: object) -> dict[str, object]:
    if not isinstance(raw, dict):
        raise PolicyError("Pinned language text is not a mapping.")
    return raw


def _snapshot_from_json(payload: object, *, origin: str) -> Snapshot:
    if not isinstance(payload, dict):
        raise PolicyError("Pinned snapshot is not a mapping.")
    version = str(payload.get("version") or "")
    adapters = payload.get("adapters")
    raw_rules = payload.get("rules")
    raw_labels = payload.get("labels")
    if not isinstance(adapters, dict) or not isinstance(raw_rules, list) or not isinstance(raw_labels, list):
        raise PolicyError("Pinned snapshot is missing adapters, rules, or labels.")
    rules: list[NormalisedRule] = []
    for raw in raw_rules:
        if not isinstance(raw, dict):
            raise PolicyError("Pinned rule is not a mapping.")
        languages_raw = raw.get("languages")
        if not isinstance(languages_raw, dict):
            raise PolicyError("Pinned rule has no languages.")
        languages = {}
        for code in ("en", "th"):
            item = _language(languages_raw.get(code))
            languages[code] = LanguageText(
                text=str(item.get("text") or ""),
                excerpt=str(item.get("excerpt") or ""),
                quotation=bool(item.get("quotation")),
            )
        checks = raw.get("checks")
        if not isinstance(checks, list):
            checks = []
        rules.append(
            NormalisedRule(
                rule_id=str(raw.get("rule_id") or ""),
                jurisdiction=str(raw.get("jurisdiction") or ""),
                domain=str(raw.get("domain") or ""),
                languages=languages,
                effective_from=raw.get("effective_from") if isinstance(raw.get("effective_from"), str) else None,
                effective_to=raw.get("effective_to") if isinstance(raw.get("effective_to"), str) else None,
                effective_stated=raw.get("effective_stated") if isinstance(raw.get("effective_stated"), str) else None,
                effective_note=str(raw.get("effective_note") or ""),
                source_url=str(raw.get("source_url") or ""),
                license=str(raw.get("license") or ""),
                verified=bool(raw.get("verified")),
                source_id=str(raw.get("source_id") or ""),
                source_version=str(adapters.get(str(raw.get("source_id") or ""), "")),
                retrieved=str(raw.get("retrieved") or ""),
                status=str(raw.get("status") or ""),
                topic=str(raw.get("topic") or ""),
                checks=tuple(str(item) for item in checks),
                caveat=str(raw.get("caveat") or ""),
                locator=str(raw.get("locator") or ""),
                source_excerpt=str(raw.get("source_excerpt") or ""),
            )
        )
    labels: list[NormalisedLabel] = []
    for raw in raw_labels:
        if not isinstance(raw, dict):
            raise PolicyError("Pinned label is not a mapping.")
        derived = raw.get("derived_from")
        if not isinstance(derived, list):
            derived = []
        labels.append(
            NormalisedLabel(
                label_id=str(raw.get("id") or ""),
                status=str(raw.get("status") or ""),
                verified=str(raw.get("status") or "") == "verified",
                label_en=str(raw.get("label_en") or ""),
                label_th=str(raw.get("label_th") or ""),
                hypothesis_en=str(raw.get("hypothesis_en") or ""),
                hypothesis_th=str(raw.get("hypothesis_th") or ""),
                derived_from=tuple(str(item) for item in derived),
                thai_is_quotation=bool(raw.get("thai_is_quotation")),
                source_id=str(raw.get("source_id") or ""),
                source_version=str(adapters.get(str(raw.get("source_id") or ""), "")),
            )
        )
    adapter_versions = {str(key): str(value) for key, value in adapters.items()}
    hashed = _hash_snapshot(rules, labels, adapter_versions)
    if version and version != hashed:
        raise PolicyError("Pinned snapshot hash does not match its contents.")
    return Snapshot(
        version=hashed,
        rules={rule.rule_id: rule for rule in rules},
        labels={label.label_id: label for label in labels},
        adapters=adapter_versions,
        origin=origin,
    )


_SERVICE: PolicyService | None = None


def get_service() -> PolicyService:
    global _SERVICE
    if _SERVICE is None:
        _SERVICE = PolicyService()
    return _SERVICE
