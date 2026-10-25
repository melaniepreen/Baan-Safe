"""One-command quick start for the BaanSafe demo backend and town UI.

Subcommands: `backend` (API only), `frontend` (open the town against a
running backend), `up` (backend + open), `stop` (SIGTERM the recorded
backend). The Makefile wraps them as `make demo`, `make backend`,
`make frontend`, `make demo-stop`.

Knobs come from the environment, so `DEMO_PORT=8001 make demo` and
`DEMO_S2_IMPL=stub make backend` work the same way:

    DEMO_PORT   listen port (default 8000)
    DEMO_HOST   bind host (default 127.0.0.1)
    DEMO_DIR    state dir: memory, traces, corrections, recorded replies,
                backend.pid (default var/demo, relative to the repo root)
    DEMO_URL    base URL `frontend` opens (default http://<host>:<port>)
    DEMO_WAIT   seconds `up`/`frontend` wait for /health (default 30)
    OPEN        1 opens a browser, 0 prints the URLs (default 1)
    RESET       1 runs scripts/demo_reset.py --yes before seeding; the
                recorded S2 replies are kept (default 0)

The env build always picks the demo config for the DEMO_KEYS
(S1_IMPL=real, S2_IMPL=cache, S2_CACHE_KEY=case, MEMORY_IMPL=local, the
DEMO_DIR state files): a shell that exports `S2_IMPL=stub` does not
change the demo — only `DEMO_S2_IMPL=stub` overrides it, and the banner
names anything the shell exported that the demo is ignoring. Every other
name (including the Mubit vars) passes through unchanged. No Mubit value
is read beyond presence; nothing here prints a secret.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from memory.content import LANE_POLICY  # noqa: E402

PID_NAME = "backend.pid"
HEALTH_TIMEOUT_S = 2
STOP_GRACE_S = 10

_FRONTEND_PAGES = ("/ui/sim/", "/ui/training.html")


def _demo_dir(base: Mapping[str, str]) -> Path:
    raw = (base.get("DEMO_DIR") or "var/demo").strip() or "var/demo"
    path = Path(raw)
    return path if path.is_absolute() else ROOT / path


def _port(base: Mapping[str, str]) -> int:
    return int((base.get("DEMO_PORT") or "8000").strip())


def _host(base: Mapping[str, str]) -> str:
    return (base.get("DEMO_HOST") or "127.0.0.1").strip() or "127.0.0.1"


def _demo_url(base: Mapping[str, str]) -> str:
    raw = (base.get("DEMO_URL") or "").strip()
    if raw:
        return raw.rstrip("/")
    return f"http://{_host(base)}:{_port(base)}"


def _truthy(base: Mapping[str, str], name: str, default: str) -> bool:
    return (base.get(name) or default).strip() == "1"


DEMO_KEYS = (
    "S1_IMPL",
    "S2_IMPL",
    "S2_CACHE_KEY",
    "MEMORY_IMPL",
    "MEMORY_LOCAL_PATH",
    "S2_CACHE_RECORD_PATH",
    "TRACE_PATH",
    "MOCK_CORRECTIONS_PATH",
)


def _demo_defaults(base: Mapping[str, str]) -> dict[str, str]:
    demo_dir = _demo_dir(base)
    return {
        "S1_IMPL": "real",
        "S2_IMPL": "cache",
        "S2_CACHE_KEY": "case",
        "MEMORY_IMPL": "local",
        "MEMORY_LOCAL_PATH": str(demo_dir / "memory.jsonl"),
        "S2_CACHE_RECORD_PATH": str(demo_dir / "s2_cache.jsonl"),
        "TRACE_PATH": str(demo_dir / "traces.jsonl"),
        "MOCK_CORRECTIONS_PATH": str(demo_dir / "corrections.jsonl"),
    }


def demo_env(base: Mapping[str, str]) -> dict[str, str]:
    """The child-process env. The demo config wins: a DEMO_KEY is taken
    from base["DEMO_" + key] when set and non-empty, else the demo
    default — never the ambient base[key]. Every other name passes
    through unchanged."""
    defaults = _demo_defaults(base)
    env = dict(base)
    for key in DEMO_KEYS:
        override = (base.get("DEMO_" + key) or "").strip()
        env[key] = override if override else defaults[key]
    return env


def shell_overrides(base: Mapping[str, str]) -> list[tuple[str, str, str]]:
    """(name, shell value, demo value) for each DEMO_KEY the calling
    shell exports that the demo ignores. A set DEMO_<name> override
    means the shell value was not ignored, so it is not listed."""
    env = demo_env(base)
    out: list[tuple[str, str, str]] = []
    for key in DEMO_KEYS:
        if (base.get("DEMO_" + key) or "").strip():
            continue
        shell = (base.get(key) or "").strip()
        if shell and shell != env[key]:
            out.append((key, shell, env[key]))
    return out


def _pid_path(env: Mapping[str, str]) -> Path:
    return _demo_dir(env) / PID_NAME


def _has_policy_row(path: Path) -> bool:
    if not path.exists():
        return False
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if str(row.get("lane") or "") == LANE_POLICY:
                return True
    return False


def ensure_seeded(env: Mapping[str, str]) -> bool:
    """Seed the 10 policy lessons when the store has none. Idempotent."""
    memory_path = Path(env["MEMORY_LOCAL_PATH"])
    if _has_policy_row(memory_path):
        return False
    memory_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "seed_memory.py")],
        env=dict(env),
        cwd=ROOT,
        check=True,
    )
    return True


def apply_reset(env: Mapping[str, str]) -> None:
    """Clear case memory, traces, and corrections; keep policy lessons and
    recorded S2 replies (an empty S2_CACHE_RECORD_PATH is 'unset' to
    demo_reset, and config/envfile never overrides a set name)."""
    reset_env = dict(env)
    reset_env["S2_CACHE_RECORD_PATH"] = ""
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "demo_reset.py"), "--yes"],
        env=reset_env,
        cwd=ROOT,
        check=True,
    )


def port_in_use(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(HEALTH_TIMEOUT_S)
        try:
            sock.connect((host, port))
        except OSError:
            return False
    return True


def wait_healthy(url: str, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url.rstrip("/") + "/health", timeout=HEALTH_TIMEOUT_S) as resp:
                if resp.status == 200:
                    return True
        except (OSError, urllib.error.URLError):
            pass
        time.sleep(0.25)
    return False


def mubit_creds_present(env: Mapping[str, str]) -> bool:
    """True when MUBIT_API_KEY and MUBIT_BASE_URL are both non-empty, in the
    env or in .env (names parsed only). Never prints or returns a value."""
    def _from(mapping: Mapping[str, str]) -> bool:
        return bool(mapping.get("MUBIT_API_KEY", "").strip()) and bool(
            mapping.get("MUBIT_BASE_URL", "").strip()
        )

    if _from(env):
        return True
    dotenv = ROOT / ".env"
    if not dotenv.exists():
        return False
    names: dict[str, bool] = {}
    for raw in dotenv.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        names[name.strip()] = bool(value.strip().strip('"').strip("'"))
    return bool(names.get("MUBIT_API_KEY")) and bool(names.get("MUBIT_BASE_URL"))


def _rel(path: Path) -> Path:
    try:
        return path.relative_to(ROOT)
    except ValueError:
        return path


def _banner(env: Mapping[str, str], url: str, ignored: list[tuple[str, str, str]]) -> str:
    demo_dir = _rel(_demo_dir(env))
    creds = mubit_creds_present(env)
    record_path = _rel(Path(env["S2_CACHE_RECORD_PATH"]))
    if creds:
        mubit = f"credentials found: a System 2 cache miss is one paid Nemotron call, recorded to {record_path}"
    else:
        mubit = "no Mubit credentials: a System 2 cache miss returns system2_unavailable, no network"
    lines = [
        "BaanSafe demo backend",
        f"  town      {url}/ui/sim/",
        f"  training  {url}/ui/training.html",
        f"  api docs  {url}/docs",
        f"  systems   S1_IMPL={env.get('S1_IMPL')} · S2_IMPL={env.get('S2_IMPL')} "
        f"(S2_CACHE_KEY={env.get('S2_CACHE_KEY')}) · MEMORY_IMPL={env.get('MEMORY_IMPL')}",
    ]
    if ignored:
        exported = ", ".join(f"{name}={shell}" for name, shell, _ in ignored)
        demo = ", ".join(f"{name}={value}" for name, _, value in ignored)
        lines.append(
            f"  note      your shell exports {exported}; the demo uses {demo} "
            f"(DEMO_{ignored[0][0]}=… overrides one)"
        )
    lines += [
        f"  mubit     {mubit}",
        f"  files     {demo_dir}/ (memory, traces, corrections, recorded replies)",
        "  Ctrl+C stops. From another terminal: make demo-stop",
    ]
    return "\n".join(lines)


def _open_frontend(url: str, open_browser: bool) -> None:
    for page in _FRONTEND_PAGES:
        target = url.rstrip("/") + page
        if open_browser:
            webbrowser.open(target)
        else:
            print(target)


def _wait_seconds(env: Mapping[str, str]) -> float:
    return float((env.get("DEMO_WAIT") or "30").strip() or "30")


def _prepare(env: Mapping[str, str]) -> None:
    """RESET then seed, in that order, so the lessons land on an empty store."""
    if _truthy(env, "RESET", "0"):
        apply_reset(env)
    ensure_seeded(env)


def _remove_pid_if_ours(pid_file: Path, pid: int) -> None:
    try:
        if int(pid_file.read_text(encoding="utf-8").strip()) == pid:
            pid_file.unlink(missing_ok=True)
    except (OSError, ValueError):
        pass


def _stop_child(proc: subprocess.Popen) -> None:
    proc.terminate()
    try:
        proc.wait(timeout=STOP_GRACE_S)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=STOP_GRACE_S)


def backend(
    env: Mapping[str, str],
    *,
    open_after: bool = False,
    ignored: list[tuple[str, str, str]] | None = None,
) -> int:
    host, port = _host(env), _port(env)
    url = _demo_url(env)
    if port_in_use(host, port):
        print(
            f"Port {port} is busy. Stop it with make demo-stop (if it is a demo backend) "
            f"or pick another port: DEMO_PORT=8001 make backend",
            file=sys.stderr,
        )
        return 1
    _prepare(env)
    demo_dir = _demo_dir(env)
    demo_dir.mkdir(parents=True, exist_ok=True)
    child_env = dict(env)
    child_env["PYTHONPATH"] = str(ROOT) + os.pathsep + child_env.get("PYTHONPATH", "")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "api.main:app", "--host", host, "--port", str(port)],
        env=child_env,
        cwd=ROOT,
    )
    pid_file = _pid_path(env)
    pid_file.write_text(str(proc.pid), encoding="utf-8")
    print(_banner(env, url, ignored or []), flush=True)

    if open_after:
        if wait_healthy(url, _wait_seconds(env)):
            _open_frontend(url, _truthy(env, "OPEN", "1"))
        else:
            print(f"Backend did not answer at {url}/health within {_wait_seconds(env):g} s.", file=sys.stderr)

    stop = {"requested": False}
    previous_sigterm = signal.getsignal(signal.SIGTERM)

    def _on_signal(signum, frame):
        stop["requested"] = True
        _stop_child(proc)

    signal.signal(signal.SIGTERM, _on_signal)
    try:
        proc.wait()
    except KeyboardInterrupt:
        if proc.poll() is None:
            _stop_child(proc)
    finally:
        signal.signal(signal.SIGTERM, previous_sigterm)
        _remove_pid_if_ours(pid_file, proc.pid)
    return 0 if stop["requested"] or proc.returncode in (0, -signal.SIGTERM, -signal.SIGINT) else (proc.returncode or 0)


def frontend(env: Mapping[str, str]) -> int:
    url = _demo_url(env)
    if not wait_healthy(url, _wait_seconds(env)):
        print(
            f"No backend answering at {url}/health. Start it with make backend (or make demo).",
            file=sys.stderr,
        )
        return 1
    _open_frontend(url, _truthy(env, "OPEN", "1"))
    return 0


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _pid_command(pid: int) -> str:
    try:
        out = subprocess.run(
            ["ps", "-o", "command=", "-p", str(pid)],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return out.stdout.strip()


def stop(env: Mapping[str, str]) -> int:
    pid_file = _pid_path(env)
    if not pid_file.exists():
        print(f"No demo backend recorded in {_demo_dir(env).relative_to(ROOT) if _demo_dir(env).is_relative_to(ROOT) else _demo_dir(env)}/{PID_NAME}.")
        if port_in_use(_host(env), _port(env)):
            print(f"Port {_port(env)} is busy, but something else is listening; leaving it alone.")
        return 0
    try:
        pid = int(pid_file.read_text(encoding="utf-8").strip())
    except ValueError:
        pid = -1
    command = _pid_command(pid) if pid > 0 else ""
    if pid > 0 and _pid_alive(pid) and "uvicorn" in command and "api.main:app" in command:
        os.kill(pid, signal.SIGTERM)
        deadline = time.monotonic() + STOP_GRACE_S
        while time.monotonic() < deadline and _pid_alive(pid):
            time.sleep(0.2)
        if _pid_alive(pid):
            print(f"Demo backend pid {pid} did not exit within {STOP_GRACE_S} s; check it yourself.")
            return 1
        _remove_pid_if_ours(pid_file, pid)
        print(f"Stopped demo backend pid {pid} on port {_port(env)}.")
        return 0
    print(f"Recorded pid {pid} is not a demo backend ({command or 'dead'}); removing the stale pid file.")
    pid_file.unlink(missing_ok=True)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("command", choices=["backend", "frontend", "up", "stop"])
    args = parser.parse_args(argv)
    env = demo_env(os.environ)
    ignored = shell_overrides(os.environ)
    if args.command == "backend":
        return backend(env, ignored=ignored)
    if args.command == "up":
        return backend(env, open_after=True, ignored=ignored)
    if args.command == "frontend":
        return frontend(env)
    return stop(env)


if __name__ == "__main__":
    raise SystemExit(main())
