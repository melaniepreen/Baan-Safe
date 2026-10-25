# Handover

25 October 2026. Tip: check `git rev-parse --short HEAD`. `make test` / `make validate` must stay green. `requirements.txt` has `openai>=1.40`.

**Judges-only URL (no auth):** `https://baansafe--baansafe-gateway-web.us-east.modal.run` — town at `/ui/sim/`. Do not broadcast.

## Main parts

One call: `gateway/route.py` `handle` ← `POST /triage` / `POST /cases/{id}/turns`.

| Part | Where | State |
|---|---|---|
| Extraction | `system1/extract.py` | English keywords; bare `unaccompanied` → child unless `adult` named. Thai = district names only. Demo English / code-switched. |
| Enrichment | `enrich/context.py`, `ingest.store` | Live when `districts.json` present. Flags never change priority. |
| Memory | `memory/adapter.py`, `memory/local.py` | Hosted **local** (`MEMORY_LOCAL_PATH=/data/memory.jsonl` on `baansafe-demo`). Case record written after every routed turn (`memory_write` stage); policy lessons seeded; repeat caller at same place + need → S1 `duplicate_merge`. `GET /metrics.memory`. `memory/mubit.py` is dormant: current Mubit has no memory API (`/v2/control/*` = 404). |
| Graduation | `gateway/graduation.py` | Threshold 2 → `complex_situation` (not into S1 rules). |
| Chooser | `gateway/chooser.py` | `field precheck`; `routing.yaml` `mode: cascade`. |
| System 1 | `system1/decide.py` | Rules-only. |
| System 2 | `system2/orchestrator.py` | Hosted **real** when `baansafe-mubit` injects key+URL. |
| Sapling | `system2/sapling.py` | Stub. |
| Router / ledger | `router/merge.py`, `ledger.py` | Confirm/cancel; in-process holds. Modal **`max_containers=1`**. |
| Traces | `llm/client.py`, `GET /metrics` | `mubit_chat` on every hop (and RL cache hits). Every call sends `metadata.session_id=case_id`; Mubit groups all S2 calls into one Task (static system prompt). ~650 distinct requests sent 25 Oct (RL loop + synthetic set + two `make mubit-traffic` batches: seed 3 → 160 hops, seed 11 → 204 hops, all distinct sessions). Top up with `make mubit-traffic COUNT=n SEED=s`. |
| UI | `ui/sim/` | Wired to transcript / dispatches / `location_context`. **Freeze until Melanie reviews.** |
| Hosting | Modal gateway | Redeployed at `82e68ac` (25 Oct 04:15 UTC). `/hosting` → `backends=live`, `memory=local`. Smoke: two callers on Sukhumvit Soi 22 → second one `finalize_case` with `duplicate_merge_count=1`, `write_error_count=0`. |
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
| Memory: local store, write path, metrics | PRs #20 #22 (+ #23 session ids, #24 RL note). Mubit memory API does not exist in the current product; `MEMORY_IMPL=local` is the hosted default. Seed with `MEMORY_IMPL=local make seed-memory`, upload via `modal volume put baansafe-demo <file> memory.jsonl` |
| Fine-tune decisions + SetFit run | PR #19, version `ft-20261025T031241Z-e4ce5eb6` |
| Training surface: loss curves, `GET /training`, `ui/training.html` | PR #28 (+ #26 `make mubit-traffic`, #27). Hosted: `/training` and `/ui/training.html` read `baansafe-versions` (ro at `/vol`) and `/data/rl_run.json` |

---

## Plan (25 Oct, 03:15 UTC)

Four tracks. Order tonight: 1 → 4 → 3 (backend half). Track 2 is done except the shadow label. Owners per `OWNERSHIP.md`: Moly = API / calls / flow / infra, Melanie = S2 / Sapling / decision brains / `ui/sim`.

### Track 1 — Memory: done (local store), Mubit memory API does not exist

Finding (25 Oct, verified live and in docs.mubit.ai): current Mubit is an LLM gateway that records calls and trains per-task adapters. `https://api.mubit.ai/v2/control/*` returns `404 unknown_route`; the `/v2/control` client came from the retired "Mubit Memory" SDK. The hosted `items=0` was a swallowed 404, and corrections were 500ing on the hosted demo.

