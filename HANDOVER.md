# Handover

25 October 2026. Tip: check `git rev-parse --short HEAD`. `make test` / `make validate` must stay green. `requirements.txt` has `openai>=1.40`.

**Judges-only URL (no auth):** `https://baansafe--baansafe-gateway-web.us-east.modal.run` — town at `/ui/sim/`. Do not broadcast.

## Main parts

One call: `gateway/route.py` `handle` ← `POST /triage` / `POST /cases/{id}/turns`.

| Part | Where | State |
|---|---|---|
| Extraction | `system1/extract.py` | English keywords; bare `unaccompanied` → child unless `adult` named. Thai = district names only. Demo English / code-switched. |
| Enrichment | `enrich/context.py`, `ingest.store` | Live when `districts.json` present. Flags never change priority. |
| Memory | `memory/adapter.py`, `memory/mubit.py` | Hosted **mubit** when `baansafe-mubit` secrets exist (same gate as S2). `/v2/control/query` + ingest; project `baansafe-demo` or `MUBIT_PROJECT_ID`. Retrieve soft-fails to `[]`. |
| Graduation | `gateway/graduation.py` | Threshold 2 → `complex_situation` (not into S1 rules). |
| Chooser | `gateway/chooser.py` | `field precheck`; `routing.yaml` `mode: cascade`. |
| System 1 | `system1/decide.py` | Rules-only. |
| System 2 | `system2/orchestrator.py` | Hosted **real** when `baansafe-mubit` injects key+URL. |
| Sapling | `system2/sapling.py` | Stub. |
| Router / ledger | `router/merge.py`, `ledger.py` | Confirm/cancel; in-process holds. Modal **`max_containers=1`**. |
| Traces | `llm/client.py`, `GET /metrics` | `mubit_chat` on every hop (and RL cache hits). |
| UI | `ui/sim/` | Wired to transcript / dispatches / `location_context`. **Freeze until Melanie reviews.** |
| Hosting | Modal gateway | Redeployed `3d1f362` era; `include_source=True`. Smoke: `/hosting` live, one S2 turn, `mubit_chat.call_count≥1`. |
| Place | `data.demo_event` | **`Sukhumvit / Watthana (Bangkok)`** — matches basemap + `flood.json`. |

Owners: `OWNERSHIP.md`. Contracts: `v0.3-contracts` (TraceEvent stages grew; schema sync still backlog).

---

## Done recently (do not re-open)

| Item | Notes |
|---|---|
| Safeguarding / unaccompanied adult | `0fdc34e` + PR #11 adult fix |
| Thai need keywords | **Reverted** — leave off |
| PR #9 town + wire P0 | Transcript creates, dispatches, confirm/cancel |
| Mubit traces + `/metrics` + RL traces | `96bef6e`…`e1fc17d` |
| Modal S1 real + mubit secret / S2 gate | `c996c35` |
| G01–G04 → system_2 | `110e370` |
| Judge audit into HANDOVER | PR #11 |
| Place → Sukhumvit / Watthana | PR #12 |
| Modal `max_containers=1` | PR #12 |
| Modal `include_source=True` (crash-loop fix) | PR #13 |
| Hosted smoke | `/hosting` `backends=live`, S2 real; free-text oxygen → S2; `mubit_chat` ok |
| Mubit memory client + three decisions | `memory/mubit.py` query/ingest. Local default `MEMORY_IMPL=mock`. Hosted sets `mubit` when the secret exists |

---

## What’s left

### Must decide / do before judges (tonight)

| # | Who | Action |
|---|---|---|
| 1 | Both | **Keep paid S2 on public URL?** Smoke left it **on** (`S2_IMPL=real`). Else redeploy with stub / no secret spend. Watch `/metrics` and 429s. |
| 2 | Both | Optional: set `MUBIT_PROJECT_ID` to a console `proj-…` if `baansafe-demo` is empty. Pitch: gateway + traces + live memory retrieve. |
| 3 | Melanie | Pull `main`, rebase any local `ui/sim` work; review Moly’s town wire before editing. |
| 4 | Moly | Share URL **only with judges**; run the frozen 3‑min script once dry. |
| 5 | Both | Optional: hide aid 501 UI / keep RL panel off (`index.html` does not load `rl_panel.js`). |

### Frozen 3-minute script

1. English **S1** (e.g. F02 rice) — threshold accept, boat may move.  
2. **S2** (e.g. F10 oxygen / under threshold) — PENDING → Accept; say Mubit→Nemotron; point at `/metrics` if a live hop ran.  
3. Reject → Correct this, or repeat theme ×2 → **Graduated to S2**.  
4. Cards in `sim_events.json` are **scripted**; one live hop proves traces.

### Nice-to-have / backlog (not demo blockers)

| # | Action |
|---|---|
| A | Sync `contracts/schemas/TraceEvent.json` to Pydantic stages (`enrich`, `memory`, `mubit_chat`); note/bump contract tag |
| B | Completers accept `**kwargs` (`case_id`) — Melanie check |
| C | Northern fixtures vs Sukhumvit units — use F17/F18 or accept first usable unit |
| D | Post-hackathon: `gateway.auth`; shared ledger/DB if multi-container |
| E | Live Sapling / STT; Laya/classifier product decision; RL `run.json` on Modal |
| F | Thai keywords only if product reopens |
| G | Housekeeping: `.vscode` gitignore, markdown moves, `routes.yaml` vs needs table |

### Branch policy

Branch → PR → merge when `make test` / `make validate` green. Do not push feature work straight to `main`. Prefer one writer on `ui/sim/sim.js` and `llm/client.py`.

---

## Live System 2

Model: `nvidia/nemotron-3-nano-30b-a3b` via Mubit. Hosted promotes when secret has key+URL. 429 → `system2_unavailable`. Replay: `make rl-loop-replay` (misses = fallbacks).

Architecture: `BaanSafe_Revised_Architecture.md`. Wire plan: `docs/wire-frontend.md`.

## Laya / latte-bench

Laya = export + optional train; S1 stays rules-only until a product wire. `make latte-bench` often skips without `bun`.
