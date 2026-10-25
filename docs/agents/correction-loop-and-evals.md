---
title: Correction loop and evals
tags: [eval, correction, learning, latte, sapling-replay]
files:
  - eval/correction_loop.py
  - eval/graduation_demo.py
  - gateway/graduation.py
  - eval/learning/harness.py
  - eval/learning/synthetic_cases.py
  - eval/gate.py
  - eval/latte/run.py
  - eval/replay.py
  - scripts/gen_synthetic_calls.py
---

## Purpose

Score stub labels, run a synthetic correction through a stub model version, and score whether corrections would change held-out calls. Nothing here promotes a rule into System 1.

## Key files

- `eval/__main__.py` — `make replay-stubs`. System 1, System 2, and Sapling stubs.
- `eval/replay.py` — scores a callable against fixture labels.
- `eval/correction_loop.py` — `make demo-correction-loop`. Case `CORR-LOOP-1`.
- `gateway/graduation.py` — the graduation rule: `graduated_patterns` counts human `s1_triage` corrections sharing one `(needs, vulnerable, danger)` pattern and a `graduation_labels` entry across `correction_loop.escalation_threshold` distinct cases; `apply(case)` tags matches `complex_situation` and adds a recommendation MemoryItem.
- `eval/graduation_demo.py` — `make demo-graduation`. Temp event log, two corrections, F02 graduates.
- `eval/compare.py` — route accuracy, latency, tokens. `cost_usd` stays null.
- `eval/learning/` — `make eval-learning`. Seeds 17, 29, 41. Report `eval/out/learning.md`.
- `eval/gate.py` — `make eval-gate`. Fails when the newest `s1_triage` fine-tune's held-out accuracy (registry via `api/routes/training.py`) is under 0.85 (`EVAL_GATE_MIN_ACCURACY`, `--min-accuracy`) or the current RL run's last-epoch `critical_under` exceeds the last `eval/snapshots/rl/` snapshot. A missing registry or run is a skip, not a failure; `EVAL_GATE_ARGS=--strict` forbids skips. No Mubit call.
- `eval/latte/` — `make latte-bench`. Pin in `eval/latte/pin.py`. Notes in `eval/LATTE.md`.
- `eval/sapling_replay.py` — `S01`–`S05`.

## Interfaces/contracts

- Correction loop: store a `Correction` via `memory/adapter.py`, write one SFT row to `eval/out/sft.jsonl`, register `stub-0` and `stub-1`. Job status `stub`. No weights. It also appends one `TrainingEvent` through `contracts.training.adapt_correction` and `training.log.append_event`. The event shape is `docs/agents/training-schema.md`.
- Learning arms: A base, B memory, C correction JSONL with empty memory, shuffled control. Held-out rows only. Thai and English of one call stay on the same side.
- Promotion recommendation does not promote. `promoted` stays false while `learning_eval.promotion` is `TODO_HUMAN`.
- Coach notes from `sim/coach.py` are `eval/out/coach.jsonl` with `source=coach`. They are not `Correction` rows and they are not promoted. See `docs/agents/caller-simulation.md`.
- Learning arms are also scored on held-out caller trait combinations (`eval/learning/simulators.py`).
- latte-bench is a submodule with no license. The runner does not vendor its source. Free mode makes no API call.
- Graduation hands System 2 a recommendation only: the case stays in System 2 tagged `complex_situation`, the rule sets no priority, and nothing moves into System 1. Routine labels (`sphere_*`, `niems_green_not_severe`, `niems_white_general`) never graduate. Non-human sources and same-case repeats do not count.
- `fixtures/synthetic/` is a seeded set of about 240 calls from `scripts/gen_synthetic_calls.py`. Language variants share `group_id`. `fixtures/synthetic/split.json` is the 70/30 group split. `fixtures/synthetic/demo.json` is eight calls for the town demo. `EVAL_LEARNING_SET=synthetic` scores that split. The default `make eval-learning` still scores the eight stub groups. `EXTRACT_EVAL_SET=fixtures` (the default) still scores the original 24 fixtures. `EXTRACT_EVAL_SET=synthetic` scores the new set. `all` scores both.

## Invariants

- `eval/out/` is gitignored. Do not commit reports or JSONL.
- Do not invent `llm.token_price_usd`. Cost stays null.
- Shuffled control is not a matched pattern. Its paired accuracy difference versus A is 0.
- Under-triage `None` (no critical held-out call) is not zero.
- `make latte-bench` skips when `bun` or the checkout is missing. It does not print `MUBIT_API_KEY`.

## How to test

- `make replay-stubs`
- `make demo-correction-loop`
- `make demo-graduation`
- `tests/test_graduation.py`
- `make eval-learning` — eight stub groups
- `EVAL_LEARNING_SET=synthetic make eval-learning` — `fixtures/synthetic` on the committed group split
- `make extract-eval` — original 24 fixtures
- `EXTRACT_EVAL_SET=synthetic make extract-eval` — synthetic calls, including Thai
- `python3 scripts/gen_synthetic_calls.py` — rewrite `fixtures/synthetic`
- `make sim-eval`
- `tests/test_learning_eval.py`, `tests/test_latte.py`
- `make latte-bench` only when bun and the submodule are present. Otherwise the skip path is the test.

## Common pitfalls

- Reading `eval/out/learning.md` as a measured learning result. The figures are the stub pattern rule.
- Copying `third_party/latte-bench` source into the repo. Import it from the checkout.
- Promoting a version from the closed-loop hook. The hook records `TODO_HUMAN` and does not promote.
- Calling Mubit from the learning harness. It does not.

## Open TODO_HUMAN keys

- `learning_eval.promotion`, `learning_eval.freeze_mubit_auto_adapters`
- `latte_bench.license_confirmation`
- `llm.token_price_usd`
- `modal.finetune_base_model` (the LoRA base the loop would train from)

Decided: `correction_loop.graduation_threshold` is `2` — used by the RL loop in `eval/rl/` (see `docs/agents/rl-loop.md`), not by this stub.
