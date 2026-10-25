""".env.example fresh-clone defaults (HANDOVER H2): real S1, cached S2, local memory, no keys."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_EXAMPLE = ROOT / ".env.example"


def parse_env_example(path: Path = ENV_EXAMPLE) -> dict[str, str]:
    """KEY=VALUE lines only; comments and blanks are ignored."""
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def test_fresh_clone_defaults():
    env = parse_env_example()
    assert env["S1_IMPL"] == "real"
    assert env["S2_IMPL"] == "cache"
    assert env["S2_CACHE_KEY"] == "exact"
    assert env["MEMORY_IMPL"] == "local"


def test_secret_and_mubit_vars_are_blank():
    env = parse_env_example()
    for key in ("MUBIT_API_KEY", "MUBIT_BASE_URL", "HF_TOKEN", "OPENROUTER_API_KEY"):
        assert key in env, key
        assert env[key] == "", key


def test_memory_local_path_defaults_to_var():
    env = parse_env_example()
    assert env["MEMORY_LOCAL_PATH"] == ""
