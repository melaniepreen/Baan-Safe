# Ownership

Person A is Moly. Person B is Melanie. Phase 0 scaffolding is shared. The decision logic behind each folder is still for the named owner. Nothing in `system1/` or `system2/` decides a case.

Mubit governs memory, policy, and traceability. System 1 acts fast. System 2 reasons deeply with Nemotron as its orchestrator. Banyan Sapling verifies aid-eligibility and denial claims on that path before the Decision Router. The Decision Router turns their outcomes into one safe next action. Mubit does not reason, and Nemotron is not inside Mubit. Sapling is not the orchestrator.

| Area | A — Moly | B — Melanie |
|---|---|---|
| Call agent | Live call UX, transcript, operator controls, dispatch view (`ui/`) | Aid caseworker view and policy dashboard. Stubs: `GET /aid/eligibility`, `POST /aid/exceptions` |
| Mubit gateway | API gateway, exclusive routing to System 1 or System 2, trace logging (`gateway/`) | Memory schemas, retrieval behaviour, correction memory (`memory/`) |
| System 1 | Fast triage rules and deterministic routing (`system1/decide.py`) | Aid eligibility fast checks (`system1/aid_eligibility.py`) |
| System 2 | Complex triage and medical reasoning, when that work starts | Exception reasoning, the Sapling gate, correction proposals, replay (`system2/`, `eval/`) |
| Nemotron | System 2 orchestration for response cases, once a model is chosen | System 2 orchestration for aid and correction cases (`system2/orchestrator.py`). Every LLM call goes through `llm/client.py` |
| Evaluation | Triage and dispatch replay | Aid, exclusion, and correction replay (`eval/replay.py`, `eval/correction_loop.py`) |

| Folder | Who | Tonight |
|---|---|---|
| `gateway/` | Moly | `handle(..., use_stubs=True)` keyword-extracts, routes via the `gateway/chooser.py` field precheck, and calls `router.merge` |
| `router/` | Moly | `merge(case, outcome)` picks the next action and fans out provisional dispatches |
| `ui/` | Moly | Transcript player, and `ui/sim/` the fixed-camera town. Framework is still `TODO_HUMAN`. Melanie's caseworker view is not built |
| `system1/` | Moly for `decide()` and `extract.py`, Melanie for `aid_eligibility.py` | `decide()` is real rules; `aid_eligibility.py` raises |
| `system2/` | Melanie | `decide()` raises while the orchestrator is unset. After reasoning, Sapling runs for aid eligibility and denials. The committed client is the stub |
| `llm/` | Shared rule, Melanie wires the call | Refuses unless `MUBIT_BASE_URL` is a Mubit host. Does not print the key |
| `memory/` | Melanie | Adapter switches `MEMORY_IMPL=mock` and `MEMORY_IMPL=mubit`. The mubit client raises |
| `eval/` | Melanie | Scores stubs. `make demo-correction-loop` runs the stub model-update loop |
| `contracts/` | Shared | v0.2 plus CR-003 (`Dispatch`, `RouterDecision.dispatches`; tag pending). Further changes go through `contracts/CHANGE_REQUESTS.md` |
| `config/` | Shared | Humans sign off. Big decisions stay `TODO_HUMAN`. `config/routing.yaml` is `exclusive` and is a harness setting |
| `fixtures/`, `mocks/` | Shared | Synthetic callers only |
| `ingest/`, `enrich/`, `data/` | Shared | Public data. Production database is `TODO_HUMAN` |
| `api/` | Shared | Stubs until each owner flips their env switch |

Integration point: Saturday 19:00 Europe/London, with `S1_IMPL=real`, `S2_IMPL=real`, and `MEMORY_IMPL=mubit` together. Contracts stay frozen at `v0.2-contracts` until then.
