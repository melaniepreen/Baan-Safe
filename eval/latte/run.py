"""Run latte-bench by reference, or skip when bun or the checkout is missing.

Free mode replays the calibrated reference and writes eval/out/latte-reference.json.
It does not call an API. LATTE_SERVE=1 runs `bun install && bun run dev` with
gateway secrets removed, which is the UI path for "Try without an API".
LATTE_LIVE=1 is that same UI with Mubit gateway env required.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from eval.latte.env import GatewayEnvError, build_live_env, describe_live_env, free_child_env
from eval.latte.pin import PIN, SUBMODULE
from paths import ROOT

RUNNER = ROOT / "eval" / "latte" / "reference_runner.mjs"


def bun_path() -> str | None:
    return shutil.which("bun")


def checkout_present() -> bool:
    return (SUBMODULE / "package.json").is_file() and (SUBMODULE / "src" / "plans.js").is_file()


def checkout_head() -> str | None:
    if not checkout_present():
        return None
    proc = subprocess.run(
        ["git", "-C", str(SUBMODULE), "rev-parse", "HEAD"],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def skip_reason() -> str | None:
    if bun_path() is None:
        return "skipped: bun is not installed"
    if not checkout_present():
        return (
            "skipped: third_party/latte-bench is not checked out "
            "(git submodule update --init third_party/latte-bench)"
        )
    return None


def _install(bun: str) -> int:
    print("bun install (submodule dependencies; no API call)", flush=True)
    proc = subprocess.run(
        [bun, "install", "--frozen-lockfile"],
        cwd=SUBMODULE,
        check=False,
    )
    return proc.returncode


def run_reference(out_dir: Path | None = None) -> int:
    reason = skip_reason()
    if reason:
        print(reason, flush=True)
        return 0
    head = checkout_head()
    if head != PIN:
        print(f"third_party/latte-bench is at {head or 'unknown'}, pin is {PIN}", flush=True)
        return 1
    bun = bun_path()
    assert bun is not None
    if _install(bun) != 0:
        return 1
    dest_dir = out_dir or (ROOT / "eval" / "out")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / "latte-reference.json"
    env = free_child_env()
    env["LATTE_PIN"] = PIN
    print("calibrated reference (no API call)", flush=True)
    proc = subprocess.run(
        [bun, str(RUNNER), str(SUBMODULE), str(dest)],
        cwd=SUBMODULE,
        env=env,
        check=False,
    )
    if proc.returncode == 0:
        print(dest, flush=True)
    return proc.returncode


def serve(live: bool) -> int:
    reason = skip_reason()
    if reason:
        print(reason, flush=True)
        return 0
    head = checkout_head()
    if head != PIN:
        print(f"third_party/latte-bench is at {head or 'unknown'}, pin is {PIN}", flush=True)
        return 1
    bun = bun_path()
    assert bun is not None
    if live:
        try:
            child = build_live_env()
        except GatewayEnvError as exc:
            print(str(exc), flush=True)
            return 1
        env = free_child_env()
        env.update(child)
        print("bun run dev (live gateway; secrets are not printed)", flush=True)
        print(describe_live_env(child), flush=True)
    else:
        env = free_child_env()
        print("bun run dev (free UI; gateway secrets removed from this process)", flush=True)
    if _install(bun) != 0:
        return 1
    proc = subprocess.run([bun, "run", "dev"], cwd=SUBMODULE, env=env, check=False)
    return proc.returncode


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if args and args[0] in ("-h", "--help"):
        print(
            "make latte-bench             # calibrated reference, no API\n"
            "make latte-bench LATTE_SERVE=1  # bun install && bun run dev, free UI\n"
            "make latte-bench LATTE_LIVE=1   # bun run dev through the Mubit gateway"
        )
        return 0
    live = os.environ.get("LATTE_LIVE", "").strip() == "1"
    serve_ui = live or os.environ.get("LATTE_SERVE", "").strip() == "1"
    if serve_ui:
        return serve(live=live)
    return run_reference()
