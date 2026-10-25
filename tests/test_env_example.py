""".env.example lists every environment name the live code reads, with safe dev values.

Scans `os.environ.get("NAME"` / `os.environ["NAME"]` under the runtime packages
and the hosted gateway app. A name may appear as `NAME=` or, when its code
needs a non-empty value, as a documented `# NAME=` line.
"""

from __future__ import annotations

import re
from pathlib import Path

from paths import ROOT

ENV_EXAMPLE = ROOT / ".env.example"
SCAN = (
    "gateway",
    "system1",
    "system2",
    "memory",
    "llm",
    "api",
    "eval",
    "training",
    "infra/modal/gateway_app.py",
)
# Not developer settings, so not in .env.example:
SKIP = {
    "MODAL_TASK_ID",  # set by Modal inside a task
    "MODAL_ENVIRONMENT",  # Modal CLI profile selector
    "VLLM_API_KEY",  # written (not read) by infra/modal/s2_cmd.py from S2_SERVE_API_KEY
    "PYTHONPATH",  # image env in gateway_app.STUB_ENV
    "PYTHONUNBUFFERED",  # image env in gateway_app.STUB_ENV
}
_READ = re.compile(r'os\.environ(?:\.get\(|\[)\s*"([A-Z][A-Z0-9_]*)"')
_LINE = re.compile(r"^(?:#\s*)?([A-Z][A-Z0-9_]*)=(.*)$")


def _scanned_files() -> list[Path]:
    files: list[Path] = []
    for entry in SCAN:
        path = ROOT / entry
        if path.is_file():
            files.append(path)
        else:
            files.extend(sorted(path.rglob("*.py")))
    return files


def _names_read() -> set[str]:
    names: set[str] = set()
    for path in _scanned_files():
        names |= set(_READ.findall(path.read_text(encoding="utf-8")))
    return names - SKIP


def _example_entries() -> dict[str, str]:
    entries: dict[str, str] = {}
    for raw in ENV_EXAMPLE.read_text(encoding="utf-8").splitlines():
        match = _LINE.match(raw.strip())
        if match:
            entries[match.group(1)] = match.group(2).strip()
    return entries


def test_every_name_the_code_reads_is_documented():
    documented = set(_example_entries())
    missing = sorted(_names_read() - documented)
    assert not missing, f"add to .env.example with a comment: {missing}"


def test_recommended_dev_values():
    entries = _example_entries()
    assert entries["MEMORY_IMPL"] == "local"
    assert entries["S1_IMPL"] == "real"
    assert entries["S2_IMPL"] == "cache"
    assert entries["S2_CACHE_KEY"] == "exact"
    assert entries["MUBIT_BASE_URL"] == "https://api.mubit.ai/compat/openrouter/v1"


def test_no_secret_values_in_example():
    entries = _example_entries()
    for name in ("MUBIT_API_KEY", "HF_TOKEN", "S2_SERVE_API_KEY", "OPENROUTER_API_KEY", "GISTDA_API_KEY"):
        assert entries[name] == "", f"{name} must be blank in git"


def test_every_entry_has_a_comment():
    """Each name is preceded by a comment line (a shared comment may cover a block)."""
    lines = ENV_EXAMPLE.read_text(encoding="utf-8").splitlines()
    previous_was_comment_or_entry = False
    for raw in lines:
        stripped = raw.strip()
        if not stripped:
            previous_was_comment_or_entry = False
            continue
        if stripped.startswith("#") and not _LINE.match(stripped):
            previous_was_comment_or_entry = True
            continue
        assert previous_was_comment_or_entry, f"no comment above {stripped.split('=')[0]}"
