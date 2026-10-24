---
title: Correction loop and evals
tags: [eval, correction, learning, latte, sapling-replay]
files:
  - eval/correction_loop.py
  - eval/learning/harness.py
  - eval/latte/run.py
  - eval/replay.py
---

## Purpose

Score stub labels, run a synthetic correction through a stub model version, and score whether corrections would change held-out calls. Nothing here promotes a rule into System 1.

## Key files

- `eval/__main__.py` — `make replay-stubs`. System 1, System 2, and Sapling stubs.
- `eval/replay.py` — scores a callable against fixture labels.
- `eval/correction_loop.py` — `make demo-correction-loop`. Case `CORR-LOOP-1`.
- `eval/compare.py` — route accuracy, latency, tokens. `cost_usd` stays null.
- `eval/learning/` — `make eval-learning`. Seeds 17, 29, 41. Report `eval/out/learning.md`.
- `eval/latte/` — `make latte-bench`. Pin in `eval/latte/pin.py`. Notes in `eval/LATTE.md`.
- `eval/sapling_replay.py` — `S01`–`S05`.

## Interfaces/contracts

- Correction loop: store a `Correction` via `memory/adapter.py`, write one SFT row to `eval/out/sft.jsonl`, register `stub-0` and `stub-1`. Job status `stub`. No weights.
- Learning arms: A base, B memory, C correction JSONL with empty memory, shuffled control. Held-out rows only. Thai and English of one call stay on the same side.
- Promotion recommendation does not promote. `promoted` stays false while `learning_eval.promotion` is `TODO_HUMAN`.
- Coach notes from `sim/coach.py` are `eval/out/coach.jsonl` with `source=coach`. They are not `Correction` rows and they are not promoted. See `docs/agents/caller-simulation.md`.
- Learning arms are also scored on held-out caller trait combinations (`eval/learning/simulators.py`).
- latte-bench is a submodule with no license. The runner does not vendor its source. Free mode makes no API call.

## Invariants

- `eval/out/` is gitignored. Do not commit reports or JSONL.
- Do not invent `llm.token_price_usd`. Cost stays null.
- Shuffled control is not a matched pattern. Its paired accuracy difference versus A is 0.
- Under-triage `None` (no critical held-out call) is not zero.
- `make latte-bench` skips when `bun` or the checkout is missing. It does not print `MUBIT_API_KEY`.

## How to test

- `make replay-stubs`
- `make demo-correction-loop`
- `make eval-learning`
- `make sim-eval`
- `tests/test_learning_eval.py`, `tests/test_latte.py`
- `make latte-bench` only when bun and the submodule are present. Otherwise the skip path is the test.

## Common pitfalls

- Reading `eval/out/learning.md` as a measured learning result. The figures are the stub pattern rule.
- Copying `third_party/latte-bench` source into the repo. Import it from the checkout.
- Promoting a version from the closed-loop hook. The hook records `TODO_HUMAN` and does not promote.
- Calling Mubit from the learning harness. It does not.

## Open TODO_HUMAN keys

- `correction_loop.graduation_threshold`
- `learning_eval.promotion`, `learning_eval.freeze_mubit_auto_adapters`
- `latte_bench.license_confirmation`
- `llm.token_price_usd`
- `modal.finetune_base_model` (the LoRA base the loop would train from)
