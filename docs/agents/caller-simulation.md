---
title: Caller simulation
tags: [sim, caller, coach, mimesis, eval]
files:
  - sim/env.py
  - sim/coach.py
  - sim/callers/scripted.py
  - eval/learning/simulators.py
---

## Purpose

Train and score against scripted flood callers. The simulator and the coach sit outside the live gateway path. Ideas come from MIMESIS, "Learning User Simulators as Training Environments for Interactive Agents", arXiv:2610.09484, https://huggingface.co/papers/2610.09484. No paper source is copied.

## Key files

- `sim/callers/traits.py` — composable traits. The scripted caller is the default.
- `sim/callers/scripted.py` — public turn plus a private trace.
- `sim/callers/model.py` — model backend. Calls `llm/client.py` only after `sim.caller_model` and `sim.caller_gpu` are set.
- `sim/callers/catalog.py` — synthetic trait combinations.
- `sim/env.py` — caller, then `gateway.handle`, turn by turn. Logs the public transcript and the hidden truth.
- `sim/coach.py` — short notes to `eval/out/coach.jsonl`.
- `eval/learning/simulators.py` — held-out trait combinations on the learning scoreboard.
- `sim/__main__.py` — `make sim-eval`. Writes `eval/out/sim.md`.

## Interfaces/contracts

- Each caller has a hidden persona: true needs, true urgency, district, vulnerable household tags. People are synthetic.
- Each turn has a private trace. `CaseState.transcript` and `CaseState.fields` do not carry it.
- Traits: `panicked_fragmented`, `omits_location`, `contradicts`, `under_reports`, `over_reports`, `code_switches`, `proxy`, `poor_line`, `distrusts_authorities`, `needs_repeating`, `elderly_hearing`.
- `run_episode` calls `gateway.handle` once per turn. A synthetic id raises while `gateway.route_chooser` is unset. The env does not call both systems, Sapling, or `router.merge`.
- Coach rows: `source=coach`, `promoted` false. They are not `Correction` records and they are not auto-promoted.
- Learning arms A, B, C, and shuffled are scored on combinations the correction side did not include. Report per-trait under-triage for `under_reports` and `omits_location`, plus turns until the public call states location and urgency.

## Invariants

- Off the live path. `gateway/` does not import `sim`.
- The scripted backend does not call `llm.complete`.
- The model backend does not call a host other than through `llm/client.py`.
- `sim.caller_model` and `sim.caller_gpu` stay `TODO_HUMAN`. A MIMESIS-style 9B is one option. Weights and license are unconfirmed.
- Synthetic households only. No phone, national id, or account number.
- Token-level self-distillation from the paper is future work and is not implemented.
- `eval/out/` is gitignored.

## How to test

- `make sim-eval`
- `make eval-learning` (the report includes the trait section)
- `tests/test_sim.py`
- `make validate`

## Common pitfalls

- Reading `eval/out/sim.md` as a measured result. The operator lines are a fixed stub.
- Mixing coach JSONL into the human correction log or promoting it.
- Copying the hidden persona into `ExtractedFields` so the gateway can see it.
- Setting `sim.caller_model` to a guessed checkpoint id.
- Copying MIMESIS source or weights into the repo.
- Calling `system1.decide` and `system2.decide` from the environment. The gateway chooses one, and the chooser is unset.

## Open TODO_HUMAN keys

- `sim.caller_model`, `sim.caller_gpu`
- `gateway.route_chooser` (synthetic ids do not route until this is set)
- `llm.provider_route` (the model backend still has to pass the Mubit client)
