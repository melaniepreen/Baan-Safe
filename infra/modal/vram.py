"""Weight and KV-cache arithmetic for the hardware note.

The figures are products of published parameter counts and the formulas
below. They are not measurements from a GPU run. Prices are not in this
file; infra/HARDWARE.md cites the Modal pricing page for those.
"""

from __future__ import annotations

GiB = 1024**3

# fp16 scale per group of 128 weights. AWQ payload is 0.5 bytes plus this.
AWQ_BYTES_PER_PARAM = 0.5 + (2 / 128)
BF16_BYTES = 2
FP8_BYTES = 1
# Standing in for the CUDA context and a batch-1 activation workspace.
# Not a measured vLLM footprint. enforce-eager keeps it smaller than CUDA graphs.
RESERVE_GIB = 2.0
DEMO_TOKENS = 4096

# safetensors parameter counts fetched from the Hugging Face model API
# on 24 October 2026, except where a comment says otherwise.
# attn_layers is the count that stores a KV cache. Hybrid models count
# attention layers only; Mamba state is small and is left out of kv_gib.
MODELS: list[dict] = [
    {
        "label": "Nano 4B",
        "repo": "nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1",
        "params": 4_512_746_496,
        "attn_layers": 32,
        "kv_heads": 8,
        "head_dim": 128,
        "size_tokens": ("4B",),
    },
    {
        "label": "Nano 8B",
        "repo": "nvidia/Llama-3.1-Nemotron-Nano-8B-v1",
        "params": 8_030_261_248,
        "attn_layers": 32,
        "kv_heads": 8,
        "head_dim": 128,
        "size_tokens": ("8B",),
    },
    {
        "label": "Nano 9B",
        "repo": "nvidia/NVIDIA-Nemotron-Nano-9B-v2",
        "params": 8_888_227_328,
        "attn_layers": 4,  # four '*' layers in hybrid_override_pattern
        "kv_heads": 8,
        "head_dim": 128,
        "size_tokens": ("9B",),
    },
    {
        "label": "Nano 30B-A3B",
        "repo": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16",
        "params": 31_577_934_400,  # card says 30B; this is the BF16 tensor count
        "attn_layers": 6,
        "kv_heads": 2,
        "head_dim": 128,
        "size_tokens": ("30B-A3B", "30B"),
    },
    {
        "label": "Super 49B",
        "repo": "nvidia/Llama-3_3-Nemotron-Super-49B-v1_5",
        "params": 49_867_145_216,
        "attn_layers": 49,  # 49 of 80 blocks have attention.no_op false
        "kv_heads": 8,  # 64 query heads / n_heads_in_group 8
        "head_dim": 128,  # hidden_size 8192 / 64
        "size_tokens": ("49B",),
    },
    {
        "label": "70B",
        "repo": "nvidia/Llama-3.1-Nemotron-70B-Instruct-HF",
        "params": 70_553_706_496,
        "attn_layers": 80,
        "kv_heads": 8,
        "head_dim": 128,
        "size_tokens": ("70B",),
    },
    {
        "label": "Super 120B-A12B",
        "repo": "nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-Base-BF16",
        "params": 123_611_012_096,
        "attn_layers": 8,
        "kv_heads": 2,
        "head_dim": 128,
        "size_tokens": ("120B-A12B", "120B"),
    },
]

# Memory in GiB, and the per-second USD rate published on
# https://modal.com/pricing on 24 October 2026. Hourly figures in the
# hardware note are these rates times 3600. "A100" without a size is the
# 40 GB part at the 40 GB rate. An automatic upgrade to 80 GB is not assumed.
GPUS: list[tuple[str, float]] = [
    ("T4", 16),
    ("L4", 24),
    ("A10", 24),
    ("L40S", 48),
    ("A100-40GB", 40),
    ("A100-80GB", 80),
    ("H100", 80),
    ("H200", 141),
]
RATE_PER_SEC = {
    "T4": 0.000164,
    "L4": 0.000222,
    "A10": 0.000306,
    "L40S": 0.000542,
    "A100": 0.000583,
    "A100-40GB": 0.000583,
    "A100-80GB": 0.000694,
    "H100": 0.001097,
    "H100!": 0.001097,
    "H200": 0.001261,
}


def weight_gib(params: int, quant: str) -> float:
    if quant == "bf16":
        nbytes = BF16_BYTES
    elif quant == "fp8":
        nbytes = FP8_BYTES
    elif quant == "awq":
        nbytes = AWQ_BYTES_PER_PARAM
    else:
        raise ValueError(f"unknown quant {quant}")
    return params * nbytes / GiB


def kv_gib(model: dict, tokens: int = DEMO_TOKENS, batch: int = 1) -> float:
    """bf16/fp16 KV cache. AWQ and FP8 weights do not shrink this cache."""
    per_token = 2 * model["attn_layers"] * model["kv_heads"] * model["head_dim"] * 2
    return per_token * tokens * batch / GiB


def footprint_gib(model: dict, quant: str, tokens: int = DEMO_TOKENS) -> float:
    return weight_gib(model["params"], quant) + kv_gib(model, tokens) + RESERVE_GIB


def match_model(model_id: str, size_label: str = "") -> dict | None:
    text = model_id or ""
    for row in MODELS:
        if row["repo"] == text or row["repo"] in text:
            return row
    haystack = f"{text} {size_label}"
    for row in MODELS:
        for token in row["size_tokens"]:
            if token in haystack:
                return row
    return None


