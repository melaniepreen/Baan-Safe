"""Read Modal choices from the environment or config/decisions.yaml.

A value of TODO_HUMAN is refused. Nothing in this module picks a model,
a GPU, or a price. Secrets are read from the process environment, which
Modal injects from modal.Secret, and this module never prints them.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml

UNSET = "TODO_HUMAN"

HF_SECRET_NAME = "baansafe-hf"
MUBIT_SECRET_NAME = "baansafe-mubit"
VERSIONS_VOLUME = "baansafe-versions"
HF_CACHE_VOLUME = "baansafe-hf-cache"

ALLOWED_GPUS = (
    "T4",
    "L4",
    "A10",
    "L40S",
    "A100",
    "A100-40GB",
    "A100-80GB",
    "H100",
    "H100!",
    "H200",
)
QUANTS = ("bf16", "fp8", "awq")
SECRET_ENV_NAMES = ("HF_TOKEN", "MUBIT_API_KEY", "S2_SERVE_API_KEY", "OPENROUTER_API_KEY")


class UnsetDecision(RuntimeError):
    """A human has not set the model id or the GPU."""


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def decisions_path() -> Path:
    override = os.environ.get("BAANSAFE_DECISIONS", "").strip()
    if override:
        return Path(override)
    local = repo_root() / "config" / "decisions.yaml"
    if local.is_file():
        return local
    return Path("/opt/baansafe/config/decisions.yaml")


def decision_value(path: str) -> str:
    file = decisions_path()
    if not file.is_file():
        raise UnsetDecision(
            f"config/decisions.yaml is not at {file}. "
            "Export the matching environment variable. This app does not guess."
        )
    data = yaml.safe_load(file.read_text(encoding="utf-8"))
    node = data
    for part in path.split("."):
        if not isinstance(node, dict) or part not in node:
            raise UnsetDecision(
                f"config/decisions.yaml has no '{path}'. A human must add it."
            )
        node = node[part]
    if not isinstance(node, str):
        raise UnsetDecision(f"config/decisions.yaml:{path} must be a string.")
    return node


def resolve(path: str, env_name: str) -> str:
    """Environment wins. TODO_HUMAN in either place is a refusal."""
    env = os.environ.get(env_name, "").strip()
    if env:
        if env == UNSET:
            raise UnsetDecision(
                f"{env_name} is {UNSET}. Name a real value or unset it."
            )
        return env
    value = decision_value(path)
    if value == UNSET or value == "":
        raise UnsetDecision(
            f"config/decisions.yaml:{path} is {UNSET}. "
            f"Export {env_name} for this deploy, or set the decision. "
            "scripts/validate.py still requires the committed file to stay "
            f"{UNSET}, so the environment variable is the path that keeps "
            "make validate green."
        )
    return value


def parse_gpu(spec: str, *, allow_cpu: bool) -> str | None:
    """Return the Modal gpu= string, or None for a CPU container."""
    raw = spec.strip()
    if allow_cpu and raw.lower() == "cpu":
        return None
    name, sep, count = raw.partition(":")
    if name not in ALLOWED_GPUS:
        raise UnsetDecision(
            f"GPU {raw!r} is not one of {', '.join(ALLOWED_GPUS)}, "
            "or 'cpu' where that app allows it. See infra/HARDWARE.md."
        )
    if sep:
        try:
            n = int(count)
        except ValueError as exc:
            raise UnsetDecision(f"GPU count in {raw!r} is not an integer.") from exc
        if not 1 <= n <= 8:
            raise UnsetDecision(f"GPU count in {raw!r} must be 1 to 8.")
    return raw


def parse_quant(value: str) -> str:
    quant = value.strip().lower()
    if quant not in QUANTS:
        raise UnsetDecision(
            f"Quant {value!r} must be one of {', '.join(QUANTS)}."
        )
    return quant


def redact(message: str) -> str:
    cleaned = message
    for name in SECRET_ENV_NAMES:
        secret = os.environ.get(name, "")
        if secret:
            cleaned = cleaned.replace(secret, "[redacted]")
    return cleaned


def require_secret_present(name: str) -> None:
    """Used by local entrypoints. The Modal secret injects the same name remotely."""
    if not os.environ.get(name, "").strip():
        raise UnsetDecision(
            f"{name} is not set in this process. "
            "On Modal it must come from a modal.Secret. It is never hardcoded."
        )
