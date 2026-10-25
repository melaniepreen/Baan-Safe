"""Banyan Sapling on Modal. A scaffold, not a vLLM server.

The checkpoint ships a custom verification head. This process is the
self-hosted backend a human may register with Mubit after `sapling.hosting`
is decided. It reads the model id and the GPU from config and refuses while
either value is TODO_HUMAN. It does not guess a fallback checkpoint.
"""

from __future__ import annotations

import hashlib
import os
import shutil
import sys
import threading
from pathlib import Path

import modal

from infra.modal.common import redact, resolve
from infra.modal.runtime import HF_CACHE_PATH, hf_cache, hf_secret, mubit_secret, with_repo
from infra.modal.sapling_gpu import require_sapling_gpu

MODEL_ID = resolve("sapling.model_id", "SAPLING_MODEL_ID")
GPU = require_sapling_gpu(resolve("sapling.gpu", "SAPLING_GPU"))
PORT = 8000

# Pins are runtime_versions.json on MubitLabs/banyan-sapling (24 October 2026).
# The card's reference CUDA is 13.0. This base image is the one the System 2
# app already uses; align it with that CUDA before a real deploy.
image = with_repo(
    modal.Image.from_registry(
        "nvidia/cuda:12.9.0-devel-ubuntu22.04",
        add_python="3.12",
    )
    .entrypoint([])
    .uv_pip_install(
        "torch==2.14.1",
        "transformers==5.17.0",
        "safetensors==0.8.0",
        "numpy==2.5.4",
        "tokenizers==0.23.3",
        "accelerate==1.15.0",
        "huggingface_hub==1.33.0",
        "fastapi>=0.115",
        "uvicorn>=0.30",
    ).env(
        {
            "SAPLING_MODEL_ID": MODEL_ID,
            "SAPLING_GPU": GPU,
            "HF_HOME": HF_CACHE_PATH,
        }
    )
)

app = modal.App("baansafe-sapling", image=image)
cache = hf_cache()

# Same map as system2/sapling_client.MODEL_LABELS. The GPU image does not
# import the API package; keep the two maps in step.
_STATUS_TO_VERDICT = {
    "supported": "supported",
    "violation": "violation",
    "insufficient_information": "missing",
    "inconsistent_context": "contradicted",
    "unsure": "unsure",
}
_ACTIONS = {
    "supported": "proceed",
    "violation": "block",
    "missing": "human_handoff",
    "contradicted": "human_handoff",
    "unsure": "human_handoff",
}


def _real_snapshot(snapshot: str) -> str:
    """Copy Hub cache links into a real directory.

    The checkpoint's verify_files() resolves each asset and refuses a path
    outside the snapshot root. snapshot_download links those assets at
    hub/blobs, so the first listed file (.gitattributes) fails that check.
    """
    src = Path(snapshot)
    dest = Path("/opt/banyan-sapling")
    if dest.exists():
        shutil.rmtree(dest)
    for path in src.rglob("*"):
        if "__pycache__" in path.parts or path.is_dir():
            continue
        target = dest / path.relative_to(src)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    return str(dest)


# distribution_manifest.json seals this pin list. The file now on the Hub is a
# shorter requirements.txt, and it is the only asset whose sha256 does not match.
_REQUIREMENTS_TXT = (
    "torch==2.14.1\n"
    "transformers==5.17.0\n"
    "safetensors==0.8.0\n"
    "numpy==2.5.4\n"
    "tokenizers==0.23.3\n"
    "accelerate==1.15.0\n"
    "huggingface-hub==1.33.0\n"
)
_REQUIREMENTS_SHA256 = "12177eb6258f0c164c27f261991f8fb1b035edaeac721c44e490a02c6a94b470"


def _restore_requirements(root: str) -> None:
    body = _REQUIREMENTS_TXT.encode()
    if hashlib.sha256(body).hexdigest() != _REQUIREMENTS_SHA256:
        raise RuntimeError("requirements.txt repair does not match the Sapling manifest.")
    path = Path(root) / "requirements.txt"
    if hashlib.sha256(path.read_bytes()).hexdigest() == _REQUIREMENTS_SHA256:
        return
    path.write_bytes(body)


def _load(local: str):
    if local not in sys.path:
        sys.path.insert(0, local)
    from inference import load_model

    return load_model(Path(local))


def _fastapi(loaded) -> object:
    from fastapi import FastAPI
    from pydantic import BaseModel, ValidationError
    from starlette.responses import JSONResponse
    from starlette.routing import Route

    class VerifyIn(BaseModel):
        policy: str
        evidence: str
        claim: str

    api = FastAPI(title="BaanSafe Sapling", version="0.1.0")

    @api.get("/health")
    def health() -> dict:
        return {
            "status": "ok",
            "service": "baansafe-sapling",
            "model_id": MODEL_ID,
            "gpu": GPU,
        }

    async def verify_endpoint(request):
        # A Starlette route, not a FastAPI parameter. Postponed annotations
        # made FastAPI look for the claim in the query string.
        try:
            body = VerifyIn.model_validate(await request.json())
        except (ValidationError, ValueError):
            return JSONResponse(
                {"detail": "Expected JSON with policy, evidence, and claim."},
                status_code=400,
            )
        from inference import predict

        model, tokenizer, calibrator, manifest = loaded
        try:
            raw = predict(
                model,
                tokenizer,
                calibrator,
                manifest,
                {"policy": body.policy, "evidence": body.evidence, "claim": body.claim},
            )
        except ValueError as exc:
            return JSONResponse({"detail": redact(str(exc))}, status_code=400)
        except Exception as exc:
            return JSONResponse({"detail": redact(str(exc))}, status_code=500)
        status = raw.get("status")
        verdict = _STATUS_TO_VERDICT.get(status)
        if verdict is None:
            return JSONResponse(
                {"detail": f"Unexpected Sapling status {status!r}."},
                status_code=502,
            )
        return JSONResponse(
            {
                "model_id": MODEL_ID,
                "verdict": verdict,
                "action": _ACTIONS[verdict],
                "status": status,
                "raw_label": raw.get("raw_label"),
                "probabilities": raw.get("probabilities"),
                "usage": raw.get("usage"),
            }
        )

    api.router.routes.append(Route("/verify", verify_endpoint, methods=["POST"]))

    return api


@app.function(
    image=image,
    gpu=GPU,
    secrets=[hf_secret(), mubit_secret()],
    volumes={HF_CACHE_PATH: cache},
    scaledown_window=120,
    timeout=3600,
    startup_timeout=1800,
)
@modal.web_server(PORT, startup_timeout=1800)
def serve() -> None:
    from huggingface_hub import snapshot_download

    try:
        token = os.environ.get("HF_TOKEN", "").strip() or None
        local = _real_snapshot(snapshot_download(MODEL_ID, token=token))
        _restore_requirements(local)
        cache.commit()
    except Exception as exc:
        raise RuntimeError(redact(f"model download failed: {exc}")) from None
    loaded = _load(local)
    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config(_fastapi(loaded), host="0.0.0.0", port=PORT, log_level="info")
    )
    threading.Thread(target=server.run, daemon=True).start()
