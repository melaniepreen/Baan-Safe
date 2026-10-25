"""The last N Mubit request ids from the trace file, one row per hop.

Each ``mubit_chat`` TraceEvent that ``llm/client.py`` emits carries Mubit's
``request_id=mreq_…`` in its note (``(recorded)`` marks a cache replay, where
the id belongs to the call that was recorded). This script lists the latest
N of them with the case id and, when the same case has a ``system_2`` trace
row in the same file, that outcome's priority and route. Paste an id into
the Mubit console's Requests filter to open the recorded call.

Only parsed fields are printed: never the note text, never a host, never a
key. Rows without a request id are skipped and counted.

    make mubit-requests N=10
    python scripts/mubit_requests.py --path traces.jsonl --n 5 --json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from contracts.models import TraceEvent  # noqa: E402
from trace import read_traces, trace_path  # noqa: E402

REQUEST_ID = re.compile(r"request_id=(\S+)")
STATUS = re.compile(r"status=(\S+)")
RECORDED_MARKER = "(recorded)"
COLUMNS = ("started_at", "case_id", "request_id", "status", "recorded", "latency_ms", "priority", "route")
WIDTHS = {
    "started_at": 17,
    "case_id": 20,
    "request_id": 37,
    "status": 10,
    "recorded": 8,
    "latency_ms": 10,
    "priority": 8,
    "route": 22,
}


def parse_note(note: str | None) -> tuple[str | None, str | None, bool]:
    """``(request_id, status, recorded)`` from a ``mubit_chat`` note."""

    text = note or ""
    recorded = RECORDED_MARKER in text
    match = REQUEST_ID.search(text)
    request_id = match.group(1) if match else None
    if request_id and request_id.endswith(RECORDED_MARKER):
        request_id = request_id[: -len(RECORDED_MARKER)]
        recorded = True
    status_match = STATUS.search(text)
    status = status_match.group(1) if status_match else None
    return (request_id or None), status, recorded


def _as_utc(stamp: datetime) -> datetime:
    if stamp.tzinfo is None:
        return stamp.replace(tzinfo=timezone.utc)
    return stamp.astimezone(timezone.utc)


def _enum_text(value) -> str | None:
    if value is None:
        return None
    return str(getattr(value, "value", value))


def collect(path: Path, n: int) -> tuple[list[dict], int]:
    """The last ``n`` request rows by ``started_at`` and the skipped count."""

    events = read_traces(path=path)
    latest_s2: dict[str, TraceEvent] = {}
    for event in events:
        if event.stage != "system_2" or event.outcome is None:
            continue
        current = latest_s2.get(event.case_id)
        if current is None or _as_utc(event.started_at) >= _as_utc(current.started_at):
            latest_s2[event.case_id] = event
    rows: list[dict] = []
    skipped = 0
    for event in events:
        if event.stage != "mubit_chat":
            continue
        request_id, status, recorded = parse_note(event.notes)
        if not request_id:
            skipped += 1
            continue
        s2 = latest_s2.get(event.case_id)
        outcome = s2.outcome if s2 is not None else None
        rows.append(
            {
                "started_at": _as_utc(event.started_at).strftime("%Y-%m-%dT%H:%MZ"),
                "case_id": event.case_id,
                "request_id": request_id,
                "status": status,
                "recorded": recorded,
                "latency_ms": int(event.latency_ms),
                "priority": _enum_text(getattr(outcome, "priority", None)),
                "route": _enum_text(getattr(outcome, "route", None)),
                "_sort": _as_utc(event.started_at),
            }
        )
    rows.sort(key=lambda row: row["_sort"])
    kept = rows[-n:] if n > 0 else []
    for row in kept:
        row.pop("_sort", None)
    return kept, skipped


def _cell(value) -> str:
    if value is None:
        return "-"
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def format_table(rows: list[dict]) -> str:
    header = " | ".join(name.ljust(WIDTHS[name]) for name in COLUMNS).rstrip()
    rule = "-+-".join("-" * WIDTHS[name] for name in COLUMNS)
    lines = [header, rule]
    for row in rows:
        lines.append(" | ".join(_cell(row[name]).ljust(WIDTHS[name]) for name in COLUMNS).rstrip())
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", type=Path, default=None, help="trace file (default: TRACE_PATH or traces.jsonl)")
    parser.add_argument("--n", type=int, default=10, help="how many of the latest request ids to list")
    parser.add_argument("--json", action="store_true", help="print a JSON list instead of a table")
    args = parser.parse_args(argv)
    path = args.path or trace_path()
    if not path.exists():
        print(f"no trace file at {path.name}; run a System 2 call first", file=sys.stderr)
        return 1
    rows, skipped = collect(path, args.n)
    trailer = f"skipped {skipped} rows without request_id"
    if args.json:
        # stdout stays one JSON document; the count goes to stderr.
        print(json.dumps(rows, ensure_ascii=False, indent=2))
        print(trailer, file=sys.stderr)
    else:
        print(format_table(rows))
        print(trailer)
    return 0


if __name__ == "__main__":
    sys.exit(main())
