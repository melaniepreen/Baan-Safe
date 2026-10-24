"""System 1 classifier on Modal.

CPU or T4/L4. The model id comes from modal.s1_model_id or S1_MODEL_ID.
A Laya checkpoint is loaded with laya.load. Anything else is a multilingual
zero-shot NLI pipeline (the mDeBERTa shape). No model id is hardcoded.
"""

from __future__ import annotations

import json
import threading

import modal

from infra.modal.common import parse_gpu, redact, resolve
from infra.modal.runtime import HF_CACHE_PATH, hf_cache, hf_secret, mubit_secret, with_repo

MODEL_ID = resolve("modal.s1_model_id", "S1_MODEL_ID")
GPU = parse_gpu(resolve("modal.s1_gpu", "S1_GPU"), allow_cpu=True)
GPU_LABEL = "cpu" if GPU is None else GPU

image = with_repo(
    modal.Image.debian_slim(python_version="3.12").pip_install(
        "fastapi>=0.115",
        "uvicorn>=0.30",
        "pydantic>=2.6",
        "transformers>=4.46",
        "sentencepiece",
        "protobuf",
        "huggingface_hub",
        "laya>=0.4.14",
    )
).env(
    {
        "S1_MODEL_ID": MODEL_ID,
        "S1_GPU": GPU_LABEL,
        "HF_HOME": HF_CACHE_PATH,
        "USE_TF": "0",
    }
)

app = modal.App("baansafe-s1", image=image)
cache = hf_cache()
_backend: tuple | None = None


def _load():
    import torch
    from huggingface_hub import snapshot_download

    try:
        snapshot_download(MODEL_ID, token=_token())
        cache.commit()
    except Exception as exc:
        raise RuntimeError(redact(f"model download failed: {exc}")) from None
    device = "cuda" if torch.cuda.is_available() else "cpu"
    if "laya" in MODEL_ID.lower():
        import laya

        return ("laya", laya.load(MODEL_ID), device)
    from transformers import pipeline

    clf = pipeline(
        "zero-shot-classification",
        model=MODEL_ID,
        device=0 if device == "cuda" else -1,
    )
    return ("nli", clf, device)


def _token() -> str | None:
    import os

    token = os.environ.get("HF_TOKEN", "").strip()
    return token or None


def _predict(payload: dict) -> dict:
    if _backend is None:
        raise RuntimeError("classifier is not loaded")
    kind, model, _device = _backend
    text = payload.get("text") or ""
    if not text.strip():
        raise ValueError("text is empty")
    if kind == "laya":
        questions = payload.get("questions")
        if not questions:
            labels = payload.get("candidate_labels") or []
            if not labels:
                raise ValueError("send questions or candidate_labels")
            questions = {
                "label": {
                    "type": "choice",
                    "instructions": "Which label fits this text?",
                    "criteria": {str(label): str(label) for label in labels},
                }
            }
        result = model.predict(text, questions)
        body = json.loads(json.dumps(result, default=str))
        return {"model_id": MODEL_ID, "backend": "laya", "result": body}
    labels = payload.get("candidate_labels") or []
    if not labels:
        raise ValueError("candidate_labels is required for the NLI backend")
    template = payload.get("hypothesis_template") or "This example is {}."
    scored = model(text, labels, hypothesis_template=template, multi_label=True)
    return {
        "model_id": MODEL_ID,
        "backend": "nli",
        "labels": scored["labels"],
        "scores": scored["scores"],
    }


def _fastapi():
    from fastapi import FastAPI, HTTPException
    from pydantic import BaseModel, ConfigDict

    class ClassifyIn(BaseModel):
        model_config = ConfigDict(extra="allow")

        text: str
        candidate_labels: list[str] | None = None
        hypothesis_template: str | None = None
        questions: dict | None = None

    api = FastAPI(title="BaanSafe System 1", version="0.1.0")

    @api.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "baansafe-s1", "model_id": MODEL_ID, "gpu": GPU_LABEL}

    @api.post("/classify")
    def classify(body: ClassifyIn) -> dict:
        try:
            return _predict(body.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=redact(str(exc))) from None
        except Exception as exc:
            raise HTTPException(status_code=500, detail=redact(str(exc))) from None

    return api


@app.function(
    image=image,
    gpu=GPU,
    cpu=1.0,
    secrets=[hf_secret(), mubit_secret()],
    volumes={HF_CACHE_PATH: cache},
    scaledown_window=120,
    timeout=3600,
    startup_timeout=1200,
)
@modal.web_server(8000, startup_timeout=180)
def serve() -> None:
    global _backend
    _backend = _load()
    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config(_fastapi(), host="0.0.0.0", port=8000, log_level="info")
    )
    threading.Thread(target=server.run, daemon=True).start()
