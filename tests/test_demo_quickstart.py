"""scripts/demo.py: env defaults, seeding, the pid-file guard, port check."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import time

from memory.content import LANE_POLICY
from scripts import demo


def test_demo_env_defaults(tmp_path):
    env = demo.demo_env({"DEMO_DIR": str(tmp_path / "demo")})
    assert env["S1_IMPL"] == "real"
    assert env["S2_IMPL"] == "cache"
    assert env["S2_CACHE_KEY"] == "case"
    assert env["MEMORY_IMPL"] == "local"
    assert env["MEMORY_LOCAL_PATH"] == str(tmp_path / "demo" / "memory.jsonl")
    assert env["S2_CACHE_RECORD_PATH"] == str(tmp_path / "demo" / "s2_cache.jsonl")
    assert env["TRACE_PATH"] == str(tmp_path / "demo" / "traces.jsonl")
    assert env["MOCK_CORRECTIONS_PATH"] == str(tmp_path / "demo" / "corrections.jsonl")
    assert "TRAINING_EVENTS_PATH" not in env


def test_demo_env_ignores_ambient_impl(tmp_path):
    base = {"DEMO_DIR": str(tmp_path), "S2_IMPL": "stub", "MEMORY_IMPL": "mock"}
    env = demo.demo_env(base)
    assert env["S2_IMPL"] == "cache"
    assert env["MEMORY_IMPL"] == "local"
    ignored = demo.shell_overrides(base)
    assert ("S2_IMPL", "stub", "cache") in ignored
    assert ("MEMORY_IMPL", "mock", "local") in ignored


def test_demo_env_demo_prefix_overrides(tmp_path):
    base = {
        "DEMO_DIR": str(tmp_path),
        "S2_IMPL": "real",
        "DEMO_S2_IMPL": "stub",
        "DEMO_MEMORY_LOCAL_PATH": str(tmp_path / "custom.jsonl"),
    }
    env = demo.demo_env(base)
    assert env["S2_IMPL"] == "stub"
    assert env["MEMORY_LOCAL_PATH"] == str(tmp_path / "custom.jsonl")
    ignored = demo.shell_overrides(base)
    assert all(name != "S2_IMPL" for name, _, _ in ignored)
    assert all(name != "MEMORY_LOCAL_PATH" for name, _, _ in ignored)


def test_demo_env_passes_other_names_through(tmp_path):
    env = demo.demo_env({"DEMO_DIR": str(tmp_path), "MUBIT_BASE_URL": "https://api.mubit.ai"})
    assert env["MUBIT_BASE_URL"] == "https://api.mubit.ai"


def test_backend_busy_port_skips_reset_and_seed(tmp_path, monkeypatch):
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    calls: list[str] = []
    monkeypatch.setattr(demo, "apply_reset", lambda env: calls.append("reset"))
    monkeypatch.setattr(demo, "ensure_seeded", lambda env: calls.append("seed"))
    env = demo.demo_env({"DEMO_DIR": str(tmp_path), "DEMO_PORT": str(port), "RESET": "1"})
    try:
        assert demo.backend(env) == 1
    finally:
        listener.close()
    assert calls == []


def _policy_rows(path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and json.loads(line).get("lane") == LANE_POLICY
    ]


def test_ensure_seeded_writes_policy_lessons(tmp_path):
    env = demo.demo_env({"DEMO_DIR": str(tmp_path), "MEMORY_LOCAL_PATH": str(tmp_path / "memory.jsonl")})
    assert demo.ensure_seeded(env) is True
    rows = _policy_rows(tmp_path / "memory.jsonl")
    assert len(rows) == 10
    assert demo.ensure_seeded(env) is False
    assert len(_policy_rows(tmp_path / "memory.jsonl")) == 10


def test_stop_ignores_foreign_pid(tmp_path):
    env = demo.demo_env({"DEMO_DIR": str(tmp_path)})
    pid_file = tmp_path / "backend.pid"
    sleeper = subprocess.Popen(["sleep", "30"])
    try:
        pid_file.write_text(str(sleeper.pid), encoding="utf-8")
        assert demo.stop(env) == 0
        assert sleeper.poll() is None  # not our uvicorn: left running
        assert not pid_file.exists()
    finally:
        sleeper.terminate()
        sleeper.wait(timeout=5)


def test_stop_without_pid_file(tmp_path, capsys):
    env = demo.demo_env({"DEMO_DIR": str(tmp_path), "DEMO_PORT": "0"})
    assert demo.stop(env) == 0
    out = capsys.readouterr().out
    assert "No demo backend recorded" in out


def test_port_in_use():
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    assert demo.port_in_use("127.0.0.1", port) is True
    listener.close()
    deadline = time.monotonic() + 5
    while demo.port_in_use("127.0.0.1", port) and time.monotonic() < deadline:
        time.sleep(0.05)
    assert demo.port_in_use("127.0.0.1", port) is False


def test_mubit_creds_present_bool_and_silent(monkeypatch, capsys):
    monkeypatch.setenv("MUBIT_API_KEY", "test-fake-key-not-real")
    monkeypatch.setenv("MUBIT_BASE_URL", "https://api.mubit.ai")
    result = demo.mubit_creds_present(dict(os.environ))
    assert result is True
    captured = capsys.readouterr()
    assert captured.out == "" and captured.err == ""
    assert "test-fake-key-not-real" not in captured.out + captured.err

    monkeypatch.delenv("MUBIT_API_KEY")
    assert demo.mubit_creds_present({"MUBIT_BASE_URL": "https://api.mubit.ai"}) is False
