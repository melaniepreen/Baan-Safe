"""scripts/demo_reset.py: local mode on tmp files, hosted mode with a fake modal CLI."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from memory.content import LANE_CASE, LANE_CORRECTION, LANE_POLICY
from scripts import demo_reset


def _row(lane: str, content: str) -> dict:
    return {"id": f"mem-{lane}-{abs(hash(content)) % 10_000}", "kind": "fact", "lane": lane, "content": content}


def _seed_memory(path: Path, *, policy: int = 2, case: int = 3, correction: int = 1) -> None:
    rows = [_row(LANE_POLICY, f"[policy:MOF-2569-NO-DUPLICATE] lesson {i}") for i in range(policy)]
    rows += [_row(LANE_CASE, f"Case synthetic-{i}: needs=water") for i in range(case)]
    rows += [_row(LANE_CORRECTION, f"Correction {i}") for i in range(correction)]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


@pytest.fixture
def local_files(tmp_path, monkeypatch):
    paths = {
        "traces": tmp_path / "traces.jsonl",
        "memory": tmp_path / "var" / "memory.jsonl",
        "s2_cache": tmp_path / "s2_cache.jsonl",
        "corrections": tmp_path / "corrections.jsonl",
        "events": tmp_path / "events.jsonl",
    }
    monkeypatch.setenv("TRACE_PATH", str(paths["traces"]))
    monkeypatch.setenv("MEMORY_LOCAL_PATH", str(paths["memory"]))
    monkeypatch.setenv("S2_CACHE_RECORD_PATH", str(paths["s2_cache"]))
    monkeypatch.setenv("MOCK_CORRECTIONS_PATH", str(paths["corrections"]))
    monkeypatch.setenv("TRAINING_EVENTS_PATH", str(paths["events"]))
    paths["traces"].write_text('{"stage":"gateway"}\n{"stage":"router"}\n', encoding="utf-8")
    paths["s2_cache"].write_text('{"key":"abc","reply":{}}\n', encoding="utf-8")
    paths["corrections"].write_text('{"correction_id":"c1"}\n', encoding="utf-8")
    paths["events"].write_text('{"event":"e1"}\n{"event":"e2"}\n', encoding="utf-8")
    _seed_memory(paths["memory"])
    return paths


def _snapshot(paths: dict[str, Path]) -> dict[str, str | None]:
    return {k: (p.read_text(encoding="utf-8") if p.exists() else None) for k, p in paths.items()}


def test_dry_run_changes_nothing(local_files, capsys):
    before = _snapshot(local_files)
    assert demo_reset.run(["--local"]) == 0
    assert _snapshot(local_files) == before
    out = capsys.readouterr().out
    assert "dry-run" in out
    assert "nothing changed" in out
    assert f"'{LANE_CASE}': 3" in out
    assert "traces_lines: 2" in out


def test_yes_keeps_policy_drops_case_and_correction(local_files, capsys):
    assert demo_reset.run(["--local", "--yes"]) == 0
    rows = demo_reset.parse_rows(local_files["memory"].read_text(encoding="utf-8"))
    lanes = demo_reset.lane_counts(rows)
    assert lanes == {LANE_POLICY: 2}
    assert local_files["traces"].exists()
    assert local_files["traces"].read_text(encoding="utf-8") == ""
    assert not local_files["s2_cache"].exists()
    assert local_files["corrections"].read_text(encoding="utf-8") == ""
    # events.jsonl is left alone without --events.
    assert local_files["events"].read_text(encoding="utf-8").count("\n") == 2
    out = capsys.readouterr().out
    assert "applied" in out
    assert "events_lines: 2" in out


def test_events_flag_truncates_event_log(local_files):
    assert demo_reset.run(["--local", "--yes", "--events"]) == 0
    assert local_files["events"].read_text(encoding="utf-8") == ""


def test_reseeds_policy_lessons_when_none_remain(local_files):
    _seed_memory(local_files["memory"], policy=0, case=2, correction=0)
    assert demo_reset.run(["--local", "--yes"]) == 0
    rows = demo_reset.parse_rows(local_files["memory"].read_text(encoding="utf-8"))
    lanes = demo_reset.lane_counts(rows)
    assert set(lanes) == {LANE_POLICY}
    assert lanes[LANE_POLICY] == len(demo_reset.policy_lessons())
    assert all("[policy:" in row["content"] for row in rows)


def test_missing_files_and_unset_record_path(local_files, monkeypatch):
    monkeypatch.delenv("S2_CACHE_RECORD_PATH")
    local_files["memory"].unlink()
    local_files["traces"].unlink()
    assert demo_reset.run(["--local", "--yes", "--json"]) == 0
    rows = demo_reset.parse_rows(local_files["memory"].read_text(encoding="utf-8"))
    assert demo_reset.lane_counts(rows) == {LANE_POLICY: len(demo_reset.policy_lessons())}
    assert local_files["traces"].read_text(encoding="utf-8") == ""
    # The committed fixture (S2_CACHE_PATH) is never the record path target.
    assert local_files["s2_cache"].exists()


class _FakeVolume:
    """Stands in for `modal volume get/put/rm`. Records calls, moves files."""

    def __init__(self, files: dict[str, str]):
        self.files = dict(files)
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> subprocess.CompletedProcess:
        self.calls.append(list(args))
        verb, volume = args[0], args[1]
        assert volume == demo_reset.DEMO_VOLUME
        if verb == "get":
            remote, local = args[2], Path(args[3])
            if remote not in self.files:
                return subprocess.CompletedProcess(args, 1, "", "not found")
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_text(self.files[remote], encoding="utf-8")
            return subprocess.CompletedProcess(args, 0, "", "")
        if verb == "put":
            local, remote = Path(args[2]), args[3]
            self.files[remote] = local.read_text(encoding="utf-8")
            return subprocess.CompletedProcess(args, 0, "", "")
        if verb == "rm":
            self.files.pop(args[2], None)
            return subprocess.CompletedProcess(args, 0, "", "")
        raise AssertionError(verb)


def _hosted_files() -> dict[str, str]:
    mem = [
        _row(LANE_POLICY, "[policy:SPHERE-WASH-15L] lesson"),
        _row(LANE_CASE, "Case synthetic-9: needs=rescue"),
        _row(LANE_CORRECTION, "Correction x"),
    ]
    return {
        "memory.jsonl": "".join(json.dumps(r) + "\n" for r in mem),
        "traces.jsonl": "{}\n{}\n{}\n",
        "s2_cache.jsonl": "{}\n",
        "events.jsonl": "{}\n",
        # corrections.jsonl absent on purpose
    }


def test_hosted_dry_run_only_downloads(capsys):
    fake = _FakeVolume(_hosted_files())
    assert demo_reset.run(["--hosted"], runner=fake) == 0
    assert {call[0] for call in fake.calls} == {"get"}
    assert fake.files == _hosted_files()
    out = capsys.readouterr().out
    assert "hosted (dry-run)" in out
    assert "corrections.jsonl is not on the volume" in out


def test_hosted_yes_puts_memory_and_removes_files():
    fake = _FakeVolume(_hosted_files())
    assert demo_reset.run(["--hosted", "--yes"], runner=fake) == 0
    verbs = [(call[0], call[2] if call[0] != "put" else call[3]) for call in fake.calls if call[0] != "get"]
    assert ("put", "memory.jsonl") in verbs
    assert ("rm", "traces.jsonl") in verbs
    assert ("rm", "s2_cache.jsonl") in verbs
    # Not on the volume, so no rm; not requested, so events stays.
    assert ("rm", "corrections.jsonl") not in verbs
    assert ("rm", "events.jsonl") not in verbs
    assert "events.jsonl" in fake.files
    assert "traces.jsonl" not in fake.files
    rows = demo_reset.parse_rows(fake.files["memory.jsonl"])
    assert demo_reset.lane_counts(rows) == {LANE_POLICY: 1}
    put_call = next(call for call in fake.calls if call[0] == "put")
    assert "--force" in put_call
