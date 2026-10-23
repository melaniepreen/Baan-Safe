# Ownership

Phase 0 is shared scaffolding. The decision logic behind each folder is still for the named owner. Nothing in `system1/` or `system2/` decides a case.

| Folder | Owner | Phase | Tonight |
|---|---|---|---|
| `system1/` | Moly | System 1 rules | `decide()` raises `NotImplementedError` |
| `gateway/` | Moly | Routing and trace | `handle(..., use_stubs=True)` works from mocks |
| `router/` | Moly | Merge policy | `merge()` raises `NotImplementedError` |
| `ui/` | Moly | Call agent UI | Transcript player only. Framework is `TODO_HUMAN` |
| `system2/` | Melanie | Deliberative reasoning | `decide()` raises `NotImplementedError` |
| `memory/` | Melanie | Mubit read/write | Raises until `MEMORY_IMPL=mubit` is real |
| `eval/` | Melanie | Replay harness | Scores stub outcomes. Does not decide them |
| `contracts/` | Shared | Frozen shapes | v0.1. Changes go through `contracts/CHANGE_REQUESTS.md` |
| `config/` | Shared | Judgement calls | Humans sign off. Big decisions stay `TODO_HUMAN` |
| `fixtures/` | Shared | Golden scenarios | Synthetic callers only |
| `mocks/` | Shared | Stand-in inputs | Lets either owner work alone |
| `ingest/`, `enrich/`, `data/` | Shared | Public data | SQLite tonight. Production database is `TODO_HUMAN` |
| `api/` | Shared | Phase 1 service | Stubs until each owner flips their env switch |

Integration point: Saturday 19:00, with `S1_IMPL=real`, `S2_IMPL=real`, and `MEMORY_IMPL=mubit` together. Contracts stay frozen at the latest tag until then.
