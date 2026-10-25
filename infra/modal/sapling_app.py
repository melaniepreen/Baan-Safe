"""Banyan Sapling on Modal. A scaffold, not a vLLM server.

The checkpoint ships a custom verification head. This process is the
self-hosted backend a human may register with Mubit after `sapling.hosting`
is decided. It reads the model id and the GPU from config and refuses while
either value is TODO_HUMAN. It does not guess a fallback checkpoint.
"""

from __future__ import annotations

import os
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


def _load(local: str):
    if local not in sys.path:
        sys.path.insert(0, local)
    from inference import load_model

    return load_model(Path(local))


def _fastapi(loaded) -> object:
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel

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

    @api.post("/verify")
    def verify_endpoint(body: VerifyIn) -> dict:
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
            raise HTTPException(status_code=400, detail=redact(str(exc))) from None
        except Exception as exc:
            raise HTTPException(status_code=500, detail=redact(str(exc))) from None
        status = raw.get("status")
        verdict = _STATUS_TO_VERDICT.get(status)
        if verdict is None:
            raise HTTPException(status_code=502, detail=f"Unexpected Sapling status {status!r}.")
        return {
            "model_id": MODEL_ID,
            "verdict": verdict,
            "action": _ACTIONS[verdict],
            "status": status,
            "raw_label": raw.get("raw_label"),
            "probabilities": raw.get("probabilities"),
            "usage": raw.get("usage"),
        }

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
        local = snapshot_download(MODEL_ID, token=token)
        cache.commit()
    except Exception as exc:
        raise RuntimeError(redact(f"model download failed: {exc}")) from None
    loaded = _load(local)
    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config(_fastapi(loaded), host="0.0.0.0", port=PORT, log_level="info")
    )
    threading.Thread(target=server.run, daemon=True).start()
