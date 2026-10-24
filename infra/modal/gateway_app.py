"""Public BaanSafe demo on Modal.

One `*.modal.run` URL serves the town (`/ui/sim/`), triage, cases, and
`POST /stt/transcribe`. The image installs `requirements.txt` and mounts this
repo at `/opt/baansafe`. System 1 and enrichment run without secrets
(`S1_IMPL=real`, `ENRICH_IMPL` auto via `ingest.store`). System 2, memory,
and Sapling stay stub/mock. No Modal secret is attached, so Nemotron is
never called.

`STT_UPSTREAM`, when it is an http(s) URL at deploy time, forwards speech
uploads to `{STT_UPSTREAM}/transcribe`. `S1_UPSTREAM`, `S2_UPSTREAM`, and
`SAPLING_UPSTREAM` are recorded on `GET /hosting` and do not replace
gateway outcomes: those apps do not return a gateway Outcome.

Runtime writes go to the `baansafe-demo` volume at `/data`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import httpx
import modal
from fastapi import FastAPI, Request
from modal import FilePatternMatcher


def _repo_on_path() -> None:
    """Find the repo for a file deploy, or the mounted tree inside Modal."""
    remote = Path("/opt/baansafe")
    root: Path | None = None
    if (remote / "paths.py").is_file() and (remote / "api" / "main.py").is_file():
        root = remote
    else:
        here = Path(__file__).resolve()
        for parent in here.parents:
            if (parent / "paths.py").is_file() and (parent / "api" / "main.py").is_file():
                root = parent
                break
    if root is None:
        raise RuntimeError(
            "infra/modal/gateway_app.py could not find the repo root "
            "(paths.py and api/main.py)."
        )
    text = str(root)
    if text not in sys.path:
        sys.path.insert(0, text)


_repo_on_path()

from infra.modal.common import repo_root  # noqa: E402

APP_NAME = "baansafe-gateway"
DATA_MOUNT = "/data"
DEMO_VOLUME = "baansafe-demo"
REMOTE_ROOT = "/opt/baansafe"
UPSTREAM_ENV_NAMES = ("S1_UPSTREAM", "S2_UPSTREAM", "SAPLING_UPSTREAM", "STT_UPSTREAM")

# Demo switches and writable paths. Nothing here is a secret.
# S1 + enrich need no key. S2 stays stub (no mubit_secret attached).
STUB_ENV = {
    "PYTHONPATH": REMOTE_ROOT,
    "PYTHONUNBUFFERED": "1",
    "S1_IMPL": "real",
    "S2_IMPL": "stub",
    "MEMORY_IMPL": "mock",
    "SAPLING_IMPL": "stub",
    # Empty = same auto as local serve: data if store.available() else off.
    "ENRICH_IMPL": "",
    "TRACE_PATH": f"{DATA_MOUNT}/traces.jsonl",
    "MOCK_CORRECTIONS_PATH": f"{DATA_MOUNT}/corrections.jsonl",
    "TRAINING_EVENTS_PATH": f"{DATA_MOUNT}/events.jsonl",
    "POLICY_PIN_DIR": f"{DATA_MOUNT}/policy-pins",
}


def http_upstream(name: str) -> str:
    """An http(s) URL from the environment, or empty. TODO_HUMAN is ignored."""
    value = os.environ.get(name, "").strip().rstrip("/")
    if value in {"", "TODO_HUMAN"}:
        return ""
    if value.startswith("https://") or value.startswith("http://"):
        return value
    return ""


def image_env() -> dict[str, str]:
    """Demo env, plus any upstream URLs exported in the shell that runs deploy.

    Empty STUB_ENV values (ENRICH_IMPL auto) are omitted so the process
    matches local serve: unset → data if store.available() else off.
    """
    env = {key: value for key, value in STUB_ENV.items() if value != ""}
    for name in UPSTREAM_ENV_NAMES:
        value = http_upstream(name)
        if value:
            env[name] = value
    return env


_DOCKERIGNORE = FilePatternMatcher.from_file(repo_root() / ".dockerignore")


def _ignore(path: Path) -> bool:
    """Skip secrets, git, and caches. Same idea as .dockerignore, plus .env.*."""
    if _DOCKERIGNORE(path):
        return True
    parts = path.parts
    if ".git" in parts or ".cursor" in parts or ".venv" in parts:
        return True
    if path.name == ".env" or path.name.startswith(".env."):
        return True
    if parts[:1] == ("var",):
        return True
    if len(parts) >= 2 and parts[0] == "training" and parts[1] == "out":
        return True
    return False


image = (
    modal.Image.debian_slim(python_version="3.12")
    .pip_install_from_requirements(str(repo_root() / "requirements.txt"))
    .env(image_env())
    .workdir(REMOTE_ROOT)
    .add_local_dir(repo_root(), remote_path=REMOTE_ROOT, ignore=_ignore)
)

app = modal.App(APP_NAME, image=image)
demo_data = modal.Volume.from_name(DEMO_VOLUME, create_if_missing=True)


def prepare_runtime_files() -> None:
    """Create the volume mount and policy-pins dir. The JSON data ships in the image."""
    mount = Path(DATA_MOUNT)
    mount.mkdir(parents=True, exist_ok=True)
    (mount / "policy-pins").mkdir(parents=True, exist_ok=True)


def _mount_routes(api: FastAPI) -> None:
    if not _has_route(api, "/stt/transcribe", "POST"):
        api.add_api_route("/stt/transcribe", transcribe, methods=["POST"])
    if not _has_route(api, "/hosting", "GET"):
        api.add_api_route("/hosting", hosting, methods=["GET"])


def _has_route(api: FastAPI, path: str, method: str) -> bool:
    for route in api.routes:
        methods = getattr(route, "methods", None) or set()
        if getattr(route, "path", None) == path and method in methods:
            return True
    return False


def build_asgi() -> FastAPI:
    """The existing FastAPI app, plus the demo speech route. No deploy required."""
    from api.main import app as api

    _mount_routes(api)
    return api


def _enrich_impl_label() -> str:
    """Match api.deps.enrich_impl: empty means auto via store.available()."""
    raw = os.environ.get("ENRICH_IMPL", STUB_ENV["ENRICH_IMPL"]).strip().lower()
    if raw:
        return raw
    from ingest import store

    return "data" if store.available() else "off"


def _backends_label(impl: dict[str, str]) -> str:
    s1 = impl.get("S1_IMPL", "stub")
    s2 = impl.get("S2_IMPL", "stub")
    if s1 == "real" and s2 == "stub":
        return "s1-real"
    if s1 == "real" and s2 == "real":
        return "live"
    return "stub"


def hosting() -> dict:
    impl = {
        "S1_IMPL": os.environ.get("S1_IMPL", STUB_ENV["S1_IMPL"]),
        "S2_IMPL": os.environ.get("S2_IMPL", STUB_ENV["S2_IMPL"]),
        "MEMORY_IMPL": os.environ.get("MEMORY_IMPL", STUB_ENV["MEMORY_IMPL"]),
        "SAPLING_IMPL": os.environ.get("SAPLING_IMPL", STUB_ENV["SAPLING_IMPL"]),
        "ENRICH_IMPL": _enrich_impl_label(),
    }
    note = (
        "System 1 runs the rules path (S1_IMPL=real). "
        "Enrichment reads shipped JSON via ingest.store (no secret). "
        "System 2, memory, and Sapling stay stub/mock; no mubit_secret attached. "
        "S1_UPSTREAM, S2_UPSTREAM, and SAPLING_UPSTREAM do not replace gateway outcomes. "
        "STT_UPSTREAM forwards POST /stt/transcribe and invents no words."
    )
    return {
        "app": APP_NAME,
        "backends": _backends_label(impl),
        "secrets": False,
        "impl": impl,
        "upstreams": {name: bool(http_upstream(name)) for name in UPSTREAM_ENV_NAMES},
        "writes": {
            "TRACE_PATH": os.environ.get("TRACE_PATH", STUB_ENV["TRACE_PATH"]),
            "MOCK_CORRECTIONS_PATH": os.environ.get(
                "MOCK_CORRECTIONS_PATH", STUB_ENV["MOCK_CORRECTIONS_PATH"]
            ),
            "TRAINING_EVENTS_PATH": os.environ.get(
                "TRAINING_EVENTS_PATH", STUB_ENV["TRAINING_EVENTS_PATH"]
            ),
            "POLICY_PIN_DIR": os.environ.get("POLICY_PIN_DIR", STUB_ENV["POLICY_PIN_DIR"]),
        },
        "note": note,
    }


def _empty_transcript(note: str) -> dict:
    return {"text": "", "stub": True, "language": None, "note": note}


async def transcribe(request: Request) -> dict:
    """Stub transcript, or a forward to the deployed speech app. Never invents words."""
    upstream = http_upstream("STT_UPSTREAM")
    if not upstream:
        return _empty_transcript(
            "speech-to-text is not live. "
            "Set STT_UPSTREAM to the baansafe-stt web URL to forward this upload. "
            "No words were invented."
        )
    content_type = request.headers.get("content-type")
    headers = {"content-type": content_type} if content_type else {}
    try:
        body = await request.body()
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"{upstream}/transcribe",
                content=body,
                headers=headers,
            )
        payload = response.json()
    except Exception:
        return _empty_transcript(
            "STT_UPSTREAM did not return a transcript. No words were invented."
        )
    text = payload.get("text") if isinstance(payload, dict) else ""
    if not isinstance(text, str):
        text = ""
    text = text.strip()
    if not text:
        return _empty_transcript(
            "The speech service returned no words. No words were invented."
        )
    language = payload.get("language") if isinstance(payload, dict) else None
    return {"text": text, "stub": False, "language": language}


@app.function(
    image=image,
    cpu=1.0,
    volumes={DATA_MOUNT: demo_data},
    scaledown_window=120,
    timeout=120,
    include_source=False,
)
@modal.asgi_app()
def web():
    prepare_runtime_files()
    return build_asgi()
