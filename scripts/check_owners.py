"""Warn when a branch touches another person's single-writer file.

`make check-owners` runs this before a PR. It is a reminder, not security:
PRs #34 and #35 each carried someone else's in-progress edits because
`git add -A` ran in the shared checkout. Work in a worktree per branch
(`git worktree add ../Baan-Safe-wt/<name> -b <branch> origin/main`) and stage
paths explicitly.

Single-writer files and the branch prefixes that mark the owner's work:

    ui/sim/sim.js   Melanie   branches melanie/..., mel/...
    llm/client.py   Moly      branches moly/...

Files changed = `git diff --name-only <base>...HEAD` plus the working tree
(`git status --porcelain`). A touched single-writer file on a branch whose
name does not start with one of the owner's prefixes is a warning. Exit 0
unless `--strict`, which exits 1 on any warning. `--base` defaults to
`origin/main`; `--branch` and `--files` override git for tests.

GitHub-side review routing is `.github/CODEOWNERS`. OWNERSHIP.md is the
human-readable source.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# path -> (owner, branch prefixes). Keep in step with .github/CODEOWNERS.
SINGLE_WRITER: dict[str, tuple[str, tuple[str, ...]]] = {
    "ui/sim/sim.js": ("Melanie", ("melanie/", "mel/")),
    "llm/client.py": ("Moly", ("moly/",)),
}


def warnings_for(branch: str, files: list[str]) -> list[str]:
    """One line per single-writer file touched from a non-owner branch."""
    name = branch.strip()
    out: list[str] = []
    for path in sorted(set(files)):
        entry = SINGLE_WRITER.get(path)
        if entry is None:
            continue
        owner, prefixes = entry
        if any(name.startswith(prefix) for prefix in prefixes):
            continue
        out.append(
            f"{path} is {owner}'s single-writer file; branch {name!r} does not start "
            f"with {' or '.join(prefixes)}. Leave it out of this PR unless {owner} asked."
        )
    return out


def _git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or f"git {' '.join(args)} failed")
    return result.stdout


def current_branch() -> str:
    return _git("rev-parse", "--abbrev-ref", "HEAD").strip()


def changed_files(base: str) -> list[str]:
    files = set(_git("diff", "--name-only", f"{base}...HEAD").split())
    for line in _git("status", "--porcelain").splitlines():
        if len(line) > 3:
            path = line[3:].strip()
            if " -> " in path:
                path = path.split(" -> ", 1)[1]
            files.add(path)
    return sorted(files)


def run(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base", default="origin/main", help="compare against this ref")
    parser.add_argument("--branch", help="branch name (default: git HEAD)")
    parser.add_argument("--files", nargs="*", help="changed files (default: git)")
    parser.add_argument("--strict", action="store_true", help="exit 1 on a warning")
    args = parser.parse_args(argv)

    try:
        branch = args.branch or current_branch()
        files = args.files if args.files is not None else changed_files(args.base)
    except RuntimeError as exc:
        print(f"check-owners: skipped ({exc})")
        return 0

    found = warnings_for(branch, files)
    if not found:
        print(f"check-owners ok: {len(files)} changed file(s) on {branch!r}, no single-writer conflict")
        return 0
    print(f"check-owners: {len(found)} warning(s) on {branch!r}")
    for line in found:
        print(f"- {line}")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(run())
