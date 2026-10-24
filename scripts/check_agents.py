"""Fail when agent docs drift: size, template, or a missing index path."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENTS_MAX_LINES = 150
TOPIC_DIR = ROOT / "docs" / "agents"
INDEX_PATH = TOPIC_DIR / "index.json"
SKIP_TOPICS = {"INDEX.md"}
SECTIONS = (
    "## Purpose",
    "## Key files",
    "## Interfaces/contracts",
    "## Invariants",
    "## How to test",
    "## Common pitfalls",
    "## Open TODO_HUMAN keys",
)


def _front_matter(text: str) -> dict | None:
    if not text.startswith("---\n"):
        return None
    end = text.find("\n---\n", 4)
    if end == -1:
        return None
    try:
        import yaml
    except ImportError:
        return None
    loaded = yaml.safe_load(text[4:end])
    if not isinstance(loaded, dict):
        return None
    return loaded


def check(root: Path | None = None) -> list[str]:
    base = root or ROOT
    errors: list[str] = []
    agents = base / "AGENTS.md"
    if not agents.is_file():
        return ["AGENTS.md is missing"]
    lines = agents.read_text(encoding="utf-8").splitlines()
    if len(lines) > AGENTS_MAX_LINES:
        errors.append(f"AGENTS.md has {len(lines)} lines; budget is {AGENTS_MAX_LINES}")

    index_path = base / "docs" / "agents" / "index.json"
    if not index_path.is_file():
        errors.append("docs/agents/index.json is missing")
        return errors
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        errors.append(f"docs/agents/index.json: {exc}")
        return errors
    docs = index.get("docs")
    if not isinstance(docs, list) or not docs:
        errors.append("docs/agents/index.json has no docs list")
        return errors

    listed: set[str] = set()
    for entry in docs:
        if not isinstance(entry, dict):
            errors.append("index entry is not an object")
            continue
        rel = entry.get("path")
        if not isinstance(rel, str) or not rel:
            errors.append("index entry is missing path")
            continue
        listed.add(rel)
        doc = base / rel
        if not doc.is_file():
            errors.append(f"index path does not exist: {rel}")
            continue
        for key in ("title", "summary", "keywords"):
            if not entry.get(key):
                errors.append(f"{rel}: index entry missing {key}")
        for extra in entry.get("files") or []:
            if not isinstance(extra, str) or not (base / extra).exists():
                errors.append(f"index file does not exist: {extra} (from {rel})")
        text = doc.read_text(encoding="utf-8")
        matter = _front_matter(text)
        if matter is None:
            errors.append(f"{rel}: missing YAML front matter")
        else:
            for key in ("title", "tags", "files"):
                if not matter.get(key):
                    errors.append(f"{rel}: front matter missing {key}")
            for extra in matter.get("files") or []:
                if not isinstance(extra, str) or not (base / extra).exists():
                    errors.append(f"front matter file does not exist: {extra} (from {rel})")
        for heading in SECTIONS:
            if heading not in text.splitlines():
                errors.append(f"{rel}: missing section {heading}")

    topic_dir = base / "docs" / "agents"
    for path in sorted(topic_dir.glob("*.md")):
        if path.name in SKIP_TOPICS:
            continue
        rel = path.relative_to(base).as_posix()
        if rel not in listed:
            errors.append(f"topic doc is not in the index: {rel}")
    return errors


def main() -> int:
    errors = check()
    if errors:
        print(f"{len(errors)} agent-doc problem(s):")
        for message in errors:
            print(f"- {message}")
        return 1
    print("agent docs ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
