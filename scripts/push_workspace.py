"""Opposite of make sync: send local work up (Modal secrets + git push).

Never prints secret values. Never commits .env.
Optional: MSG='summary' commits current work before pushing.
Refuses to push when behind origin (run make sync first).
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKIP_COMMIT_PATHS = (".env", ".venv", ".vscode")


def run(cmd: list[str], *, check: bool = True, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        cmd,
        cwd=ROOT,
        check=check,
        text=True,
        capture_output=capture,
    )


def step(title: str) -> None:
    print(f"\n== {title}")


def ahead_behind(status: str) -> tuple[int, int]:
    ahead = behind = 0
    m = re.search(r"ahead (\d+)", status)
    if m:
        ahead = int(m.group(1))
    m = re.search(r"behind (\d+)", status)
    if m:
        behind = int(m.group(1))
    return ahead, behind


def sync_secrets() -> None:
    step("modal secrets")
    py = ROOT / ".venv" / "bin" / "python"
    if not py.is_file():
        py = Path(sys.executable)
    env = os.environ.copy()
    venv_bin = ROOT / ".venv" / "bin"
    if venv_bin.is_dir():
        env["PATH"] = str(venv_bin) + os.pathsep + env.get("PATH", "")
    result = run([str(py), str(ROOT / "scripts" / "sync_modal_secrets.py")], check=False, capture=True)
    if result.returncode != 0:
        err = (result.stderr or result.stdout or "").strip()
        print(err or "secret sync skipped or failed (fill .env keys, or run make sync first)")
        return
    # Re-print child stdout without risking secrets (script only prints key names).
    out = (result.stdout or "").strip()
    if out:
        print(out)


def maybe_commit() -> bool:
    """Return True if the tree is clean enough to consider pushing commits."""
    step("git commit")
    porcelain = run(["git", "status", "--porcelain"], capture=True).stdout
    if not porcelain.strip():
        print("working tree clean")
        return True

    msg = os.environ.get("MSG", "").strip()
    lines = [ln for ln in porcelain.splitlines() if ln.strip()]
    only_skip = True
    for ln in lines:
        path = ln[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        if not any(path == s or path.startswith(s + "/") for s in SKIP_COMMIT_PATHS):
            only_skip = False
            break
    if only_skip and not msg:
        print("only local IDE/env paths dirty; nothing to commit")
        print(porcelain.rstrip())
        return True

    if not msg:
        print("uncommitted changes (will not auto-commit without MSG):")
        print(porcelain.rstrip())
        print("tip: make push MSG='what you changed'")
        return True  # still allow pushing earlier commits

    run(["git", "add", "-A"])
    for skip in SKIP_COMMIT_PATHS:
        run(["git", "reset", "-q", "--", skip], check=False)
    staged = run(["git", "diff", "--cached", "--name-only"], capture=True).stdout.strip()
    if not staged:
        print("nothing staged after excluding .env/.venv/.vscode")
        return True
    run(["git", "commit", "-m", msg])
    print(f"committed: {msg}")
    return True


def run_sync() -> int:
    step("make sync (behind origin)")
    py = ROOT / ".venv" / "bin" / "python"
    if not py.is_file():
        py = Path(sys.executable)
    return run([str(py), str(ROOT / "scripts" / "sync_workspace.py")], check=False).returncode


def push_git() -> int:
    step("git push")
    run(["git", "fetch", "origin", "--prune"])
    branch = run(["git", "branch", "--show-current"], capture=True).stdout.strip()
    if branch != "main":
        print(f"on {branch}; make push only sends main (checkout main or push this branch yourself)")
        return 1
    status = run(["git", "status", "-sb"], capture=True).stdout.strip()
    print(status)
    ahead, behind = ahead_behind(status)
    if behind:
        print(f"behind origin/main by {behind}; running sync to pull/merge first")
        if run_sync() != 0:
            print("sync failed (conflicts?). Set SYNC_KEEP=local|remote|manual and retry")
            return 1
        run(["git", "fetch", "origin", "--prune"])
        status = run(["git", "status", "-sb"], capture=True).stdout.strip()
        print(status)
        ahead, behind = ahead_behind(status)
        if behind:
            print("still behind after sync; resolve manually")
            return 1
    if ahead == 0:
        print("nothing new to push to origin/main")
        return 0
    run(["git", "push", "origin", "main"])
    print(f"pushed {ahead} commit(s) to origin/main")
    return 0


def main() -> int:
    print("BaanSafe push (send)")
    sync_secrets()
    maybe_commit()
    code = push_git()
    print("\ndone" if code == 0 else "\nfailed")
    return code


if __name__ == "__main__":
    sys.exit(main())
