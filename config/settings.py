"""Load YAML config. Product decisions fail loudly when still TODO_HUMAN."""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import yaml

from paths import ROOT

UNSET = "TODO_HUMAN"
DECISIONS_PATH = ROOT / "config" / "decisions.yaml"


class DecisionRequired(RuntimeError):
    """Raised when code needs a human decision that is still TODO_HUMAN."""


def load_yaml(name: str) -> dict[str, Any]:
    path = ROOT / "config" / name
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError(f"{path} must be a mapping")
    return data


@lru_cache(maxsize=1)
def decisions() -> dict[str, Any]:
    return load_yaml("decisions.yaml")


def _lookup(path: str) -> Any:
    node: Any = decisions()
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise DecisionRequired(
                f"config/decisions.yaml has no '{path}'. A human must add it."
            )
        node = node[part]
    return node


def is_unset(value: Any) -> bool:
    return value is None or value == UNSET or value == ""


def require_decision(path: str) -> Any:
    """Return a decision value, or raise if a human has not set it."""
    value = _lookup(path)
    if is_unset(value):
        raise DecisionRequired(
            f"config/decisions.yaml:{path} is {UNSET}. "
            "A human must set it before this code can run."
        )
    return value


def unset_decisions(paths: list[str]) -> list[str]:
    missing: list[str] = []
    for path in paths:
        try:
            value = _lookup(path)
        except DecisionRequired:
            missing.append(path)
            continue
        if is_unset(value):
            missing.append(path)
    return missing


def iter_decision_leaves(node: Any | None = None, prefix: str = "") -> list[tuple[str, Any]]:
    if node is None:
        node = decisions()
    leaves: list[tuple[str, Any]] = []
    if isinstance(node, dict):
        for key, value in node.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            if isinstance(value, dict):
                leaves.extend(iter_decision_leaves(value, path))
            else:
                leaves.append((path, value))
    return leaves
