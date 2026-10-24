"""Shared teammate sync (download): pull, env, venv deps, Modal CLI/secrets.

Never prints secret values. Use `make push` to send commits and secrets.
Does not overwrite existing .env values. Adds missing keys from .env.example.
Uses .venv so macOS PEP 668 does not block pip.

Conflict handling (git pull / stash pop):
  SYNC_KEEP=local   prefer your stashed edits on conflict (default)
  SYNC_KEEP=remote  prefer origin/main on conflict
  SYNC_KEEP=manual  leave conflict markers; exit non-zero
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ENV_PATH = ROOT / ".env"
ENV_EXAMPLE = ROOT / ".env.example"
VENV = ROOT / ".venv"
REQS = (ROOT / "requirements.txt", ROOT / "infra" / "modal" / "requirements.txt")
SECRET_KEYS = ("HF_TOKEN", "MUBIT_API_KEY")
# Local noise we do not stash/commit through sync.
SKIP_DIRTY_PREFIXES = (".vscode/", ".vscode")


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


def parse_dotenv(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        return out
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        out[key.strip()] = value.strip().strip("'").strip('"')
    return out


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def keep_mode() -> str:
    mode = os.environ.get("SYNC_KEEP", "local").strip().lower()
    if mode not in {"local", "remote", "manual"}:
        print(f"unknown SYNC_KEEP={mode!r}; using local")
        return "local"
    return mode


def porcelain_paths(porcelain: str) -> list[str]:
    paths: list[str] = []
    for ln in porcelain.splitlines():
        if not ln.strip():
            continue
        path = ln[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.append(path)
    return paths


def meaningful_dirty(porcelain: str) -> bool:
    for path in porcelain_paths(porcelain):
        if any(path == p or path.startswith(p if p.endswith("/") else p + "/") for p in SKIP_DIRTY_PREFIXES):
            continue
        if path == ".env":
            continue
        return True
    return False


def unmerged_paths() -> list[str]:
    out = run(["git", "diff", "--name-only", "--diff-filter=U"], capture=True).stdout.strip()
    if not out:
        return []
    return [p for p in out.splitlines() if p.strip()]


def git_dir() -> Path:
    raw = run(["git", "rev-parse", "--git-dir"], capture=True).stdout.strip()
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def in_merge_or_rebase() -> bool:
    gd = git_dir()
    return (gd / "MERGE_HEAD").exists() or (gd / "rebase-merge").exists() or (gd / "rebase-apply").exists()


def resolve_conflicts(paths: list[str], *, source: str) -> bool:
    """Resolve unmerged paths. Returns True if clean afterward.

    For stash pop: ours=HEAD (post-pull/remote), theirs=stash (local).
    For merge pull: ours=local branch tip, theirs=origin.
    `source` is 'stash' or 'merge' so local/remote map correctly.
    """
    mode = keep_mode()
    if not paths:
        return True
    print(f"conflicts in {len(paths)} file(s):")
    for p in paths:
        print(f"  - {p}")

    if mode == "manual":
        print("SYNC_KEEP=manual: left conflict markers. Fix, git add, then re-run make sync")
        return False

    # Map preference onto git checkout --ours/--theirs.
    if source == "stash":
        # stash pop: theirs = stashed local work, ours = current (pulled) tree
        which = "--theirs" if mode == "local" else "--ours"
    else:
        # merge: ours = local commits, theirs = incoming origin
        which = "--ours" if mode == "local" else "--theirs"

    print(f"resolving with SYNC_KEEP={mode} ({which} for {source})")
    for p in paths:
        run(["git", "checkout", which, "--", p], check=False)
        run(["git", "add", "--", p], check=False)

    left = unmerged_paths()
    if left:
        print("still unmerged after auto-resolve:")
        for p in left:
            print(f"  - {p}")
        return False
    print("conflicts resolved")
    return True


def ensure_env() -> None:
    step("env")
    if not ENV_EXAMPLE.is_file():
        print("missing .env.example")
        return
    if not ENV_PATH.is_file():
        shutil.copy(ENV_EXAMPLE, ENV_PATH)
        print("created .env from .env.example (fill keys locally; do not commit)")
        return

    example_lines = ENV_EXAMPLE.read_text().splitlines()
    existing = parse_dotenv(ENV_PATH)
    added: list[str] = []
    for raw in example_lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key = stripped.split("=", 1)[0].strip()
        if key and key not in existing:
            with ENV_PATH.open("a") as fh:
                fh.write("\n" + raw + "\n")
            existing[key] = ""
            added.append(key)
    if added:
        print(f"added missing keys to .env: {', '.join(added)} (values left blank)")
    else:
        print(".env present; no new keys from .env.example")
    present = [k for k in SECRET_KEYS if existing.get(k)]
    missing = [k for k in SECRET_KEYS if not existing.get(k)]
    if present:
        print(f"secret keys set locally: {', '.join(present)}")
    if missing:
        print(f"secret keys still blank: {', '.join(missing)}")


def finish_merge_if_clean() -> bool:
    """If a merge is in progress and conflicts are gone, commit it."""
    merge_head = git_dir() / "MERGE_HEAD"
    if not merge_head.exists():
        return True
    if unmerged_paths():
        return False
    run(
        ["git", "commit", "--no-edit", "-m", "Merge origin during make sync"],
        check=False,
    )
    return not merge_head.exists()


def pull_git() -> bool:
    """Pull origin. Returns True if ok to continue sync."""
    step("git pull")
    run(["git", "fetch", "origin", "--prune"])

    existing = unmerged_paths()
    if existing or in_merge_or_rebase():
        print("repo already has unresolved conflicts or an unfinished merge/rebase")
        if keep_mode() == "manual":
            print("SYNC_KEEP=manual: resolve manually, then re-run make sync")
            return False
        source = "merge"
        if not resolve_conflicts(existing or unmerged_paths(), source=source):
            return False
        if not finish_merge_if_clean():
            print("could not finish in-progress merge; resolve manually")
            return False

    branch = run(["git", "branch", "--show-current"], capture=True).stdout.strip() or "main"
    upstream = f"origin/{branch}"
    # Ensure upstream ref exists
    has_upstream = run(["git", "rev-parse", "--verify", upstream], check=False, capture=True).returncode == 0
    if not has_upstream:
        print(f"no {upstream} yet; skip pull")
        return True

    dirty = run(["git", "status", "--porcelain"], capture=True).stdout
    stashed = False
    if meaningful_dirty(dirty):
        print("stashing local changes for pull")
        run(["git", "stash", "push", "-u", "-m", "baansafe-sync"])
        stashed = True
    elif dirty.strip():
        print("local noise only (.vscode/.env); pull without stash")

    # Prefer fast-forward.
    result = run(["git", "pull", "--ff-only"], check=False, capture=True)
    if result.returncode != 0:
        print("ff-only pull not possible; trying merge pull")
        merge = run(["git", "pull", "--no-rebase", "--no-edit"], check=False, capture=True)
        if merge.returncode != 0:
            print(merge.stdout or "")
            print(merge.stderr or "")
            conflicts = unmerged_paths()
            if conflicts:
                if not resolve_conflicts(conflicts, source="merge"):
                    if stashed:
                        print("keeping stash 'baansafe-sync'; run: git stash pop")
                    return False
                if not finish_merge_if_clean():
                    print("merge commit failed; resolve manually")
                    if stashed:
                        print("keeping stash 'baansafe-sync'")
                    return False
                print("merge pull completed with auto-resolved conflicts")
            else:
                print("pull failed without conflict markers; resolve locally")
                if stashed:
                    run(["git", "stash", "pop"], check=False)
                return False
        else:
            out = (merge.stdout or "").strip() or "merged"
            print(out.splitlines()[-1])
    else:
        out = (result.stdout or "").strip() or "up to date"
        print(out.splitlines()[-1] if out else "up to date")

    if stashed:
        pop = run(["git", "stash", "pop"], check=False, capture=True)
        if pop.returncode != 0:
            print(pop.stdout or "")
            print(pop.stderr or "")
            conflicts = unmerged_paths()
            if conflicts:
                if not resolve_conflicts(conflicts, source="stash"):
                    print("stash kept if still listed in: git stash list")
                    return False
                # stash pop with conflicts leaves index dirty but drops stash only on success;
                # after resolving, clear conflict state by ensuring files are added.
                print("restored stashed local changes (auto-resolved)")
            else:
                print("stash pop failed; try: git stash pop")
                return False
        else:
            print("restored stashed local changes")
    return True


def install_deps() -> Path:
    step("python deps (.venv)")
    py = venv_python()
    if not py.is_file():
        print(f"creating {VENV.relative_to(ROOT)}")
        run([sys.executable, "-m", "venv", str(VENV)])
        py = venv_python()
    for req in REQS:
        if not req.is_file():
            continue
        print(f"pip install -r {req.relative_to(ROOT)}")
        run([str(py), "-m", "pip", "install", "-q", "-U", "pip"])
        run([str(py), "-m", "pip", "install", "-q", "-r", str(req)])
    print(f"deps ok ({py})")
    return py


def modal_ready(py: Path) -> bool:
    step("modal")
    modal_bin = py.parent / ("modal.exe" if sys.platform == "win32" else "modal")
    modal_cmd = [str(modal_bin)] if modal_bin.is_file() else ["modal"]
    if not modal_bin.is_file() and not shutil.which("modal"):
        print("modal CLI missing; pip install -r infra/modal/requirements.txt into .venv")
        return False
    ver = run([*modal_cmd, "--version"], check=False, capture=True)
    print((ver.stdout or ver.stderr or "modal").strip())
    profile = run([*modal_cmd, "profile", "current"], check=False, capture=True)
    if profile.returncode != 0:
        print("not logged in. Run: modal token new")
        return False
    name = (profile.stdout or "").strip() or "(default)"
    print(f"logged in as profile {name}")
    return True


def sync_secrets(py: Path, logged_in: bool) -> None:
    step("modal secrets")
    if not logged_in:
        print("skipped (modal not logged in)")
        return
    keys = parse_dotenv(ENV_PATH)
    if not all(keys.get(k) for k in SECRET_KEYS):
        print("skipped (need HF_TOKEN and MUBIT_API_KEY in .env)")
        return
    env = os.environ.copy()
    env["PATH"] = str(py.parent) + os.pathsep + env.get("PATH", "")
    subprocess.run(
        [str(py), str(ROOT / "scripts" / "sync_modal_secrets.py")],
        cwd=ROOT,
        check=True,
        env=env,
    )


def push_readiness() -> None:
    step("push readiness")
    branch = run(["git", "branch", "--show-current"], capture=True).stdout.strip()
    status = run(["git", "status", "-sb"], capture=True).stdout.strip()
    print(status)
    ahead = behind = 0
    if "ahead " in status or "behind " in status:
        m = re.search(r"ahead (\d+)", status)
        if m:
            ahead = int(m.group(1))
        m = re.search(r"behind (\d+)", status)
        if m:
            behind = int(m.group(1))
    dirty = run(["git", "status", "--porcelain"], capture=True).stdout.strip()
    if behind:
        print(f"behind origin/{branch} by {behind}; run make sync again if pull did not finish")
    if dirty and meaningful_dirty(dirty + "\n"):
        print("local changes present (not committed). make push MSG='...' when ready; .env stays gitignored.")
    if ahead and not behind and not meaningful_dirty(dirty + "\n" if dirty else ""):
        print(f"{ahead} commit(s) ready to push on {branch}")
    elif ahead and meaningful_dirty(dirty + "\n" if dirty else ""):
        print(f"{ahead} commit(s) ahead, plus uncommitted files")
    elif not ahead and not meaningful_dirty(dirty + "\n" if dirty else "") and not behind:
        print("in sync with origin; nothing to push")

    print("tip: make push                 # send secrets + commits")
    print("tip: make push MSG='summary'   # commit local work, then push")
    print("tip: SYNC_KEEP=local|remote|manual  # conflict preference (default local)")
    print("tip: source .venv/bin/activate")


def main() -> int:
    print("BaanSafe sync (shared)")
    if not pull_git():
        print("\nsync stopped: git conflicts need attention")
        print("  SYNC_KEEP=local   make sync   # prefer your edits (default)")
        print("  SYNC_KEEP=remote  make sync   # prefer origin")
        print("  SYNC_KEEP=manual  make sync   # leave markers for you")
        return 1
    ensure_env()
    py = install_deps()
    logged_in = modal_ready(py)
    sync_secrets(py, logged_in)
    push_readiness()
    print("\ndone")
    return 0


if __name__ == "__main__":
    sys.exit(main())
