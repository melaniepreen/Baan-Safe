"""Learned routing overlay. Owner: Moly.

Written by the RL loop (eval/rl/). Read on the live path only when
`RL_OVERLAY` names a file, or when a caller passes an `Overlay` into
`gateway.handle`. Off by default. Schema `baansafe.rl_overlay.v1`.

Narrow signatures promote (a repeated System 2 decision becomes a System 1
rule or a recommendation). Coarse signatures demote (System 1 under-triage
sends the pattern back to System 2).
"""

from __future__ import annotations

import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from config.settings import load_yaml
from contracts.models import CaseState
from system1.extract import NUMBER_WORDS

SCHEMA = "baansafe.rl_overlay.v1"
ENV_VAR = "RL_OVERLAY"

_WORD = re.compile(r"[a-z']+")

# Extraction provenance and enrichment data flags are not caller signal.
EXCLUDED_FLAGS = frozenset(
    {
        "keyword_extraction",
        "in_active_flood_extent",
        "repeat_flood_area",
        "heavy_rain_forecast",
        "heavy_rain_observed",
    }
)

STOPWORDS = frozenset(
    "a an the is are was were we i my our us me you they them it this that "
    "and or of to in on at for with from since has have had be been do does "
    "did can could will would should there here not no yes so but what which "
    "who when where how about just really please".split()
)


def _min_confidence() -> float:
    return float(load_yaml("escalation.yaml").get("system_1_min_confidence") or 0.8)


def coarse_signature(case: CaseState) -> str:
    """District- and wording-free shape of the case."""
    fields = case.fields
    needs = ",".join(sorted(need.value for need in fields.needs)) or "none"
    vuln = ",".join(sorted(fields.vulnerable)) or "none"
    danger = ",".join(sorted(fields.danger)) or "none"
    medical = "1" if fields.medical else "0"
    if fields.location is None or fields.location_confidence is None:
        loc = "none"
    elif fields.location_confidence < _min_confidence():
        loc = "low"
    else:
        loc = "ok"
    people = "known" if fields.people_count is not None else "unknown"
    flags = ",".join(sorted(set(case.policy_flags) - EXCLUDED_FLAGS)) or "none"
    return (
        f"needs={needs}|vuln={vuln}|danger={danger}|medical={medical}"
        f"|loc={loc}|people={people}|flags={flags}"
    )


def narrow_signature(case: CaseState) -> str:
    """Coarse signature plus a hash of the caller's content tokens."""
    ignored = set(STOPWORDS) | set(NUMBER_WORDS)
    if case.fields.location:
        ignored |= set(_WORD.findall(case.fields.location.lower()))
    tokens = {
        token
        for turn in case.transcript
        if turn.speaker == "caller"
        for token in _WORD.findall(turn.text.lower())
        if token not in ignored
    }
    digest = hashlib.sha1(" ".join(sorted(tokens)).encode("utf-8")).hexdigest()[:12]
    return f"{coarse_signature(case)}|text={digest}"


@dataclass
class Overlay:
    graduation_threshold: int = 2
    graduated: dict[str, dict[str, Any]] = field(default_factory=dict)
    recommendations: dict[str, dict[str, Any]] = field(default_factory=dict)
    demoted: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"schema": SCHEMA, **asdict(self)}

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> Overlay:
        if payload.get("schema") != SCHEMA:
            raise ValueError(f"overlay schema is not {SCHEMA}")
        return cls(
            graduation_threshold=int(payload.get("graduation_threshold") or 2),
            graduated=dict(payload.get("graduated") or {}),
            recommendations=dict(payload.get("recommendations") or {}),
            demoted=dict(payload.get("demoted") or {}),
        )


def load(path: str | Path) -> Overlay:
    return Overlay.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def save(overlay: Overlay, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(overlay.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


_env_cache: tuple[str, float, Overlay] | None = None


def load_from_env() -> Overlay | None:
    """RL_OVERLAY opt-in, cached by file mtime. None means no overlay."""
    global _env_cache
    raw = os.environ.get(ENV_VAR, "").strip()
    if not raw:
        _env_cache = None
        return None
    path = Path(raw)
    mtime = path.stat().st_mtime
    if _env_cache and _env_cache[0] == str(path) and _env_cache[1] == mtime:
        return _env_cache[2]
    overlay = load(path)
    _env_cache = (str(path), mtime, overlay)
    return overlay
