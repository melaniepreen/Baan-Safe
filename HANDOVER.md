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

## Plan (25 Oct, 03:15 UTC)

Four tracks. Order tonight: 1 → 4 → 3 (backend half). Track 2 is done except the shadow label. Owners per `OWNERSHIP.md`: Moly = API / calls / flow / infra, Melanie = S2 / Sapling / decision brains / `ui/sim`.

### Track 1 — Mubit memory: from "wired" to "changed an outcome" (tonight, Moly)

State: hosted runs `MEMORY_IMPL=mubit` on workspace `ws-3e4ac86aadff0b72`, but every trace showed `items=0`. Judge read that as "claimed, not used".

| Step | What | Status |
|---|---|---|
| 1a | `feat/memory-record-metrics`: call `store_record()` after the router; carry `source_case_id` through ingest/retrieve so S1 `duplicate_merge` can fire; `memory` block on `GET /metrics` (`retrieve_count`, `hit_count`, `item_total`, `write_count`, `duplicate_merge_count`, `hit_rate`); `memory_write` trace stage | agent running |
| 1b | `feat/memory-seed`: `scripts/seed_memory.py` + `make seed-memory` (6–10 policy lessons from `policies/` into the workspace, idempotent); live proof turn 1 → correction → turn 2 on the hosted URL | agent running |
| 1c | Merge 1a then 1b; re-run seed once if 1a changed the ingest shape | after both land |
| 1d | `modal deploy` gateway; smoke: turn 1, correction, turn 2 shows `memory via adapter mode=mubit; items≥1`, router note `retrieved correction memory`, `/metrics.memory.hit_count≥1` | after 1c |
| 1e | Frozen script step 3 becomes "second caller → memory retrieves the correction"; point at `/metrics` memory block | after 1d |

Not tonight: `memory_ref` on the training event (ties memory to the fine-tune story).

### Track 2 — Fine-tuning: decide, don't train (tier 1 done)

| Tier | What | Status |
|---|---|---|
| 1 | `modal.finetune_base_model = nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1`, `modal.finetune_gpu = T4`, both in `DECIDED`. Real SetFit run on T4: version **`ft-20261025T031241Z-e4ce5eb6`** on `baansafe-versions` (168 rows, 20 steps, `train_loss 0.3013`). `FINETUNE_S1_MODEL` stays env-only | **done, PR #19** |
| 2 | SetFit **shadow** label: `S1_SHADOW_VERSION=<id>` loads the adapter off the volume, emits `shadow_label` + `shadow_confidence` in the `system_1` trace. Never changes `next_action`. Gives Melanie a disagreement rate | post-demo, ~½ day, Moly plumbing / Melanie reads |
| 3 | S1 stays rules-only (DECIDED). Laya full-encoder recipe parked until human events exist (log has 25, mostly from `demo-correction-loop`) | decision, no work |
| 3 | Sapling: stays stub by decision. When reopened: `sapling.hosting=self-hosted`, `sapling.gpu=L40S`, `sapling.model_id=MubitLabs/banyan-sapling`, `sapling.thai_handling=translate`; needs CUDA 13 base image and confirmation Mubit can route to a self-hosted endpoint. 0 `sapling_verdict` rows, so nothing to fine-tune | post-demo, Melanie |
| 3 | STT: stays scripted. When reopened: `modal.stt_model_id=biodatlab/whisper-th-large-v3-combined`, `modal.stt_gpu=T4` | post-demo, unowned |

Carry-forward bug: `s1_app`, `s2_app`, `sapling_app`, `stt_app` chain `.env()` after `with_repo()`; Modal 1.6 rejects that on deploy. Two-line reorder each (see `finetune_app.py` on `main`). Fix when any of them is next deployed.

### Track 3 — S2 cache + overlay "learns to be faster" demo

Design reviewed against code. Compatible with four corrections:

1. `make rl-loop-replay` does **not** write the cache; only live `make rl-loop` does, and `eval/out/` is gitignored. Ship a committed `fixtures/s2_cache/demo.jsonl` read via `S2_CACHE_PATH`.
2. No signature-based key. Exact key only; the sim plays fixtures that are in the cache. A reply recorded for a different prompt is not a cache hit.
3. Record the cache **after** Track 1 lands (memory items are in `_messages`, so the key changes once the workspace has content).
4. Local `make hackathon-demo` vs hosted URL tell different stories (no LLM calls vs real Mubit traffic). Pick one for the 3-minute script; hosted stays the judges' URL unless both agree.

| Half | What | Owner / effort |
|---|---|---|
| Backend | `S2_IMPL=cache` installs the replay completer via `system2.orchestrator.use_completer()` at `api/main.py` startup (no change to `orchestrate()`); miss → existing `system2_unavailable`; cache hit emits `mubit_chat status=cache_hit` via `eval/rl/run._emit_rl_cache_hit`; `make hackathon-demo` = `RL_OVERLAY=… S1_IMPL=real S2_IMPL=cache make serve` | Moly, ~2 h, after Track 1 |
| UI | Model Path panel (stage list with latency + cache hit + graduated rule), purple house = S1 via graduated rule, "Learned" badge in `patterns.js`; `rl_panel.js` already renders overlay tables | Melanie, ~5 h, after she pulls `main` |

### Track 4 — Judge items still open

| # | Who | Item |
|---|---|---|
| 1 | Both | Paid S2 on the public URL: keep or stub. Watch `mubit_chat.call_count` and 429s (429 → `system2_unavailable`). |
| 2 | Moly | Dry-run the frozen script on the hosted URL with the UI open, after 1d. |
| 3 | Melanie | Pull `main` (PRs #16–#19 plus Track 1) before touching `ui/sim`. |
| 4 | Both | Aid 501 UI / RL panel hidden or not. |
| 5 | Moly | `python -m contracts.export_schemas` so `TraceEvent.json` catches `enrich`, `memory`, `mubit_chat`, `memory_write`; bump the contract tag note. |

### Decisions needed from humans

- Track 4 #1 (paid S2 on public URL).
- Track 3 #4 (local cache demo vs hosted live demo for the script).
- Track 3 UI half: Melanie go / no-go for tonight.

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
