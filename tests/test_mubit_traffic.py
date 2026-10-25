"""scripts/mubit_traffic.py: deterministic variants, no socket on dry-run."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load():
    spec = importlib.util.spec_from_file_location("mubit_traffic", ROOT / "scripts" / "mubit_traffic.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_variants_are_distinct_and_deterministic():
    mod = _load()
    a = mod.build_variants(40, 7)
    b = mod.build_variants(40, 7)
    assert [v["case_id"] for v in a] == [f"traffic-7-{i:04d}" for i in range(40)]
    assert a == b
    texts = [" ".join(t["text"] for t in v["transcript"] if t["speaker"] == "caller") for v in a]
    assert len(set(texts)) == 40
    assert not any("Placeholder" in t for t in texts)
    # synthetic only: no digit runs that could read as a phone or id
    assert not any(re.search(r"\d{7,}", t) for t in texts)


def test_dry_run_prints_and_opens_no_socket(monkeypatch, capsys):
    mod = _load()
    monkeypatch.delenv("MUBIT_API_KEY", raising=False)
    monkeypatch.delenv("MUBIT_BASE_URL", raising=False)

    def boom(*_a, **_k):  # pragma: no cover - must not be reached
        raise AssertionError("dry-run must not run a case")

    monkeypatch.setattr(mod, "_run_one", boom)
    assert mod.main(["--count", "3", "--seed", "2", "--dry-run"]) == 0
    out = capsys.readouterr().out.strip().splitlines()
    assert len(out) == 3
    assert json.loads(out[0])["case_id"] == "traffic-2-0000"


def test_live_refuses_without_credentials(monkeypatch):
    mod = _load()
    monkeypatch.delenv("MUBIT_API_KEY", raising=False)
    monkeypatch.delenv("MUBIT_BASE_URL", raising=False)
    with pytest.raises(SystemExit) as exc:
        mod.main(["--count", "1"])
    assert "MUBIT_API_KEY" in str(exc.value)
    assert "mbt_" not in str(exc.value)
