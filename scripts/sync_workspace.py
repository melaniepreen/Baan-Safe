"""Shared teammate sync: pull, env, venv deps, Modal CLI/secrets, push readiness.

Never prints secret values. Does not auto-push (set SYNC_PUSH=1 to push main).
Does not overwrite existing .env values. Adds missing keys from .env.example.
Uses .venv so macOS PEP 668 does not block pip.
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


def pull_git() -> None:
    step("git pull")
    run(["git", "fetch", "origin", "--prune"])
    dirty = run(["git", "status", "--porcelain"], capture=True).stdout.strip()
    stashed = False
    if dirty:
        print("stashing local changes for ff-only pull")
        run(["git", "stash", "push", "-u", "-m", "baansafe-sync"])
        stashed = True
    result = run(["git", "pull", "--ff-only"], check=False, capture=True)
    if result.returncode != 0:
        print(result.stdout or "")
        print(result.stderr or "")
        print("ff-only pull failed; resolve locally, then re-run make sync")
        if stashed:
            run(["git", "stash", "pop"], check=False)
        return
    out = (result.stdout or "").strip() or "up to date"
    print(out.splitlines()[-1] if out else "up to date")
    if stashed:
        pop = run(["git", "stash", "pop"], check=False, capture=True)
        if pop.returncode != 0:
            print(pop.stdout or "")
            print(pop.stderr or "")
            print("stash pop had conflicts; fix files, then continue")
        else:
            print("restored stashed local changes")


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
    # Prefer venv modal on PATH for the child.
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
        print(f"behind origin/{branch} by {behind}; pull/rebase before push")
    if dirty:
        print("local changes present (not committed). Commit when ready; .env stays gitignored.")
    if ahead and not behind and not dirty:
        print(f"{ahead} commit(s) ready to push on {branch}")
    elif ahead and dirty:
        print(f"{ahead} commit(s) ahead, plus uncommitted files")
    elif not ahead and not dirty and not behind:
        print("in sync with origin; nothing to push")

    if os.environ.get("SYNC_PUSH", "").strip() == "1":
        if branch != "main":
            print("SYNC_PUSH=1 ignored: only pushes main")
            return
        if behind:
            print("SYNC_PUSH=1 refused: branch is behind origin")
            return
        if not ahead:
            print("SYNC_PUSH=1: nothing ahead to push")
            return
        step("git push")
        run(["git", "push", "origin", "main"])
        print("pushed main")
    else:
        print("tip: make sync SYNC_PUSH=1  # push main when ahead and not behind")
        print("tip: source .venv/bin/activate  # use the synced interpreter")


def main() -> int:
    print("BaanSafe sync (shared)")
    pull_git()
    ensure_env()
    py = install_deps()
    logged_in = modal_ready(py)
    sync_secrets(py, logged_in)
    push_readiness()
    print("\ndone")
    return 0


if __name__ == "__main__":
    sys.exit(main())
