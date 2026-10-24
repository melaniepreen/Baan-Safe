"""Optional Thai speech-to-text. Model id stays a human choice.

faster-whisper loads whatever checkpoint STT_MODEL_ID names. The language
defaults to Thai and can be overridden per request.
"""

from __future__ import annotations

import tempfile
import threading
from pathlib import Path

import modal

from infra.modal.common import parse_gpu, redact, resolve
from infra.modal.runtime import HF_CACHE_PATH, hf_cache, hf_secret, mubit_secret, with_repo

MODEL_ID = resolve("modal.stt_model_id", "STT_MODEL_ID")
GPU = parse_gpu(resolve("modal.stt_gpu", "STT_GPU"), allow_cpu=True)
GPU_LABEL = "cpu" if GPU is None else GPU

image = with_repo(
    modal.Image.debian_slim(python_version="3.12").pip_install(
        "fastapi>=0.115",
        "uvicorn>=0.30",
        "python-multipart",
        "faster-whisper>=1.1",
    )
).env(
    {
        "STT_MODEL_ID": MODEL_ID,
        "STT_GPU": GPU_LABEL,
        "HF_HOME": HF_CACHE_PATH,
    }
)

app = modal.App("baansafe-stt", image=image)
cache = hf_cache()
_model = None


def _load():
    from faster_whisper import WhisperModel

    device = "cuda" if GPU is not None else "cpu"
    compute = "float16" if device == "cuda" else "int8"
    return WhisperModel(MODEL_ID, device=device, compute_type=compute)


def _fastapi():
    from fastapi import FastAPI, File, Form, HTTPException, UploadFile

    api = FastAPI(title="BaanSafe speech-to-text", version="0.1.0")

    @api.get("/health")
    def health() -> dict:
        return {"status": "ok", "service": "baansafe-stt", "model_id": MODEL_ID, "gpu": GPU_LABEL}

    @api.post("/transcribe")
    async def transcribe(
        file: UploadFile = File(...),
        language: str = Form("th"),
    ) -> dict:
        if _model is None:
            raise HTTPException(status_code=503, detail="model is not loaded")
        audio = await file.read()
        if not audio:
            raise HTTPException(status_code=400, detail="empty audio")
        try:
            with tempfile.NamedTemporaryFile(suffix=Path(file.filename or "clip.wav").suffix or ".wav") as handle:
                handle.write(audio)
                handle.flush()
                segments, info = _model.transcribe(handle.name, language=language or None)
                text = "".join(segment.text for segment in segments).strip()
        except Exception as exc:
            raise HTTPException(status_code=500, detail=redact(str(exc))) from None
        return {
            "model_id": MODEL_ID,
            "language": getattr(info, "language", language),
            "text": text,
        }

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
    global _model
    _model = _load()
    import uvicorn

    server = uvicorn.Server(
        uvicorn.Config(_fastapi(), host="0.0.0.0", port=8000, log_level="info")
    )
    threading.Thread(target=server.run, daemon=True).start()
