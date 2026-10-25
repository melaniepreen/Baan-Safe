"""Seed the memory store with lessons derived from the policy corpus.

`make seed-memory` writes 6-10 short English items into lane `baansafe-policy`
through `memory.adapter.ingest_items`, the same adapter the gateway uses:
`MEMORY_IMPL=local` appends them to the JSONL file at MEMORY_LOCAL_PATH
(`var/memory.jsonl` by default, `/data/memory.jsonl` on Modal);
`MEMORY_IMPL=mubit` posts them to `/v2/control/ingest` (dormant until Mubit
exposes a memory API). Every item is prefixed with a stable tag
`[policy:<rule_id>]` and its text is taken from the sentences
`policies/service.py` serves for that rule. `rule` items are corpus
sentences only. `lesson` items add one operational note from this repo's
own fixes (for example system1/extract.py on "unaccompanied").

Idempotency: before writing, the script looks for the tags already in the
store (local: read the file; mubit: the same /v2/control/query body shape as
memory/mubit.py) and skips any tag that is present. The tag prefix is the
dedup key.

Flags:
  --dry-run            print the items; write nothing (no key needed)
  --case-fact CASE_ID  also write one synthetic `fact` for a case id, in the
                       summary shape of memory.content.record_content, so a
                       second call from the same household can retrieve it
  --path FILE          local mode: write to FILE instead of MEMORY_LOCAL_PATH
  --json               machine-readable report on stdout

Refuses to run (exit 2) when MEMORY_IMPL is `mock`, or is `mubit` without
MUBIT_API_KEY. Never prints the key. Synthetic people only.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

LANE = "baansafe-policy"
CASE_LANE = "baansafe-case"
WRITABLE_MODES = ("local", "mubit")
MAX_CHARS = 300
_TAG = re.compile(r"\[policy:([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\]")
_SENTENCE = re.compile(r"(?<=[.!?])\s+")


@dataclass(frozen=True)
class LessonSpec:
    """Which corpus sentences make one memory item.

    `pick` is a tuple of substrings in priority order. A sentence of the
    rule's English text is kept when it contains one of them; later picks are
    dropped first when the item would pass 300 chars. `note` is this repo's
    own operational lesson and is only allowed on `lesson` items.
    """

    rule_id: str
    entry_type: str  # "rule" or "lesson"
    pick: tuple[str, ...]
    note: str = ""


# Each spec names a rule in policies/*.yaml. The text is read from the corpus
# at run time; nothing here restates a policy.
SPECS: tuple[LessonSpec, ...] = (
    LessonSpec(
        "MOF-2569-WITHIN-REGULATION",
        "rule",
        ("Clause 4 says", "Do not add a definition"),
    ),
    LessonSpec(
        "MOF-2569-OUTSIDE-APPROVAL",
        "rule",
        ("Clause 9 says", "is not approved by this sentence"),
    ),
    LessonSpec(
        "MOF-2569-NO-DUPLICATE",
        "lesson",
        ("A second payment", "is not duplicated"),
        note=(
            "BaanSafe: a repeat call from the same household is one case; "
            "merge it with the open case before a new dispatch or aid."
        ),
    ),
    LessonSpec(
        "MOF-2569-CASH-DISCRETION",
        "rule",
        ("Clause 5.7 says", "It is not a decision for the model"),
    ),
    LessonSpec(
        "MOF-2569-WATER-ACTUAL",
        "rule",
        ("Clause 5.1.3 allows", "prints no baht cap"),
    ),
    LessonSpec(
        "SPHERE-WASH-15L",
        "rule",
        ("15 litres is not a ceiling",),
    ),
    LessonSpec(
        "UNHCR-DO-NOT-SCORE",
        "rule",
        ("A category label is not",),
    ),
    LessonSpec(
        "IFRC-PGI-UASC",
        "lesson",
        ("especially unaccompanied and separated children",),
        note="BaanSafe: 'unaccompanied' alone signals a child alone unless an adult is named.",
    ),
    LessonSpec(
        "IFRC-PGI-CHILD-DEFINITION",
        "lesson",
        ("A call that involves a child is a protection matter",),
        note=(
            "BaanSafe: a safeguarding flag, an aid denial or exception, or a "
            "supervisor route always requires a human."
        ),
    ),
    LessonSpec(
        "READY-NOT-ALONE",
        "lesson",
        ("says not to leave the person alone", "not a rule that every older person"),
        note="BaanSafe: assess an older person alone in floodwater individually.",
    ),
)


def tag_for(rule_id: str) -> str:
    return f"[policy:{rule_id}]"


def tags_in(text: str) -> set[str]:
    return {f"[policy:{m}]" for m in _TAG.findall(text or "")}


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in _SENTENCE.split(text.strip()) if part.strip()]


def build_lessons(service=None) -> list[dict[str, Any]]:
    """Memory items from the corpus. Reads rules through the policy service."""
    if service is None:
        from policies.service import get_service

        service = get_service()
    items: list[dict[str, Any]] = []
    for spec in SPECS:
        rule = service.require_rule(spec.rule_id)
        text = rule.languages["en"].text
        # Pick order is priority order: the first needle's sentence survives
        # trimming longest.
        chosen: list[str] = []
        for needle in spec.pick:
            for sentence in _sentences(text):
                if needle in sentence and sentence not in chosen:
                    chosen.append(sentence)
        if not chosen:
            raise ValueError(
                f"{spec.rule_id}: none of {spec.pick} is in the corpus text; "
                "update SPECS or the corpus, do not invent a sentence."
            )
        if spec.note and spec.entry_type != "lesson":
            raise ValueError(f"{spec.rule_id}: only lesson items carry a note.")
        head = tag_for(spec.rule_id)

        def _join(sentences: list[str]) -> str:
            text = f"{head} {' '.join(sentences)}"
            return f"{text} {spec.note}" if spec.note else text

        # Drop whole corpus sentences from the end until it fits. Never cut a
        # sentence in half and never trim the tag or the note.
        while len(_join(chosen)) > MAX_CHARS and len(chosen) > 1:
            chosen.pop()
        content = _join(chosen)
        if len(content) > MAX_CHARS:
            raise ValueError(
                f"{spec.rule_id}: {len(content)} chars; shorten the note or pick a shorter sentence."
            )
        items.append(
            {
                "type": spec.entry_type,
                "content": content,
                "lane": LANE,
                "metadata": {
                    "policy_id": rule.rule_id,
                    "domain": rule.domain,
                    "jurisdiction": rule.jurisdiction,
                    "source_id": rule.source_id,
                    "verified": rule.verified,
                },
            }
        )
    return items


def build_case_fact(case_id: str) -> dict[str, Any]:
    """One synthetic case summary in the shape memory.mubit.write uses."""
    needs = "water,evacuation"
    decision = "ask_next_question"
    priority = "P2"
    try:
        from fixtures.load import load_case

        case = load_case(case_id)
        needs = ",".join(case.fields.needs) or "none"
    except Exception:
        pass
    location = "Watthana District, Bangkok"
    summary = (
        f"Case {case_id}: needs={needs}; location={location}; decision={decision}; "
        f"priority={priority}. "
        "Synthetic household (no real person): older resident, water on the ground floor."
    )
    return {
        "type": "fact",
        "content": summary[:800],
        "lane": CASE_LANE,
        "source_case_id": case_id,
        "metadata": {
            "source_case_id": case_id,
            "lane": CASE_LANE,
            "location": location,
            "needs": needs.split(","),
            "priority": priority,
            "next_action": decision,
        },
    }


def _texts_in(payload: Any) -> list[str]:
    """Every content-like string in a control-plane response, any shape."""
    out: list[str] = []
    if isinstance(payload, dict):
        for key in ("content", "text", "summary", "final_answer", "context"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                out.append(value)
        for key in ("evidence", "entries", "items", "results", "lessons", "data"):
            value = payload.get(key)
            if isinstance(value, list):
                for row in value:
                    out.extend(_texts_in(row))
    elif isinstance(payload, list):
        for row in payload:
            out.extend(_texts_in(row))
    elif isinstance(payload, str):
        out.append(payload)
    return out


def _memory_mode() -> str:
    return os.environ.get("MEMORY_IMPL", "mock").strip().lower() or "mock"


def existing_tags(items: list[dict[str, Any]]) -> tuple[set[str], dict[str, Any]]:
    """Tags already present in the store.

    Local mode reads the JSONL file. Mubit mode runs a tag-only control query
    with the same body shape as memory.mubit.retrieve. Returns the tag set
    and a secret-free probe for the report.
    """
    wanted = [tag_for(_TAG.search(item["content"]).group(1)) for item in items]
    if _memory_mode() == "local":
        from memory import local

        found: set[str] = set()
        rows = local.load_rows()
        for row in rows:
            found |= tags_in(str(row.get("content") or "")) & set(wanted)
        return found, {"path": str(local.store_path()), "rows": len(rows)}

    from memory import mubit

    body = mubit.query_body(
        "BaanSafe policy lessons " + " ".join(wanted),
        limit=50,
        entry_types=["lesson", "rule"],
    )
    payload = mubit.query(body)
    found: set[str] = set()
    for text in _texts_in(payload):
        found |= tags_in(text) & set(wanted)
    return found, payload


def refuse_reason() -> str | None:
    mode = _memory_mode()
    if mode not in WRITABLE_MODES:
        return (
            f"MEMORY_IMPL is {mode!r}; seeding writes to BaanSafe's local store "
            "(MEMORY_IMPL=local, file at MEMORY_LOCAL_PATH) or to the Mubit control "
            "plane (MEMORY_IMPL=mubit, load .env). Set one and retry."
        )
    if mode == "mubit" and not os.environ.get("MUBIT_API_KEY", "").strip():
        return "MUBIT_API_KEY is unset. Load .env (set -a; source .env; set +a) and retry."
    return None


def _scrub(text: str) -> str:
    key = os.environ.get("MUBIT_API_KEY", "").strip()
    return text.replace(key, "<redacted>") if key else text


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="print items, POST nothing")
    parser.add_argument("--case-fact", metavar="CASE_ID", help="also ingest one synthetic case fact")
    parser.add_argument("--json", action="store_true", help="JSON report on stdout")
    parser.add_argument("--no-skip", action="store_true", help="ingest even when the tag already exists")
    parser.add_argument(
        "--path", metavar="FILE", help="local mode: JSONL file to write (overrides MEMORY_LOCAL_PATH)"
    )
    args = parser.parse_args(argv)
    if args.path:
        os.environ["MEMORY_LOCAL_PATH"] = str(Path(args.path).expanduser())

    items = build_lessons()
    if args.case_fact:
        items.append(build_case_fact(args.case_fact))
    report: dict[str, Any] = {
        "lane": LANE,
        "mode": _memory_mode(),
        "count": len(items),
        "tags": sorted(tags_in(" ".join(i["content"] for i in items))),
        "items": items,
        "dry_run": bool(args.dry_run),
    }

    if args.dry_run:
        _print(report, args.json)
        return 0

    reason = refuse_reason()
    if reason:
        print(f"seed-memory refused: {reason}", file=sys.stderr)
        return 2

    from memory.adapter import ingest_items

    try:
        if args.no_skip:
            present, probe = set(), {}
        else:
            present, probe = existing_tags([i for i in items if i["type"] != "fact"])
    except Exception as exc:  # the API told us something; report it without the key
        report["query_error"] = _scrub(f"{type(exc).__name__}: {exc}")
        _print(report, args.json)
        print(
            "seed-memory: the store probe failed, so nothing was ingested. "
            "If the error is HTTP 404 unknown_route, current Mubit has no memory API; "
            "use MEMORY_IMPL=local, or set MUBIT_CONTROL_URL to a host that serves /v2/control.",
            file=sys.stderr,
        )
        return 1
    report["already_present"] = sorted(present)
    report["probe"] = probe
    to_send = [
        item
        for item in items
        if item["type"] == "fact" or not (tags_in(item["content"]) & present)
    ]
    report["skipped"] = len(items) - len(to_send)
    if not to_send:
        report["ingested"] = 0
        _print(report, args.json)
        return 0
    try:
        response = ingest_items(to_send)
    except Exception as exc:
        report["ingest_error"] = _scrub(f"{type(exc).__name__}: {exc}")
        _print(report, args.json)
        return 1
    report["ingested"] = len(to_send)
    report["ingest_response"] = response
    _print(report, args.json)
    return 0


def _print(report: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(_scrub(json.dumps(report, ensure_ascii=False, indent=2, default=str)))
        return
    label = "dry-run" if report.get("dry_run") else "seed"
    print(
        f"seed-memory {label}: {report['count']} items, lane={report['lane']}, "
        f"mode={report.get('mode', 'mock')}"
    )
    for item in report["items"]:
        print(f"  {item['type']:6} {len(item['content']):3} chars  {_scrub(item['content'])}")
    if "already_present" in report:
        print(f"already present: {len(report['already_present'])}; skipped {report.get('skipped', 0)}")
    if "ingested" in report:
        print(f"ingested: {report['ingested']}")
    for key in ("query_error", "ingest_error"):
        if key in report:
            print(f"{key}: {report[key]}")


if __name__ == "__main__":
    raise SystemExit(run())
