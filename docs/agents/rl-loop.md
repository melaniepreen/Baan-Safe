---
title: RL loop
tags: [rl, overlay, cascade, graduation, demotion, bandit]
files:
  - eval/rl/run.py
  - eval/rl/learner.py
  - eval/rl/reward.py
  - eval/rl/themes.py
  - gateway/overlay.py
  - config/routing.yaml
---

## Purpose

Score System 1 / System 2 outcomes in a reward loop. A System 1 escalate cascades to System 2 in the same turn. Consistent correct System 2 decisions graduate to a System 1 rule; P1 and complex patterns become a recommendation instead. System 1 under-triage demotes a pattern to System 2. A shadow bandit learns routing but never routes. Every scored episode appends a sim `TrainingEvent`.

## Key files

- `eval/rl/run.py` — `python -m eval.rl --s2 live|replay|fake`. Writes `eval/out/rl/run.json`, `rl.md`, `overlay.json`, `s2_cache.jsonl`.
- `eval/rl/themes.py` — eight authored themes with variants and settled truth.
- `eval/rl/reward.py` — priority distance, route, human, cost, and correctness scoring.
- `eval/rl/learner.py` — graduation streaks, demotion, Beta(1,1) shadow bandit.
- `gateway/overlay.py` — coarse/narrow signatures, `Overlay`, `RL_OVERLAY` opt-in. Live-path code.
- `gateway/route.py` — `handle(case, use_stubs, overlay)`; cascade and the fallback guard.
- `api/routes/endpoints.py` — `GET /rl/run` serves `run.json`, else 404 saying to run `make rl-loop`.

## Interfaces/contracts

- `Overlay` schema `baansafe.rl_overlay.v1`: `graduation_threshold`, `graduated`, `recommendations`, `demoted`. Narrow signatures promote; coarse signatures demote. A narrow signature is the coarse signature plus `|text=` + a 12-char hash of caller content tokens (stopwords, number words, and location tokens excluded).
- `run.json` schema `baansafe.rl_run.v1`: per-epoch summaries, per-episode rows, events, the final overlay, training counts, notes.
- Cascade: `source_outcomes = [deciding outcome, *prior]`, so `[0]` is always the deciding system.
- S2 modes: `live` calls Mubit through `llm.complete` with a 2/4/8 s 429 backoff and caches replies; `replay` reads the cache only and a miss counts as a fallback; `fake` replays authored truth and is for tests.
- Learner events: `graduate`, `recommend`, `demote`, recorded once per signature.

## Invariants

- The no-stub fallback (`missing_evidence == ["fixture_stub"]`) never cascades.
- P1 and complex outcomes (requires_human, supervisor or aid route, aid need, or a safeguarding/aid flag) never graduate — they become recommendations passed back to System 2.
- Direct System 2 routes (hard trigger or demotion) never graduate.
- The bandit never routes; it only records pick vs actual.
- `eval/out/` is gitignored. No test or run hits the network without `--s2 live`.

## How to test

- `python -m eval.rl --s2 fake --epochs 3` — road-info and cold-hall graduate, quiet-grandmother and upstairs-water recommend, weak-grandfather-water demotes, aid never graduates.
- `make rl-loop` (live) and `make rl-loop-replay` (cache only).
- `tests/test_rl_loop.py`, `tests/test_cascade.py`, `tests/test_overlay.py`, `tests/test_orchestrator.py`.
- `GET /rl/run` on `make serve`.

## Common pitfalls

- Reading `source_outcomes` in the wrong order. The deciding outcome is `[0]`; priors follow.
- Treating a demoted route as a cascade. A demoted coarse signature enters at System 2 directly.
- Expecting unmatched-needs escalations to graduate. Graduated rules apply only where System 1 escalates for no needs or low confidence.
- Assuming the fake completer is a model. It replays authored truth; it measures loop plumbing, not reasoning.
- Setting `RL_OVERLAY` globally in tests. It is process state cached by mtime; unset it or pass `overlay=` explicitly.

## Open TODO_HUMAN keys

- `modal.finetune_base_model` — the export runs but fine-tune stays blocked.
- `system1.extraction_model`, `sim.caller_model`, `sim.caller_gpu`.
