"""scripts/demo_reset.py: dry run by default, filtered memory.jsonl, empty traces and cache.

Every `modal` call goes through an injected fake. Nothing here talks to Modal.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from scripts import demo_reset

CASE = demo_reset.LANE_CASE
POLICY = demo_reset.LANE_POLICY
CORRECTION = demo_reset.LANE_CORRECTION

# Original order matters: kept lines must come back in this sequence.
MEMORY_LINES = [
    json.dumps({"id": "p1", "lane": POLICY, "content": "[policy:A-B] rule one"}),
    json.dumps({"id": "c1", "lane": CASE, "content": "Case F01: needs=water"}),
    json.dumps({"id": "x1", "lane": CORRECTION, "content": "lesson", "metadata": {"k": "v"}}),
    "this line is not json {",
    json.dumps({"id": "c2", "lane": CASE, "content": "Case F02: needs=rescue"}),
    json.dumps({"id": "p2", "lane": POLICY, "content": "[policy:C-D] rule two", "needs": []}),
    "",
    json.dumps({"id": "c3", "lane": CASE, "content": "Case F03: needs=food"}),
]
KEPT_LINES = [MEMORY_LINES[0], MEMORY_LINES[2], MEMORY_LINES[3], MEMORY_LINES[5]]


class FakeModal:
    """Serves one memory.jsonl on `get`; records what each `put` uploaded."""

    def __init__(self, memory_text: str) -> None:
        self.memory_text = memory_text
        self.calls: list[list[str]] = []
        self.puts: list[tuple[str, str, bytes]] = []  # (volume, remote, bytes)
        self.gets: list[tuple[str, str]] = []  # (volume, remote)

    def __call__(self, argv: list[str]) -> subprocess.CompletedProcess:
        self.calls.append(list(argv))
        at = argv.index("volume")
        sub = argv[at + 1]
        if sub == "get":
            volume, remote, local = argv[at + 2 : at + 5]
            self.gets.append((volume, remote))
            Path(local).write_text(self.memory_text, encoding="utf-8")
        elif sub == "put":
            assert argv[at + 2] == "--force"
            volume, local, remote = argv[at + 3 : at + 6]
            # Read now: the script's temp dir is gone after reset() returns.
            self.puts.append((volume, remote, Path(local).read_bytes()))
        else:  # pragma: no cover - guards against a new subcommand
            raise AssertionError(f"unexpected modal call: {argv}")
        return subprocess.CompletedProcess(argv, 0)


@pytest.fixture
def fake() -> FakeModal:
    return FakeModal("\n".join(MEMORY_LINES) + "\n")


def test_filter_memory_keeps_non_case_rows_verbatim():
    split = demo_reset.filter_memory("\n".join(MEMORY_LINES) + "\n")
    assert split.kept == KEPT_LINES
    assert split.keep == 4
    assert split.dropped == 3
    assert (split.policy, split.correction, split.other, split.unparsed) == (2, 1, 0, 1)
    assert split.text() == "".join(line + "\n" for line in KEPT_LINES)


def test_dry_run_downloads_only(fake: FakeModal, capsys: pytest.CaptureFixture[str]):
    code = demo_reset.main([], run=fake)
    out = capsys.readouterr().out
    assert code == 0
    assert fake.gets == [("baansafe-demo", "memory.jsonl")]
    assert fake.puts == []
    assert len(fake.calls) == 1
    assert "memory.jsonl: keep 4 (policy 2, correction 1, other 0, unparsed 1), drop 3 case rows" in out
    assert "traces.jsonl: would truncate" in out
    assert "s2_cache.jsonl: would truncate" in out
    assert "dry run" in out
    # The exact argv is printed so the plan is auditable.
    assert "volume get baansafe-demo memory.jsonl" in out


def test_yes_uploads_filtered_memory_and_empty_files(fake: FakeModal, capsys: pytest.CaptureFixture[str]):
    code = demo_reset.main(["--yes"], run=fake)
    out = capsys.readouterr().out
    assert code == 0
    assert fake.gets == [("baansafe-demo", "memory.jsonl")]
    assert [remote for _v, remote, _b in fake.puts] == ["memory.jsonl", "traces.jsonl", "s2_cache.jsonl"]
    assert all(volume == "baansafe-demo" for volume, _r, _b in fake.puts)
    by_remote = {remote: body for _v, remote, body in fake.puts}
    assert by_remote["memory.jsonl"].decode("utf-8").splitlines() == KEPT_LINES
    assert by_remote["traces.jsonl"] == b""
    assert by_remote["s2_cache.jsonl"] == b""
    put_calls = [argv for argv in fake.calls if "put" in argv]
    assert len(put_calls) == 3
    assert all("--force" in argv for argv in put_calls)
    assert "traces.jsonl: truncate" in out
    assert "s2_cache.jsonl: truncate" in out
    assert "done: 3 upload(s)" in out


def test_keep_flags_skip_traces_and_cache(fake: FakeModal, capsys: pytest.CaptureFixture[str]):
    code = demo_reset.main(["--yes", "--keep-traces", "--keep-cache"], run=fake)
    out = capsys.readouterr().out
    assert code == 0
    assert [remote for _v, remote, _b in fake.puts] == ["memory.jsonl"]
    assert len([argv for argv in fake.calls if "put" in argv]) == 1
    assert "traces.jsonl: keep (--keep-traces)" in out
    assert "s2_cache.jsonl: keep (--keep-cache)" in out


def test_volume_flag_is_used_for_get_and_put(fake: FakeModal):
    assert demo_reset.main(["--yes", "--volume", "baansafe-other"], run=fake) == 0
    assert fake.gets == [("baansafe-other", "memory.jsonl")]
    assert {volume for volume, _r, _b in fake.puts} == {"baansafe-other"}


def test_failed_get_changes_nothing(capsys: pytest.CaptureFixture[str]):
    calls: list[list[str]] = []

    def failing(argv: list[str]) -> subprocess.CompletedProcess:
        calls.append(argv)
        raise subprocess.CalledProcessError(1, argv)

    code = demo_reset.main(["--yes"], run=failing)
    err = capsys.readouterr().err
    assert code == 1
    assert len(calls) == 1
    assert "nothing changed" in err


def test_never_touches_other_volume_files(fake: FakeModal):
    demo_reset.main(["--yes"], run=fake)
    remotes = {argv[-1] for argv in fake.calls}
    for name in ("rl_run.json", "events.jsonl", "corrections.jsonl", "policy-pins"):
        assert name not in remotes
    assert not any("rm" in argv or "delete" in argv for argv in fake.calls)
