# BaanSafe

Flood and disaster call-triage scaffold. Mubit governs memory, policy, and traceability. System 1 acts fast. System 2 reasons deeply with Nemotron as its orchestrator. The decision router turns one system's outcome into the next action. Mubit does not reason.

This tree is Phase 0 plus a Phase 1 API. **System 1 and System 2 decision logic are not implemented.** Callers, households, and transcripts are synthetic. Real district names and public flood polygons are used only to anchor scenarios.

The architecture note is `BaanSafe_Revised_Architecture.md`. What to do in the morning is `MORNING_REPORT.md`. Who owns each folder is `OWNERSHIP.md`. Background reading for Phase 1 is `research/INDEX.md`.

## Setup

Python 3.11 or newer (this environment runs 3.12). From the repo root:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional `.env` values are listed in `.env.example`. None are required for the stub service. Do not commit keys.

## Commands

```bash
make validate       # fixtures, mocks, decisions, personal-data scan
make test           # pytest
make replay-stubs   # accuracy of s1/s2 stub files against expected labels
make demo-stub      # gateway.handle(..., use_stubs=True) for every fixture
make demo-correction-loop  # stub: correction -> JSONL -> model version -> before/after
make serve          # API on :8000, docs at /docs
make ingest         # public sources, using the cache
make ingest-refresh # ignore the cache
make data-report    # rewrite data/SOURCES.md
```

`make` uses `python3` unless you pass `PYTHON=.venv/bin/python`.

## API switches

| Variable | Default tonight | Owner flips to |
|---|---|---|
| `S1_IMPL` | `stub` | `real` when `system1/decide.py` exists |
| `S2_IMPL` | `stub` | `real` when `system2/decide.py` exists |
| `MEMORY_IMPL` | `mock` | `mubit` when `memory/mubit.py` exists |
| `ENRICH_IMPL` | `data` if `data/processed` exists, else `off` | `off` to skip lookups |

`real` and `mubit` return HTTP 501 (`not implemented yet — owner: …`) until that code exists.

Stub gateway flow for `/triage` and `/cases/{id}/turns`: enrich → memory through `memory/adapter.py` → route to System 1 **or** System 2 (fixture `expected.system` until `gateway.route_chooser` is set; never both) → copy that one stub into a `RouterDecision` → trace the gateway and the system that ran, with the outcome on the system event. `router/merge.py` is not called. A case id that is not a fixture returns HTTP 501 until a human sets `gateway.route_chooser`.

`GET /aid/eligibility` and `POST /aid/exceptions` return HTTP 501. They do not approve a payment.

LLM calls, when a human writes them, go through `llm/client.py`. That client requires `MUBIT_BASE_URL` on a `mubit.ai` host and `MUBIT_API_KEY`, and it still refuses while `llm.provider_route` is `TODO_HUMAN`. It does not print the key.

`make demo-correction-loop` runs a synthetic correction through memory, writes an SFT/LoRA JSONL file under `eval/out/` (gitignored), registers stub model versions `stub-0` and `stub-1`, and prints quality, latency, and a null cost. It does not train weights and it does not promote a rule into System 1.

## Data

Public sources and row counts are in `data/SOURCES.md`. Raw responses are gitignored under `data/raw/`. SQLite is the overnight store. The production database is `TODO_HUMAN` in `config/decisions.yaml`.

## Contracts

`contracts/models.py` is the shared shape. JSON Schema for a UI is in `contracts/schemas/`. Do not edit a contract to suit one system. Propose a change in `contracts/CHANGE_REQUESTS.md`.
