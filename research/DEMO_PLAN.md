# Demo plan for Saturday

Europe/London (UTC+1). The Night Shift check-ins are 12:00 and the window from 12:00 to 18:00. Our own integration point stays 19:00. This note does not pick a track or a model.

Positioning line, if you need it in the first minute: "Mubit governs memory, policy, and traceability. System 1 acts fast. System 2 reasons deeply with Nemotron as its orchestrator. The Decision Router turns their outcomes into one safe next action."

## Storyline

One synthetic caller. Three beats. No real household, no phone number, no street.

1. **A clear call.** Play `F01` (or whichever clear fixture you rehearse). The gateway retrieves mock memory, routes only to System 1, and the router copies that one outcome. The trace shows a gateway event and a System 1 event with the outcome attached. System 2 does not appear. Say that Mubit did not decide the priority.
2. **A call that is not clear.** Play `F10`. The gateway routes only to System 2. The trace has a System 2 outcome and no System 1 outcome. The next action asks a human. If Nemotron is still a stub, say so, and show the 501 that `S2_IMPL=real` returns rather than pretending.
3. **The correction becomes a model update.** This is the beat the judging sheet asks for. Run `make demo-correction-loop`. A synthetic water request is labelled information-only, an operator correction stores a memory item, a one-row SFT/LoRA JSONL file is written, a training job is recorded as a stub, model version `stub-1` is registered, and the replay prints route accuracy 0.0 then 1.0, latency 20 ms then 28 ms, and cost null. Say, out loud, that `graduation_threshold` is still unset, so nothing was promoted into System 1, and that the job did not train weights. If Mubit is live by the afternoon, replace the stub job with whatever the adapter guide actually starts. If it is not, the stub is the honest demo.

`C01-a` / `C01-b` is the second correction beat if you have time: a correction posted on the first case shows up in the second case's memory. That is memory. Beat 3 is the model version. Do not let the judges confuse them. The public Mubit docs are thin on the training hop; `research/MUBIT.md` says that plainly.

## The four judging criteria

Equal weight. Map the beats, do not add a fifth slide.

| Criterion | What you show |
|---|---|
| Use of Mubit | Beat 3, and the sentence that every LLM call goes through `llm/client.py` or does not happen. If the key is unset, show the refusal rather than a direct provider call. |
| Usefulness | Beat 1 and beat 2 on a flood call a Thai operator would recognise: district, people, water, a human on the high-risk one. The map (`/map/flood`, `/map/facilities`) is the picture. Aid stays a 501 unless Melanie has a real check. Do not invent a baht amount. |
| Technical execution | Exclusive routing (one system on the trace), contracts at `v0.2-contracts`, `make validate` and `make test` green, and an answer for "what if the correction is wrong?" (`research/PAPERS.md`, the RiCL note). |
| Demo | Three beats, scripted, under the time limit. Rehearse the command once at 18:30. `eval/out/` is gitignored; run it during the demo, do not depend on a leftover file. |

## Tracks, as options

Pick one primary by the 12:00 check-in. The others can be a sentence.

| Track | What we already have | What is still a stub |
|---|---|---|
| Recurring tasks — corrections become model updates | `make demo-correction-loop` | A real Mubit adapter or training job. The JSONL row is one synthetic example |
| Own your intelligence layer — quality, cost, latency of an open model against a closed one | `eval/compare.py` prints all three. Cost is null until `llm.token_price_usd` is set | A named open model and a named closed baseline. `research/MODELS.md` lists options and does not pick |
| Fast refresh — the model keeps up with new flood data | Ingest is already repeatable (`make ingest`). Active-learning papers are in `research/PAPERS.md` | Nothing retrains when GISTDA or GDACS changes. GDACS itself only answers inside 05:00–07:45 Europe/London |

The correction loop serves the first track directly and the second track's scoreboard. It does not serve fast refresh unless someone points the dataset at a new day's fixtures. That is a good answer at the check-in, not a reason to build it this morning.

## Check-ins

**By 12:00.** Show the three beats on stubs. Say which track you are entering. Name the model you have *not* chosen yet, and the one decision that would unblock a live Mubit call (`llm.provider_route`, plus the key in `.env`, never in chat). Confirm `data.demo_event` is still open: northern fixture districts, Hat Yai, or the central-plain counts.

**12:00–18:00.** Replace at most one stub with a real path. The one that changes the judging score is the model-update hop, not a prettier map. Keep `make test` green after each replacement. Do not flip `S1_IMPL` and `S2_IMPL` together until 19:00.

**18:30.** One full rehearsal. Then stop changing the route chooser.

## Saturday task list

### A — Moly

- Rehearse beat 1 and beat 2 from `make demo-stub` and `/docs`.
- Decide whether the live route chooser is a rule, a small model, or "fixtures only today". Until that is written down, non-fixture cases return 501. The harness lookup of `expected.system` is not the product rule.
- If there is time before 19:00, start `system1/decide.py` on the seven clear fixtures (`F01`–`F07`) and the two duplicates (`F08`, `F09`). Leave escalation rules unread until you have looked at `research/triage-philosophy.md`.
- Call-agent surface: the transcript player is the UI. A dispatch view can sit on `/cases` and `/map`. Framework stays `TODO_HUMAN`.
- Do not implement `router/merge.py` unless the exclusive stub is no longer enough for the demo. The stub already returns one next action.

### B — Melanie

- Own beat 3. Run `make demo-correction-loop` until the narration is one minute.
- Aid caseworker: `GET /aid/eligibility` and `POST /aid/exceptions` return 501 and must not approve a payment. A real check can return `needs_human`. It cannot return an amount.
- Memory: `memory/mubit.py` is the client to fill once `memory.mubit_project` and the key exist. Keep the adapter. Do not put a retrieval call back in front of the gateway.
- Nemotron: `system2/orchestrator.py` raises before any network while its model, hosting, and latency budget are unset. `use_banyan_sapling` is already true. When the orchestrator returns, `decide()` runs the Sapling verifier on aid-eligibility and denial outcomes. The committed client is the stub. `SAPLING_IMPL=live` refuses while hosting, the GPU, the model id, or Thai handling is unset, and it does not open a socket. Chat completions stay on `llm.complete`.
- Eval: extend `eval/compare.py` when you have a real before and after. Leave cost null until a human sets a price.

### 19:00 integration

Both people, one process. `S1_IMPL=real`, `S2_IMPL=real`, `MEMORY_IMPL=mubit`, only for the paths that actually exist. Anything still raising should raise a 501 with the owner's name, not a guessed label. Contracts stay at `v0.2-contracts` unless a change went through `contracts/CHANGE_REQUESTS.md`. Replay the three beats once on the integrated process. If a switch is still stub, say which one, and do not paper over it.
