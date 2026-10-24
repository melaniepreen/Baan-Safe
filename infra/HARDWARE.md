# Hardware

Checked 24 October 2026. Prices are the per-second rates on the Modal pricing page, not a separate hourly sticker. The hourly column is that rate times 3600. GPU names are the strings in the Modal GPU guide. Nothing here is a chosen `system2.orchestrator_model`. Those decisions stay `TODO_HUMAN`.

## Demo setup

The cheapest setup that can still show a live model is:

| Workload | Shape | Why |
|---|---|---|
| System 1 classifier | CPU | mDeBERTa is 0.52 GiB of fp16 weights. Laya-multilingual, at the 322M parameters on its card, is 0.60 GiB. Both sit in RAM. |
| System 2, if a live Nemotron is required | one T4, Nano 4B, bf16 | T4 is the lowest GPU rate on the pricing page. The 4B bf16 footprint below is 10.91 GiB, inside 16 GiB. |
| Correction-loop LoRA | same T4 and the same 4B base | The job loads the base in 16-bit and trains a small adapter for a few dozen steps. |
| Speech-to-text | leave it scripted, or one T4 / CPU | A Whisper-large checkpoint is a few GiB. It is optional for the three demo beats. |

An A100 is not in that setup.

Use an 80 GB A100 when the human picks one of these, because it is the cheapest comfortable fit:

- 70B in fp8 (68.96 GiB with the reserve below). One A100-80GB.
- 30B-A3B in bf16 on a single GPU (60.84 GiB). Three L4s are a few cents cheaper per second and have under 4 GiB of slack.
- 120B-A12B in AWQ on a single GPU (61.39 GiB). Three L4s are again slightly cheaper and tight.

49B bf16 (95.65 GiB) and 70B bf16 (134.67 GiB) fit one H200 (141 GiB). 120B bf16 (232.27 GiB) fits two H200s with slack, or three 80 GB A100s with about 1 GiB of slack. The 40 GB A100 is never the cheapest row: an L40S has 48 GB and a lower per-second rate.

The 4B, 8B, 9B, 49B, and 70B cards checked on 24 October 2026 list English. The 30B-A3B card's language tags are English, Spanish, French, German, Japanese, and Italian. The 120B-A12B base card's language list includes Thai. That is the same trade-off as `research/MODELS.md`: the checkpoint whose card lists Thai is the one that needs an 80 GB-class GPU even at AWQ.

## Prices

