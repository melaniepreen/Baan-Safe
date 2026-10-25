# BaanSafe

Flood and disaster call-triage scaffold. Mubit is the LLM gateway: it records every System 2 call, groups them into a task, and trains per-task adapters; it does not reason and exposes no memory API (memory is BaanSafe's own store behind `memory/adapter.py`). The field precheck picks one entry point; `mode: cascade` lets a System 1 escalate continue to System 2 in the same turn. System 2's orchestrator is Nemotron, hosted as `openrouter via mubit gateway` (model `nvidia/nemotron-3-nano-30b-a3b`). Banyan Sapling verifies System 2 aid-eligibility and denial claims before the Decision Router. System 1 is rules-only. Fixture callers are synthetic. Owners: `OWNERSHIP.md`. Architecture note: `BaanSafe_Revised_Architecture.md`.

## Architecture

```
gateway/route.py     auth note, extract -> enrich -> memory -> policy pre-check
        | cascade (config/routing.yaml). gateway/chooser.py field precheck
        | overlay: gateway/overlay.py learned rules (RL_OVERLAY opt-in)
        +-- system1/extract.py + decide.py       rules-only keywords, needs table
        |        \-- s1 escalate --+             same turn, handoff to S2
        +-- system2/orchestrator.py              Nemotron via llm/client.py
                 \-- system2/sapling.py          aid_eligibility, denial only
router               router/merge.py -> next_action + provisional dispatches
                     source_outcomes = [deciding, *prior]
training             corrections, coach, sim -> event log -> export-training
                     -> per-task fine-tune -> eval/learning (group_id, source)
eval/rl              reward loop: graduate, recommend, demote, shadow bandit
```

## Invariants

1. Model calls go through Mubit. `llm/client.py` refuses a host that is not `api.mubit.ai` or a `mubit.ai` subdomain. There is no OpenRouter client. Do not read `OPENROUTER_API_KEY`.
2. Unset decisions stay the string `TODO_HUMAN`. Code raises `DecisionRequired` or `NotImplementedError` and names the key. The allowlist is `DECIDED` in `scripts/validate.py`.
3. Synthetic people only. `scripts/validate.py` rejects phones, 13-digit ids, PromptPay, passport, immigration status, and bank account.
4. Do not fetch ReliefWeb or add DDPM as a source. `ingest/reliefweb.py` sends no request.
5. Never commit or print secrets. `.env` is gitignored. A key in an error string is a bug.
6. Branch off `main`, open a pull request, and merge into `main` when green. Do not push feature work straight to `main`. Delete the remote branch after merge. Prefer one focused PR per change set; rebase onto `main` before merge if the tip moved.
7. `make test` and `make validate` stay green before merge.
8. Do not edit `frontend-prototype/` unless the task says so.
9. The no-stub fallback outcome (`missing_evidence == ["fixture_stub"]`) never cascades.

## Commands

```
make test
make validate
make replay-stubs
make demo-graduation
make rl-loop
make rl-loop-replay
make mubit-traffic
make eval-learning
make sim-eval
make extract-eval
make latte-bench
make serve
make sync
make push
make modal-secrets
make modal-deploy-s1
make modal-deploy-s2
make modal-deploy-sapling
make modal-deploy-stt
make export-training
make export-laya
make modal-finetune
```

The Makefile sets `PYTHONPATH=.`. `make latte-bench` prints `skipped` and exits 0 when `bun` or `third_party/latte-bench` is missing. `make serve` is the API on port 8000.

## Where to look

Index: `docs/agents/index.json`. Read one topic file, not the whole set.

| Task | Doc | Start here |
|---|---|---|
| Gateway, auth, memory, LLM host check | `docs/agents/gateway-and-llm-client.md` | `gateway/route.py`, `gateway/chooser.py`, `llm/client.py` |
| Fast path | `docs/agents/system1.md` | `system1/decide.py`, `system1/extract.py` |
| Nemotron, Sapling | `docs/agents/system2-and-sapling.md` | `system2/decide.py`, `system2/sapling.py` |
| Aid eligibility, policy corpus, escalation | `docs/agents/policies-api.md` | `policies/service.py`, `api/routes/policies.py` |
| Router | `docs/agents/decision-router.md` | `router/merge.py` |
| Corrections, learning eval, latte-bench | `docs/agents/correction-loop-and-evals.md` | `eval/correction_loop.py`, `eval/learning/` |
| RL loop, overlay, cascade | `docs/agents/rl-loop.md` | `eval/rl/`, `gateway/overlay.py` |
| Training log, export, per-task fine-tune | `docs/agents/training-schema.md` | `training/log.py`, `training/export.py`, `infra/modal/finetune_job.py` |
| Caller simulation, coach | `docs/agents/caller-simulation.md` | `sim/env.py`, `sim/coach.py` |
| Ingest, data files, banned sources | `docs/agents/data-ingest.md` | `ingest/__main__.py`, `data/SOURCES.md` |
| Live public sources, snapshots | `docs/agents/data-sources.md` | `ingest/demo_sources.py`, `data/snapshots/` |
| Modal, GPU, deploy | `docs/agents/modal-infra.md` | `infra/modal/`, `infra/HARDWARE.md` |
| YAML decisions | `docs/agents/config-and-decisions.md` | `config/decisions.yaml`, `config/settings.py` |
| Tests and validate | `docs/agents/testing.md` | `tests/`, `scripts/validate.py` |
| UI, correct this | `docs/agents/frontend.md` | `ui/player.html`, `ui/correct.js` |
| Country packs | `docs/agents/country-packs.md` | `countries/` |

## Done

- `make test` and `make validate` pass.
- No decision value outside `DECIDED`. No secrets in the diff.
- `frontend-prototype/` unchanged unless the task asked for it.
- The change is on a PR into `main` (or merged), not a lone push of feature work to `main`.
