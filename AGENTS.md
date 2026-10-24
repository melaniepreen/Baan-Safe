# BaanSafe

Flood and disaster call-triage scaffold. Mubit governs memory, policy, and traceability and does not reason. One turn goes to System 1 or System 2, never both. System 2's orchestrator is Nemotron, hosted as `openrouter via mubit gateway`. Banyan Sapling verifies System 2 aid-eligibility and denial claims before the Decision Router. `system1/` and `system2/` decision logic is not implemented. Fixture callers are synthetic. Owners: `OWNERSHIP.md`. Architecture note: `BaanSafe_Revised_Architecture.md`.

## Architecture

```
gateway/route.py     auth note, memory/adapter.py, policy pre-check
        | exclusive (config/routing.yaml). Fixture ids use expected.system.
        +-- system1/decide.py                    raises NotImplementedError
        +-- system2/orchestrator.py              raises while model id or latency is unset
                 \-- system2/sapling.py          aid_eligibility, denial only
router               stub copies that one Outcome. router/merge.py is not called.
training             corrections, coach, sim -> event log -> export-training
                     -> per-task fine-tune -> eval/learning (group_id, source)
```

## Invariants

1. Model calls go through Mubit. `llm/client.py` refuses a host that is not `api.mubit.ai` or a `mubit.ai` subdomain. There is no OpenRouter client. Do not read `OPENROUTER_API_KEY`.
2. Unset decisions stay the string `TODO_HUMAN`. Code raises `DecisionRequired` or `NotImplementedError` and names the key. The allowlist is `DECIDED` in `scripts/validate.py`.
3. Synthetic people only. `scripts/validate.py` rejects phones, 13-digit ids, PromptPay, passport, immigration status, and bank account.
4. Do not fetch ReliefWeb or add DDPM as a source. `ingest/reliefweb.py` sends no request.
5. Never commit or print secrets. `.env` is gitignored. A key in an error string is a bug.
6. Push straight to `main`. Do not open a pull request.
7. `make test` and `make validate` stay green.
8. Do not edit `frontend-prototype/` unless the task says so.

## Commands

```
make test
make validate
make replay-stubs
make eval-learning
make sim-eval
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
make modal-finetune
```

The Makefile sets `PYTHONPATH=.`. `make latte-bench` prints `skipped` and exits 0 when `bun` or `third_party/latte-bench` is missing. `make serve` is the API on port 8000.

## Where to look

Index: `docs/agents/index.json`. Read one topic file, not the whole set.

| Task | Doc | Start here |
|---|---|---|
| Gateway, auth, memory, LLM host check | `docs/agents/gateway-and-llm-client.md` | `gateway/route.py`, `llm/client.py` |
| Fast path | `docs/agents/system1.md` | `system1/decide.py` |
| Nemotron, Sapling | `docs/agents/system2-and-sapling.md` | `system2/decide.py`, `system2/sapling.py` |
| Aid eligibility, policy corpus, escalation | `docs/agents/policies-api.md` | `policies/service.py`, `api/routes/policies.py` |
| Router | `docs/agents/decision-router.md` | `router/merge.py` |
| Corrections, learning eval, latte-bench | `docs/agents/correction-loop-and-evals.md` | `eval/correction_loop.py`, `eval/learning/` |
| Training log, export, per-task fine-tune | `docs/agents/training-schema.md` | `training/log.py`, `training/export.py`, `infra/modal/finetune_job.py` |
| Caller simulation, coach | `docs/agents/caller-simulation.md` | `sim/env.py`, `sim/coach.py` |
| Ingest, SQLite, banned sources | `docs/agents/data-ingest.md` | `ingest/__main__.py`, `data/SOURCES.md` |
| Modal, GPU, deploy | `docs/agents/modal-infra.md` | `infra/modal/`, `infra/HARDWARE.md` |
| YAML decisions | `docs/agents/config-and-decisions.md` | `config/decisions.yaml`, `config/settings.py` |
| Tests and validate | `docs/agents/testing.md` | `tests/`, `scripts/validate.py` |
| UI, correct this | `docs/agents/frontend.md` | `ui/player.html`, `ui/correct.js` |

## Done

- `make test` and `make validate` pass.
- No decision value outside `DECIDED`. No secrets in the diff.
- `frontend-prototype/` unchanged unless the task asked for it.
- The commit is on `main` and has been pushed.