| Step | What | Status |
|---|---|---|
| 1a | PR #22: honest `retrieve_error=` on the memory trace, correction kept locally (no more 500), `scripts/seed_memory.py` with 10 policy lessons from `policies/service.py`, `MUBIT_CONTROL_URL` override | merged, deployed |
| 1b | PR #20: `MEMORY_IMPL=local` (`memory/local.py`, JSONL, field-overlap scoring), `store_record()` after the router, `source_case_id` round-trip, own-case exclusion, `/metrics.memory`, 16 new tests | merged, deployed |
| 1c | Seeded `/data/memory.jsonl` on `baansafe-demo` with the 10 lessons | done |
| 1d | Hosted proof: caller A (water, Sukhumvit Soi 22) → `create_provisional_dispatch`, `items=2`; caller B next door, same need → `items=3`, `finalize_case`, `duplicate_merge_count=1` | done |
| 1e | Frozen script step 3 uses the two-caller merge | done below |

Known behaviour to say out loud: duplicate detection is district/street + need granularity (that's all the record carries), so two households on the same soi with the same need merge. The town's Reject button writes a correction lesson into the same store.

### Track 2 — Fine-tuning: decide, don't train (tier 1 done)

| Tier | What | Status |
|---|---|---|
| 1 | `modal.finetune_base_model = nvidia/Llama-3.1-Nemotron-Nano-4B-v1.1`, `modal.finetune_gpu = T4`, both in `DECIDED`. Real SetFit run on T4: version **`ft-20261025T031241Z-e4ce5eb6`** on `baansafe-versions` (168 rows, 20 steps, `train_loss 0.3013`). `FINETUNE_S1_MODEL` stays env-only | **done, PR #19** |
| 1b | Loss curves + held-out eval in `finetune_job.py` (PR #28). Versions on `baansafe-versions`, all visible at `/training` and `/ui/training.html`: `ft-20261025T045101Z-e4ce5eb6` SetFit s1_triage, 168 rows, 20 loss points (`loss_source=log_history`), **held-out accuracy 0.875 on 72 rows**; `ft-20261025T045212Z-8d9937b9` LoRA on the 7-row event s2 set, loss 14.27 → 0.0017 (overfit, 7 rows); `ft-20261025T045425Z-114efba3` LoRA on the 36-row RL s2 set, loss 13.20 → 6.56. Re-run: `SYNTHETIC=1 make export-training` then `make modal-finetune DATASET=training/out/s1_synthetic.jsonl` (held-out picked up automatically) or `DATASET=eval/out/rl/training/s2.jsonl`; refresh RL block with `modal volume put --force baansafe-demo eval/out/rl/run.json rl_run.json` | **done** |
| 2 | SetFit **shadow** label: `S1_SHADOW_VERSION=<id>` loads the adapter off the volume, emits `shadow_label` + `shadow_confidence` in the `system_1` trace. Never changes `next_action`. Gives Melanie a disagreement rate | post-demo, ~½ day, Moly plumbing / Melanie reads |
| 3 | S1 stays rules-only (DECIDED). Laya full-encoder recipe parked until human events exist (log has 25, mostly from `demo-correction-loop`) | decision, no work |
| 3 | Sapling: stays stub by decision. When reopened: `sapling.hosting=self-hosted`, `sapling.gpu=L40S`, `sapling.model_id=MubitLabs/banyan-sapling`, `sapling.thai_handling=translate`; needs CUDA 13 base image and confirmation Mubit can route to a self-hosted endpoint. 0 `sapling_verdict` rows, so nothing to fine-tune | post-demo, Melanie |
| 3 | STT: stays scripted. When reopened: `modal.stt_model_id=biodatlab/whisper-th-large-v3-combined`, `modal.stt_gpu=T4` | post-demo, unowned |

Carry-forward bug: `s1_app`, `s2_app`, `sapling_app`, `stt_app` chain `.env()` after `with_repo()`; Modal 1.6 rejects that on deploy. Two-line reorder each (see `finetune_app.py` on `main`). Fix when any of them is next deployed.

### Track 3 — S2 cache + overlay "learns to be faster" demo

**Backend half done (PRs #31, #32), hosted in cache mode.** `S2_IMPL=cache` (`system2/cache.py`): cache-first completer, Mubit only on a miss, miss recorded to `S2_CACHE_RECORD_PATH`. Committed `fixtures/s2_cache/demo.jsonl` holds 158 replies (fixtures + synthetic, `MEMORY_IMPL=mock`, exact key); `make record-s2-cache` refills misses. Hosted: `/hosting` → `backends: cache`, `S2_CACHE_KEY=case` (ignores random case id, memory summaries, ledger), record file `/data/s2_cache.jsonl`. Proof 25 Oct 05:40: frozen script pass 1 → F10 and caller B `api.mubit.ai status=ok`; pass 2 → both `s2_cache/case status=cache_hit`, `/metrics.mubit_chat.cache_hit_count=2`. **Before the demo, run the exact script once more after any transcript edit** — a changed word is a miss (goes live, then recorded). To flip back to live-only: `S2_IMPL=real modal deploy infra/modal/gateway_app.py`. `TraceEvent.json` synced (Track 4 #5 done). UI half still Melanie's.

Design reviewed against code. Compatible with four corrections:

1. `make rl-loop-replay` does **not** write the cache; only live `make rl-loop` does, and `eval/out/` is gitignored. Ship a committed `fixtures/s2_cache/demo.jsonl` read via `S2_CACHE_PATH`.
2. No signature-based key. Exact key only; the sim plays fixtures that are in the cache. A reply recorded for a different prompt is not a cache hit.
3. Record the cache **after** Track 1 lands (memory items are in `_messages`, so the key changes once the workspace has content).
4. Local `make hackathon-demo` vs hosted URL tell different stories (no LLM calls vs real Mubit traffic). Pick one for the 3-minute script; hosted stays the judges' URL unless both agree.

| Half | What | Owner / effort |
|---|---|---|
| Backend | **done**: `orchestrator._active_completer()` picks `system2.cache.completer` when `S2_IMPL=cache` and no `use_completer` override; miss with creds → one Mubit call (recorded), miss without → `system2_unavailable`; hit emits `mubit_chat host=s2_cache[/case] status=cache_hit`. Local demo: `S1_IMPL=real S2_IMPL=cache make serve` (fixtures hit the committed file) | Moly, PRs #31 #32 |
| UI | Model Path panel (stage list with latency + cache hit + graduated rule), purple house = S1 via graduated rule, "Learned" badge in `patterns.js`; `rl_panel.js` already renders overlay tables | Melanie, ~5 h, after she pulls `main` |

### Track 4 — Judge items still open

| # | Who | Item |
|---|---|---|
| 1 | Both | Paid S2 on the public URL: keep or stub. Watch `mubit_chat.call_count` and 429s (429 → `system2_unavailable`). |
| 2 | Moly | Dry-run the frozen script on the hosted URL with the UI open, after 1d. |
| 3 | Melanie | Pull `main` (PRs #16–#19 plus Track 1) before touching `ui/sim`. |
| 4 | Both | Aid 501 UI / RL panel hidden or not. |
| 5 | Moly | ~~`python -m contracts.export_schemas`~~ done in PR #31 (`enrich`, `memory`, `mubit_chat` added to `TraceEvent.json`). |

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
| 2 | Both | Ask Mubit to switch **training on** for workspace `ws-3e4ac86aadff0b72` (console has no Adapters page). The System 2 Task already holds ~650 requests across ~650 sessions (adapter cycle ran 25 Oct ~04:00 with issues; see Mubit history). `make mubit-traffic` adds more distinct examples any time. Pitch: gateway + traces + per-task adapter; memory is ours. |
| 3 | Melanie | Pull `main`, rebase any local `ui/sim` work; review Moly’s town wire before editing. |
| 4 | Moly | Share URL **only with judges**; run the frozen 3‑min script once dry. |
| 5 | Both | Optional: hide aid 501 UI / keep RL panel off (`index.html` does not load `rl_panel.js`). |

### Frozen 3-minute script

1. English **S1** (e.g. F02 rice) — threshold accept, boat may move.  
2. **S2** (e.g. F10 oxygen / under threshold) — PENDING → Accept; say Mubit→Nemotron; point at `/metrics` if a live hop ran.  
3. Second caller, same soi + same need → **memory** `items≥1`, S1 `duplicate_merge` (no second truck); `/metrics.memory.duplicate_merge_count`. Then Reject → Correct this (lesson lands in the store).  
4. Cards in `sim_events.json` are **scripted**; one live hop proves traces.

### Nice-to-have / backlog (not demo blockers)

| # | Action |
|---|---|
| A | ~~Sync `TraceEvent.json`~~ done (PR #31) |
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
