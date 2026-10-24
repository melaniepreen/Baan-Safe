"""argv for `vllm serve`. No Modal import, so the GPU image can run it too.

The API key is not placed on the command line. vLLM reads VLLM_API_KEY from
the environment when a human has set S2_SERVE_API_KEY in the Modal secret.
"""

from __future__ import annotations

import os
import sys

from infra.modal.common import redact
from infra.modal.vram import (
    fits,
    gpu_name_and_count,
    match_model,
    slack_gib,
)

VLLM_PORT = 8000


class FitRefusal(SystemExit):
    """The requested GPU cannot hold this checkpoint under the published formula."""


def check_fit(model_id: str, size_label: str, quant: str, gpu_spec: str) -> None:
    name, _count = gpu_name_and_count(gpu_spec)
    if quant == "fp8" and name == "T4":
        raise FitRefusal(
            "Refusing fp8 on a T4. vLLM's native fp8e4nv path needs compute "
            "capability 8.9 or newer (L4, L40S, H100). See infra/HARDWARE.md."
        )
    model = match_model(model_id, size_label)
    if model is None:
        print(
            f"No VRAM row for model {model_id!r} size {size_label!r}. "
            "Not refusing. infra/HARDWARE.md lists the checkpoints that were measured.",
            file=sys.stderr,
        )
        return
    if not fits(model, quant, gpu_spec):
        raise FitRefusal(
            f"Refusing {model['label']} {quant} on {gpu_spec}. "
            "Weights plus a 4096-token KV cache plus a 2 GiB reserve exceed "
            "that GPU. See infra/HARDWARE.md."
        )
    slack = slack_gib(model, quant, gpu_spec)
    if slack < 4:
        print(
            f"Tight fit: {slack:.1f} GiB of slack for {model['label']} {quant} on {gpu_spec}.",
            file=sys.stderr,
        )


def vllm_argv(model_id: str, quant: str, gpu_spec: str, port: int = VLLM_PORT) -> list[str]:
    _name, count = gpu_name_and_count(gpu_spec)
    if quant == "bf16":
        dtype_flags = ["--dtype", "float16" if _name == "T4" else "bfloat16"]
    elif quant == "fp8":
        dtype_flags = ["--quantization", "fp8", "--dtype", "auto"]
    elif quant == "awq":
        dtype_flags = ["--quantization", "awq", "--dtype", "float16"]
    else:
        raise FitRefusal(f"Quant {quant!r} is not bf16, fp8, or awq.")
    argv = [
        "vllm",
        "serve",
        model_id,
        "--host",
        "0.0.0.0",
        "--port",
        str(port),
        "--served-model-name",
        model_id,
        "--tensor-parallel-size",
        str(count),
        "--max-model-len",
        os.environ.get("S2_MAX_MODEL_LEN", "4096"),
        *dtype_flags,
    ]
    # CUDA graphs add minutes to a cold start. Default is the fast boot.
    if os.environ.get("S2_FAST_BOOT", "1") != "0":
        argv.append("--enforce-eager")
    return argv


def main() -> None:
    from infra.modal.common import parse_gpu, parse_quant, resolve

    model_id = resolve("modal.s2_model_id", "S2_MODEL_ID")
    size_label = resolve("modal.nemotron_size", "NEMOTRON_SIZE")
    quant = parse_quant(resolve("modal.s2_quant", "S2_QUANT"))
    gpu_spec = parse_gpu(resolve("modal.s2_gpu", "S2_GPU"), allow_cpu=False)
    assert gpu_spec is not None
    check_fit(model_id, size_label, quant, gpu_spec)
    argv = vllm_argv(model_id, quant, gpu_spec)
    print(" ".join(argv), flush=True)
    if not os.environ.get("S2_SERVE_API_KEY", "").strip():
        print(
            "S2_SERVE_API_KEY is unset. vLLM will not require a bearer token.",
            file=sys.stderr,
        )
    else:
        os.environ["VLLM_API_KEY"] = os.environ["S2_SERVE_API_KEY"]
    try:
        os.execvp(argv[0], argv)
    except OSError as exc:
        raise SystemExit(redact(str(exc))) from None


if __name__ == "__main__":
    main()