Source: [Modal pricing](https://modal.com/pricing), resource-cost table, read 24 October 2026. The page lists USD per second. Hourly figures are `rate × 3600`.

| Modal GPU string | Memory | USD / second | USD / hour (`× 3600`) |
|---|---:|---:|---:|
| T4 | 16 GB | 0.000164 | 0.5904 |
| L4 | 24 GB | 0.000222 | 0.7992 |
| A10 | 24 GB | 0.000306 | 1.1016 |
| L40S | 48 GB | 0.000542 | 1.9512 |
| A100-40GB | 40 GB | 0.000583 | 2.0988 |
| A100-80GB | 80 GB | 0.000694 | 2.4984 |
| H100 | 80 GB | 0.001097 | 3.9492 |
| H200 | 141 GB | 0.001261 | 4.5396 |

The pricing table says "Nvidia A10", "Nvidia A100, 40 GB", "Nvidia A100, 80 GB", and "Nvidia H100 SXM5". The GPU guide's request strings are `A10`, `A100`, `A100-40GB`, `A100-80GB`, and `H100`. `A100` with no size is the 40 GB part, and Modal may move it onto an 80 GB board at the 40 GB price. The fit check does not count on that upgrade. One FAQ example on the same page still says "A10G"; that is the same 24 GB board as `A10`.

CPU is 0.0000131 USD per physical core per second, which is 0.04716 USD per core-hour. Memory is 0.00000222 USD per GiB per second, which is 0.007992 USD per GiB-hour. A container asks for at least 0.125 cores and 128 MiB. The Starter plan is $0 plus compute and includes $30 of compute per month. A GPU still needs a payment method on the account ([GPU guide](https://modal.com/docs/guide/gpu)).

A region selection multiplies the base rate by 1.15 to 1.75. The apps do not set a region. Non-preemptible CPU and memory are 3× the list price. The apps leave the default, which is preemptible.

These rates are for time the container is up. The pricing FAQ says Modal bills application load, input processing, and a default 60 seconds after the last input. The apps set `scaledown_window` to 120 seconds, so a quiet endpoint keeps billing for two minutes and then stops.

## Formula

Weight GiB = `parameter_count × bytes_per_parameter / 1024³`.

| Quant | Bytes per parameter |
|---|---:|
| bf16 | 2 |
| fp8 | 1 |
| AWQ, group size 128, plus fp16 scales | 0.5 + 2/128 = 0.515625 |

KV GiB at 4096 tokens and batch 1 = `2 × attention_layers × kv_heads × head_dim × 2 bytes × 4096 / 1024³`.

The KV term stays at 2 bytes for every quant. An fp8 KV cache would be smaller on L4, L40S, and H100, and current vLLM rejects it on a T4 (compute capability 7.5). The table does not take that saving.

A flat 2 GiB is added for the CUDA context and a batch-1 workspace. That number is an allowance, not a measurement. vLLM with CUDA graphs can use more. The System 2 app passes `--enforce-eager` unless `S2_FAST_BOOT=0`, which skips those graphs.

Footprint = weights + KV + 2 GiB. A multi-GPU row splits the weights evenly and still charges the full KV and the 2 GiB on every GPU. Hybrid Mamba checkpoints may not split that cleanly. Where the table shows `L4:3`, the single-GPU column next to it is the safer demo shape.

Active parameters on the MoE cards do not shrink the weight term. The 30B-A3B card says 3.5B active and "30B" total. Its safetensors file is 31,577,934,400 bf16 parameters. The 120B-A12B card is the one `research/MODELS.md` describes as about 12B active. Its safetensors file is 123,611,012,096 bf16 parameters. Memory follows the safetensors count.

Mamba recurrent state is omitted. It is small next to the weights.

`infra/modal/vram.py` is this arithmetic. `python infra/modal/vram.py` reprints the table.

## Nemotron footprints

Parameter counts are the bf16 tensor counts from the Hugging Face model API on 24 October 2026. Attention shape is from each repo's `config.json` on the same day.

| Checkpoint | Params (bf16 tensors) | Attention layers | KV heads | Head dim |
|---|---:|---:|---:|---:|
| [Llama-3.1-Nemotron-Nano-4B-v1.1](https://huggingface.co/nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1) | 4,512,746,496 | 32 | 8 | 128 |
| [Llama-3.1-Nemotron-Nano-8B-v1](https://huggingface.co/nvidia/Llama-3.1-Nemotron-Nano-8B-v1) | 8,030,261,248 | 32 | 8 | 128 |
| [NVIDIA-Nemotron-Nano-9B-v2](https://huggingface.co/nvidia/NVIDIA-Nemotron-Nano-9B-v2) | 8,888,227,328 | 4 | 8 | 128 |
| [NVIDIA-Nemotron-3-Nano-30B-A3B-BF16](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16) | 31,577,934,400 | 6 | 2 | 128 |
| [Llama-3_3-Nemotron-Super-49B-v1_5](https://huggingface.co/nvidia/Llama-3_3-Nemotron-Super-49B-v1_5) | 49,867,145,216 | 49 of 80 blocks | 8 | 128 |
| [Llama-3.1-Nemotron-70B-Instruct-HF](https://huggingface.co/nvidia/Llama-3.1-Nemotron-70B-Instruct-HF) | 70,553,706,496 | 80 | 8 | 128 |
| [NVIDIA-Nemotron-3-Super-120B-A12B-Base-BF16](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-Base-BF16) | 123,611,012,096 | 8 | 2 | 128 |

The 9B pattern has four `*` attention layers. The 30B pattern has six. The 120B pattern has eight. The 49B config has 80 blocks and 49 of them keep attention; query heads are 64 and `n_heads_in_group` is 8, so there are 8 KV heads, and head dim is 8192/64.

There is also [NVIDIA-Nemotron-Nano-4B-v2.1](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16), whose card says 3.97×10⁹ parameters and lists English. It is smaller than the 4.51B row, so the same T4 conclusion holds. It is not a separate row because this note uses the safetensors count above.

| Model | Quant | Weights GiB | KV at 4096 GiB | Weights + KV + 2 GiB | Cheapest fit | Fit with at least 4 GiB slack |
|---|---|---:|---:|---:|---|---|
| Nano 4B | bf16 | 8.41 | 0.50 | 10.91 | T4 | T4 |
| Nano 4B | fp8 | 4.20 | 0.50 | 6.70 | L4 | L4 |
| Nano 4B | awq | 2.17 | 0.50 | 4.67 | T4 | T4 |
| Nano 8B | bf16 | 14.96 | 0.50 | 17.46 | L4 | L4 |
| Nano 8B | fp8 | 7.48 | 0.50 | 9.98 | L4 | L4 |
| Nano 8B | awq | 3.86 | 0.50 | 6.36 | T4 | T4 |
| Nano 9B | bf16 | 16.56 | 0.06 | 18.62 | L4 | L4 |
| Nano 9B | fp8 | 8.28 | 0.06 | 10.34 | L4 | L4 |
| Nano 9B | awq | 4.27 | 0.06 | 6.33 | T4 | T4 |
| Nano 30B-A3B | bf16 | 58.82 | 0.02 | 60.84 | L4:3 | A100-80GB |
| Nano 30B-A3B | fp8 | 29.41 | 0.02 | 31.43 | L4:2 | L4:2 |
| Nano 30B-A3B | awq | 15.16 | 0.02 | 17.19 | L4 | L4 |
| Super 49B | bf16 | 92.88 | 0.77 | 95.65 | H200 | H200 |
| Super 49B | fp8 | 46.44 | 0.77 | 49.21 | L4:3 | L4:3 |
| Super 49B | awq | 23.95 | 0.77 | 26.71 | T4:2 | L4:2 |
| 70B | bf16 | 131.42 | 1.25 | 134.67 | H200 | H200 |
| 70B | fp8 | 65.71 | 1.25 | 68.96 | A100-80GB | A100-80GB |
| 70B | awq | 33.88 | 1.25 | 37.13 | L4:2 | L40S |
| Super 120B-A12B | bf16 | 230.24 | 0.03 | 232.27 | A100-80GB:3 | H200:2 |
| Super 120B-A12B | fp8 | 115.12 | 0.03 | 117.15 | H200 | H200 |
| Super 120B-A12B | awq | 59.36 | 0.03 | 61.39 | L4:3 | A100-80GB |

fp8 rows start at L4. vLLM still runs on a T4 (compute capability 7.5 or higher, [vLLM GPU install](https://docs.vllm.ai/en/stable/getting_started/installation/gpu/)), and its Triton attention path rejects fp8 and bf16 KV on SM 7.5 ([vLLM PR 43914](https://github.com/vllm-project/vllm/pull/43914)). The server passes `--dtype float16` for a T4 bf16 or AWQ checkpoint. The weight size stays 2 bytes per parameter because the published checkpoint is bf16.

AWQ means an AWQ checkpoint id. The app passes `--quantization awq`. It does not quantise a bf16 repo on the fly.

A single A100-80GB also holds 49B fp8 (49.21 GiB). Three L4s are slightly cheaper per second (3 × 0.000222 = 0.000666, against 0.000694). One GPU is the simpler demo.

## Other workloads

**System 1.** [MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7](https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7) has 278,811,651 fp16 parameters on the Hub API (24 October 2026), which is 0.52 GiB. The card's language list does not include `th`. XNLI itself has a Thai split, so a human should measure it before relying on it. [convaiinnovations/laya-multilingual](https://huggingface.co/convaiinnovations/laya-multilingual) is the 322M mmBERT checkpoint in the 24 October Laya note, 0.60 GiB at 2 bytes per parameter, and that note says the card includes Thai. Either one is a CPU endpoint. A T4 is there if the human wants the ~30 ms figure from that note. `modal.s1_gpu` accepts `cpu`, `T4`, or `L4`.

**Fine-tune.** The job consumes the messages JSONL from `make demo-correction-loop` and writes LoRA weights under `/vol/versions/<version id>/` on the `baansafe-versions` volume, then returns the version id. A 4B bf16 base fits a T4. An 8B or 9B bf16 base needs an L4. A 70B LoRA loads the 70B base, so it needs the same board as 70B inference plus room for activations. The app refuses a pair that fails the table. Full fine-tuning of the 322M Laya encoder is a different recipe (the upstream RLCD notebook). This job does not run that recipe. A dry run records the version id and does not train.

**Speech.** Optional. `research/MODELS.md` names Thonburian Whisper and Typhoon2-Audio. OpenAI's model table lists Whisper large at 1550M parameters ([whisper README](https://github.com/openai/whisper#available-models-and-languages)), which is 2.89 GiB at 2 bytes per parameter. That fits a T4 and a CPU. Confirm the checkpoint you put in `STT_MODEL_ID`. The endpoint's default language is `th` and the request can override it.

## Cold start

The pricing FAQ says Modal spins a container up in 1–2 seconds, and that this is the container rather than a model load. The first deploy also builds the image. A later start reuses it.

Weight download is the Hub `usedStorage` of the checkpoint (about 2 bytes per bf16 parameter for the rows above; the 4B repo's stored size is larger than its tensor count, so check the files page before assuming an 8 GiB download). The apps download into the `baansafe-hf-cache` volume and commit it, so the next container skips the transfer.

vLLM then loads the weights and, unless `--enforce-eager` is set, captures CUDA graphs. This repo defaults to eager. No load time was measured here. The GPU guide says asking for more than two GPUs on one container usually waits longer for a machine.

The web endpoints wait up to 20 minutes (System 1 and speech) or 30 minutes (System 2) for the port to open, which covers a cold weight load. After the last request they stay up for 120 seconds and then scale to zero.

## What the apps refuse

`infra/modal/s2_app.py` and the fine-tune app call the same fit check at import. A 70B bf16 checkpoint on a T4 exits before any download. fp8 on a T4 exits for the same reason. An unknown checkpoint id prints a warning and continues, because this table does not cover every Nemotron repo.

Deploy still needs a human to export `S2_GPU`, `S2_MODEL_ID`, `NEMOTRON_SIZE`, and `S2_QUANT` (and the matching variables for the other apps). The yaml values stay `TODO_HUMAN` so `make validate` keeps passing.