def gpu_name_and_count(spec: str) -> tuple[str, int]:
    name, _, count = spec.partition(":")
    return name, int(count) if count else 1


def gpu_memory_gib(spec: str) -> float | None:
    name, count = gpu_name_and_count(spec)
    for gpu, memory in GPUS:
        if gpu == name:
            return memory * count
    if name == "A100":
        # Modal's "A100" request is the 40 GB part. Do not assume the 80 GB upgrade.
        return 40.0 * count
    return None


def fits(model: dict, quant: str, gpu_spec: str, tokens: int = DEMO_TOKENS) -> bool:
    memory = gpu_memory_gib(gpu_spec)
    if memory is None:
        return False
    name, count = gpu_name_and_count(gpu_spec)
    # Tensor parallel splits weights. KV and the reserve are counted per GPU.
    weights = weight_gib(model["params"], quant) / count
    return weights + kv_gib(model, tokens) + RESERVE_GIB <= memory / count


def _shapes() -> list[str]:
    shapes: list[str] = []
    for name, _memory in GPUS:
        # A10 has the same 24 GiB as L4 and a higher published rate.
        if name == "A10":
            continue
        shapes.append(name)
        for count in (2, 3, 4):
            shapes.append(f"{name}:{count}")
    return shapes


def shape_rate(spec: str) -> float:
    name, count = gpu_name_and_count(spec)
    return RATE_PER_SEC[name] * count


def slack_gib(model: dict, quant: str, gpu_spec: str, tokens: int = DEMO_TOKENS) -> float:
    memory = gpu_memory_gib(gpu_spec)
    if memory is None:
        return -1.0
    name, count = gpu_name_and_count(gpu_spec)
    per_gpu = weight_gib(model["params"], quant) / count + kv_gib(model, tokens) + RESERVE_GIB
    return (memory / count) - per_gpu


def cheapest_gpu(model: dict, quant: str, *, min_slack_gib: float = 0.0) -> str:
    """Lowest published per-second cost among shapes that fit, up to 4 GPUs."""
    best: tuple[float, str] | None = None
    for spec in _shapes():
        if not fits(model, quant, spec):
            continue
        # Native fp8 on Turing (T4, SM75) is refused by current vLLM. See HARDWARE.md.
        if quant == "fp8" and gpu_name_and_count(spec)[0] == "T4":
            continue
        if slack_gib(model, quant, spec) < min_slack_gib:
            continue
        rate = shape_rate(spec)
        if best is None or rate < best[0]:
            best = (rate, spec)
    if best is None:
        return "no shape up to 4 GPUs"
    return best[1]


def table_rows() -> list[dict]:
    rows = []
    for model in MODELS:
        for quant in ("bf16", "fp8", "awq"):
            gpu = cheapest_gpu(model, quant)
            comfortable = cheapest_gpu(model, quant, min_slack_gib=4.0)
            rows.append(
                {
                    "label": model["label"],
                    "quant": quant,
                    "weights": weight_gib(model["params"], quant),
                    "kv": kv_gib(model),
                    "total": footprint_gib(model, quant),
                    "gpu": gpu,
                    "comfortable": comfortable,
                    "fp8_on_t4": False,
                }
            )
    return rows


# Banyan Sapling. Stored-parameter count is the figure on the model card
# (MubitLabs/banyan-sapling, read 24 October 2026), not a safetensors recount.
# 48 layers, 4 KV heads, head dim 128 are from that repo's config.json.
# The reference runtime is one example at a time and generates no tokens.
# Quantized and CPU inference are outside that runtime, so this row is bf16 only.
SAPLING = {
    "label": "Banyan Sapling",
    "repo": "MubitLabs/banyan-sapling",
    "params": 23_042_164_740,
    "attn_layers": 48,
    "kv_heads": 4,
    "head_dim": 128,
    "input_tokens": 16384,
}
SAPLING_GPU_GIB = 48.0


def sapling_footprint(tokens: int | None = None) -> dict[str, float]:
    """BF16 weights + KV at the given token count + the 2 GiB reserve."""
    length = SAPLING["input_tokens"] if tokens is None else tokens
    weights = weight_gib(SAPLING["params"], "bf16")
    kv = kv_gib(SAPLING, length)
    return {
        "weights": weights,
        "kv": kv,
        "reserve": RESERVE_GIB,
        "total": weights + kv + RESERVE_GIB,
        "slack_on_48": SAPLING_GPU_GIB - (weights + kv + RESERVE_GIB),
    }


def main() -> None:
    print(f"reserve_gib={RESERVE_GIB} demo_tokens={DEMO_TOKENS} kv_dtype=fp16/bf16")
    print()
    print("| Model | Quant | Weights GiB | KV 4096 GiB | Weights+KV+reserve | Cheapest fit | Fit with 4 GiB slack |")
    print("|---|---|---:|---:|---:|---|---|")
    for row in table_rows():
        print(
            f"| {row['label']} | {row['quant']} | {row['weights']:.2f} | "
            f"{row['kv']:.2f} | {row['total']:.2f} | {row['gpu']} | {row['comfortable']} |"
        )
    sap = sapling_footprint()
    print()
    print("| Model | Quant | Weights GiB | KV 16384 GiB | Weights+KV+reserve | Slack on 48 GiB |")
    print("|---|---|---:|---:|---:|---:|")
    print(
        f"| Banyan Sapling | bf16 | {sap['weights']:.2f} | {sap['kv']:.2f} | "
        f"{sap['total']:.2f} | {sap['slack_on_48']:.2f} |"
    )


if __name__ == "__main__":
    main()
