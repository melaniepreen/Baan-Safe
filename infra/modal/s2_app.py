"""System 2 Nemotron server. OpenAI-compatible vLLM, for Mubit to route to.

Mubit stays the application hop. This process is the self-hosted backend a
human registers in the Mubit console. It does not call Mubit itself.
"""

from __future__ import annotations

import os
import subprocess
import sys

import modal

from infra.modal.common import parse_gpu, parse_quant, redact, resolve
from infra.modal.runtime import HF_CACHE_PATH, hf_cache, hf_secret, mubit_secret, with_repo
from infra.modal.s2_cmd import VLLM_PORT, check_fit, vllm_argv
from infra.modal.vram import match_model, weight_gib

MODEL_ID = resolve("modal.s2_model_id", "S2_MODEL_ID")
SIZE = resolve("modal.nemotron_size", "NEMOTRON_SIZE")
QUANT = parse_quant(resolve("modal.s2_quant", "S2_QUANT"))
GPU = parse_gpu(resolve("modal.s2_gpu", "S2_GPU"), allow_cpu=False)
assert GPU is not None
check_fit(MODEL_ID, SIZE, QUANT, GPU)

image = with_repo(
    modal.Image.from_registry(
        "nvidia/cuda:12.9.0-devel-ubuntu22.04",
        add_python="3.12",
    )
    .entrypoint([])
    .uv_pip_install("vllm==0.21.0", "huggingface_hub")
).env(
    {
        "S2_MODEL_ID": MODEL_ID,
        "NEMOTRON_SIZE": SIZE,
        "S2_QUANT": QUANT,
        "S2_GPU": GPU,
        "HF_HOME": HF_CACHE_PATH,
    }
)

app = modal.App("baansafe-s2", image=image)
cache = hf_cache()


def _memory_mb() -> int:
    model = match_model(MODEL_ID, SIZE)
    if model is None:
        return 16384
    return max(8192, min(131072, int((weight_gib(model["params"], QUANT) + 6) * 1024)))


@app.function(
    image=image,
    gpu=GPU,
    memory=_memory_mb(),
    secrets=[hf_secret(), mubit_secret()],
    volumes={HF_CACHE_PATH: cache},
    scaledown_window=120,
    timeout=3600,
    startup_timeout=1800,
)
@modal.web_server(VLLM_PORT, startup_timeout=1800)
def serve() -> None:
    from huggingface_hub import snapshot_download

    try:
        token = os.environ.get("HF_TOKEN", "").strip() or None
        snapshot_download(MODEL_ID, token=token)
        cache.commit()
    except Exception as exc:
        raise RuntimeError(redact(f"model download failed: {exc}")) from None
    env = os.environ.copy()
    serve_key = os.environ.get("S2_SERVE_API_KEY", "").strip()
    if serve_key:
        env["VLLM_API_KEY"] = serve_key
    else:
        print(
            "S2_SERVE_API_KEY is unset. The OpenAI port will not require a bearer token.",
            file=sys.stderr,
        )
    argv = vllm_argv(MODEL_ID, QUANT, GPU, VLLM_PORT)
    print(" ".join(argv), flush=True)
    subprocess.Popen(argv, env=env)
