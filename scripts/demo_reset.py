"""Reset the hosted demo volume to one known state. `make demo-reset`.

Every rehearsal against the public demo grows three files on the
`baansafe-demo` Modal volume, mounted at `/data` by
infra/modal/gateway_app.py: `traces.jsonl` (TRACE_PATH), `s2_cache.jsonl`
(S2_CACHE_RECORD_PATH, the misses recorded by system2/cache.py), and the
`baansafe-case` rows memory/local.py appends to `memory.jsonl`
(MEMORY_LOCAL_PATH). This script empties the first two and drops the case
rows from the third. Every other memory row (the policy lessons from
scripts/seed_memory.py, corrections, anything else) is kept byte for byte,
in its original order. A line that is not JSON is kept and counted as
`unparsed`; blank lines are dropped.

Default is a DRY RUN: download memory.jsonl, print the plan, upload nothing.
`--yes` performs the uploads with `modal volume put --force`. `--keep-traces`
and `--keep-cache` leave those two files alone. Nothing is ever deleted from
the volume, and `rl_run.json`, `events.jsonl`, `corrections.jsonl`, and
`policy-pins/` are never touched.

Every CLI call goes through one `run(argv)` callable (default:
`subprocess.run(argv, check=True)`), so tests inject a fake and nothing real
is called. No secret is read or printed. Each `modal` argv is printed so a
dry run is auditable.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

DEFAULT_VOLUME = "baansafe-demo"
MEMORY_FILE = "memory.jsonl"
TRACES_FILE = "traces.jsonl"
CACHE_FILE = "s2_cache.jsonl"

# Mirrors memory/content.py LANE_*; kept literal so this script imports nothing
# from the app and can run from any checkout.
LANE_CASE = "baansafe-case"
LANE_CORRECTION = "baansafe-correction"
LANE_POLICY = "baansafe-policy"

Runner = Callable[[list[str]], subprocess.CompletedProcess]


def default_run(argv: list[str]) -> subprocess.CompletedProcess:
    """The real thing. Raises CalledProcessError on a non-zero exit."""
    return subprocess.run(argv, check=True)


def modal_cli() -> list[str]:
    """`modal` from PATH, else the interpreter's module (the Makefile's
    `$(PYTHON) -m modal` form) so the venv works without activation."""
    if shutil.which("modal"):
        return ["modal"]
    return [sys.executable, "-m", "modal"]


def get_argv(volume: str, remote: str, local: Path, *, cli: list[str] | None = None) -> list[str]:
    return [*(cli or modal_cli()), "volume", "get", volume, remote, str(local)]


def put_argv(volume: str, local: Path, remote: str, *, cli: list[str] | None = None) -> list[str]:
    return [*(cli or modal_cli()), "volume", "put", "--force", volume, str(local), remote]


@dataclass
class MemorySplit:
    """Result of filtering one memory.jsonl. `kept` holds the original lines."""

    kept: list[str] = field(default_factory=list)
    dropped: int = 0
    policy: int = 0
    correction: int = 0
    other: int = 0
    unparsed: int = 0

    @property
    def keep(self) -> int:
        return len(self.kept)

    def text(self) -> str:
        return "".join(line + "\n" for line in self.kept)

    def summary(self) -> str:
        return (
            f"{MEMORY_FILE}: keep {self.keep} (policy {self.policy}, "
            f"correction {self.correction}, other {self.other}, unparsed {self.unparsed}), "
            f"drop {self.dropped} case rows"
        )


def filter_memory(text: str) -> MemorySplit:
    """Drop `baansafe-case` rows. Keep every other line verbatim."""
    split = MemorySplit()
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            split.kept.append(line)
            split.unparsed += 1
            continue
        lane = row.get("lane") if isinstance(row, dict) else None
        if lane == LANE_CASE:
            split.dropped += 1
            continue
        split.kept.append(line)
        if lane == LANE_POLICY:
            split.policy += 1
        elif lane == LANE_CORRECTION:
            split.correction += 1
        else:
            split.other += 1
    return split


def _show(argv: list[str]) -> None:
    print("  $ " + " ".join(argv))


def reset(
    *,
    volume: str = DEFAULT_VOLUME,
    yes: bool = False,
    keep_traces: bool = False,
    keep_cache: bool = False,
    run: Runner = default_run,
) -> int:
    """Dry run unless `yes`. Returns a process exit code."""
    cli = modal_cli()
    mode = "apply" if yes else "dry run"
    print(f"demo-reset ({mode}) volume={volume}")
    with tempfile.TemporaryDirectory(prefix="baansafe-demo-reset-") as tmp:
        work = Path(tmp)
        downloaded = work / MEMORY_FILE
        argv = get_argv(volume, MEMORY_FILE, downloaded, cli=cli)
        _show(argv)
        try:
            run(argv)
        except FileNotFoundError:
            print("modal CLI not found; nothing changed", file=sys.stderr)
            return 1
        except subprocess.CalledProcessError as exc:
            print(
                f"{MEMORY_FILE}: modal volume get failed (exit {exc.returncode}); nothing changed",
                file=sys.stderr,
            )
            return 1
        if not downloaded.is_file():
            print(f"{MEMORY_FILE}: not downloaded; nothing changed", file=sys.stderr)
            return 1

        split = filter_memory(downloaded.read_text(encoding="utf-8"))
        filtered = work / "memory.reset.jsonl"
        filtered.write_text(split.text(), encoding="utf-8")
        empty = work / "empty"
        empty.write_bytes(b"")

        verb = "truncate" if yes else "would truncate"
        print(split.summary())
        print(f"{TRACES_FILE}: {'keep (--keep-traces)' if keep_traces else verb}")
        print(f"{CACHE_FILE}: {'keep (--keep-cache)' if keep_cache else verb}")

        puts: list[tuple[Path, str]] = [(filtered, MEMORY_FILE)]
        if not keep_traces:
            puts.append((empty, TRACES_FILE))
        if not keep_cache:
            puts.append((empty, CACHE_FILE))

        if not yes:
            print("dry run: nothing uploaded. Planned uploads:")
            for local, remote in puts:
                _show(put_argv(volume, local, remote, cli=cli))
            print("re-run with --yes to apply")
            return 0

        for local, remote in puts:
            argv = put_argv(volume, local, remote, cli=cli)
            _show(argv)
            run(argv)
        print(f"done: {len(puts)} upload(s) to {volume}")
    return 0


def main(argv: list[str] | None = None, *, run: Runner = default_run) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--volume", default=DEFAULT_VOLUME, help=f"Modal volume (default {DEFAULT_VOLUME})")
    parser.add_argument("--yes", action="store_true", help="apply; without it this is a dry run")
    parser.add_argument("--keep-traces", action="store_true", help=f"do not truncate {TRACES_FILE}")
    parser.add_argument("--keep-cache", action="store_true", help=f"do not truncate {CACHE_FILE}")
    args = parser.parse_args(argv)
    return reset(
        volume=args.volume,
        yes=args.yes,
        keep_traces=args.keep_traces,
        keep_cache=args.keep_cache,
        run=run,
    )


if __name__ == "__main__":
    raise SystemExit(main())
