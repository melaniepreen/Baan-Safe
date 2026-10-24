# BaanSafe PRD

Shared product and interface note for Moly and Melanie. Every claim below is what the code on `main` does. This file does not set a value in `config/decisions.yaml`. Owners in the status table are from `OWNERSHIP.md`. Callers are synthetic: `caller_id_hash` values look like `synthetic:f02`, and `scripts/validate.py` rejects phones, 13-digit ids, PromptPay, passport, immigration status, and bank account.

## 1. Product

BaanSafe is a flood call-triage scaffold for a synthetic Thai flood. A call is triaged, a provisional dispatch can be named, and aid casework is a separate check that does not approve a payment. Mubit governs memory, policy, and traceability and does not reason. One turn goes to System 1 or System 2, never both. Every LLM call goes through `llm/client.py` or `llm/openai_client.py`. Both refuse a host that is not `api.mubit.ai` or a `mubit.ai` subdomain. `llm.provider_route` is `mubit`. The OpenAI SDK base is the Mubit compat prefix (`/compat/openrouter/v1`). There is no OpenRouter client.

Demo story, as the town page runs it (`ui/sim/`, `make serve`, `http://127.0.0.1:8000/ui/sim/`):

- The picture is a placeholder block. `data.demo_event` is `TODO_HUMAN`. Household districts are the fixture districts (Lampang, Phrae, Nan, Phayao). Street names in `ui/sim/data/streets.json` are marked placeholder.
- The phone sends a line by matching it to one of 20 fixture ids (`ui/sim/data/town.json` `calls`, same order as `fixtures/index.json`), then `POST /cases` with that `fixture_id` and `POST /cases/{id}/turns` with the typed or spoken text.
- The gateway returns a `RouterDecision`. `final_priority` lights the house (P1 red, P2 amber, P3 yellow, P4 blue). The phone speaks a scripted line from `ui/sim/data/replies.json`, not a live operator.
- The right-hand feed plays `ui/sim/data/sim_events.json`. Every card is badged simulated. Its confidence threshold (default 0.75) is page-only. It is not `system_1_min_confidence` (0.80) and it is not the field precheck.
- Reject opens Correct this (`ui/correct.js`) and posts `POST /cases/{id}/corrections`.
- Speech uses the browser Web Speech API, else `POST /stt/transcribe`. This API does not mount `infra/modal/stt_app`. If neither returns words, the phone shows a stub transcript and sends nothing.

Scope that is in the tree tonight:

- Gateway: keyword-extract when fields are empty, enrich, mock memory, field precheck, one stub outcome, `router.merge`.
- System 1 rules (`system1/extract.py`, `system1/decide.py`) when `S1_IMPL=real` or `use_stubs=False`. The API default is `use_stubs=True`, so a normal `/turns` call still uses the stub outcome file.
- System 2, Sapling's live client, aid eligibility, aid exceptions, and the Mubit memory client still raise or return HTTP 501.
- Integration named in `OWNERSHIP.md`: `S1_IMPL=real`, `S2_IMPL=real`, and `MEMORY_IMPL=mubit` together. Contracts are v0.2 plus CR-003 (`Dispatch`, `RouterDecision.dispatches`, tag pending).

`frontend-prototype/` is not part of this product surface.

## 2. Status

| Component | Owner | State | Files |
|---|---|---|---|
| Gateway turn | Moly | live | `gateway/route.py` `handle` |
| Field precheck | Moly | live. Decided value `field precheck` | `gateway/chooser.py`, `config/escalation.yaml` |
| Keyword extract | Moly | live. English phrase and regex families. Skipped when the case already has fields and `keyword_extraction` is absent | `system1/extract.py` |
| System 1 decide | Moly | live rules. Default request uses the stub file instead | `system1/decide.py`, `mocks/s1_stub/` |
| Aid eligibility | Melanie | stub. `check` raises. `GET /aid/eligibility` is 501 | `system1/aid_eligibility.py` |
| Router merge | Moly | live. Always called from `handle` | `router/merge.py` |
| Auth | Moly | TODO_HUMAN. A note is recorded. The request is not rejected | `gateway/auth.py` |
| Enrichment | shared | live when SQLite exists, else off | `enrich/context.py`, `ingest/db.py` |
| Policy pre-check | Moly | live notes only. Does not change priority | `gateway/policy.py` |
| Memory mock | Melanie | live for fixture ids | `memory/adapter.py`, `mocks/memory_context/` |
| Mubit memory client | Melanie | stub. Raises. Three keys are TODO_HUMAN | `memory/mubit.py` |
| System 2 / Nemotron | Melanie | stub. `orchestrate` raises while the model id or latency is TODO_HUMAN | `system2/decide.py`, `system2/orchestrator.py` |
| Sapling | Melanie | gate is written. Client is `stub`. Not reached while `orchestrate` raises | `system2/sapling.py`, `system2/sapling_client.py` |
| Aid exceptions | Melanie | stub. `POST /aid/exceptions` is 501 | `system2/aid_exceptions.py` |
| LLM clients | Melanie wires the call | host check is live. Not called on a triage turn | `llm/client.py`, `llm/openai_client.py` |
| Policy corpus | Melanie | live `GET/POST /policies`. `policies.authoritative_set` is TODO_HUMAN | `policies/service.py`, `api/routes/policies.py` |
| Town phone and feed | `OWNERSHIP.md` lists `ui/` as Moly. The phone, feed, and rulebook are what the demo consumes | live page. Feed and vehicle picture are simulated | `ui/sim/sim.js`, `ui/sim/data/` |
| Correct this | Moly | live post of a v1 correction | `ui/correct.js`, `ui/player.html` |
| Training log and export | shared log, Melanie eval | live append and export. Fine-tune refuses a TODO_HUMAN base model | `training/log.py`, `training/export.py`, `infra/modal/finetune_job.py` |
| Held-out eval | Melanie | stub scoreboard. Does not load weights. Promotion stays false | `eval/learning/` |
| Extract eval | Moly rules, shared fixtures | live comparison of extract vs hand-filled fields. Writes `eval/out/extract.md` | `eval/extract_eval.py` |
| Caller sim | Melanie | scripted path is live. Model backend is TODO_HUMAN | `sim/env.py`, `sim/coach.py` |
| Modal apps | shared | refuse to start while `modal.*` is TODO_HUMAN | `infra/modal/` |
| Speech to text | shared | TODO_HUMAN. Not mounted on this API | `infra/modal/stt_app.py` |

## 3. Shared context

Models are Pydantic v2 with `extra=forbid`. JSON Schema copies are `contracts/schemas/*.json`. Required fields below are the schema `required` arrays.

### 3.1 Phone turn to the gateway

Producer: the town phone (`ui/sim/sim.js` `runPlaceCall`). Consumer: Moly's `gateway.route.handle` via `api/routes/endpoints.py` `execute` (`use_stubs=True`).

Path: `POST /cases` `{ "fixture_id": "F02" }` then `POST /cases/{case_id}/turns` with a `TranscriptTurn`. The turn response is `TurnResult`: `case` (`CaseState`) and `decision` (`RouterDecision`). `POST /triage` takes a full `CaseState` and returns the same `RouterDecision`. The phone does not call `/triage`.

`CaseState` required: `case_id`, `caller_id_hash`, `transcript`, `fields`, `received_at`. `TranscriptTurn` required: `t_ms` (int ≥ 0), `speaker` (`caller` or `operator`), `text` (non-empty).

To match the gateway, Melanie must provide either a known `fixture_id` or a `transcript` of `TranscriptTurn`s. A body with neither is HTTP 422. Moly must accept that turn and return one `RouterDecision`. He must not route from `fixtures/... expected.system`. The chooser reads fields and `policy_flags`.

Minimal turn:

```json
{ "t_ms": 1000, "speaker": "caller", "text": "Our rice is finished." }
```

Mismatch: `ui/sim/sim.js` and `ui/sim/README.md` still say `gateway.route_chooser` is `TODO_HUMAN`. The decided value is `field precheck`, and `gateway/chooser.py` runs for every case, including fixtures. The page still maps free text onto a fixture id. Fixture cases already have hand-filled `fields` and no `keyword_extraction` flag, so `gateway/route.py` `_extract` does not run, and the new sentence is not what the chooser sees.

### 3.2 Extracted fields to the chooser and to System 1

Producer: Moly `system1.extract.extract(transcript, districts=None) -> (ExtractedFields, flags)`. Consumer: `gateway/chooser.py` and `system1/decide.py`. Melanie's System 2 will read the same `CaseState.fields` when `orchestrate` returns.

`ExtractedFields`: `location` (str or null), `location_confidence` (0–1 or null), `people_count` (int ≥ 0 or null), `vulnerable` (str list), `medical` (bool, default false), `danger` (str list), `needs` (list of `Need`). No field is required; defaults are null, false, and empty lists. `Need`: `rescue`, `medical`, `water`, `food`, `shelter`, `evacuation`, `power`, `information`, `aid_payment`.

The gateway attaches the returned flags plus `keyword_extraction` only when it actually extracts.

Chooser triggers (`config/escalation.yaml` `route_to_system_2_if_any`), any one sends the turn to System 2:

- `fields.medical`
- `vulnerable` contains `oxygen_dependent` or `immobile`
- location is missing, confidence is missing, or confidence is below 0.7
- `policy_flags` contains `safeguarding`, `conflicting_evidence`, or `aid_exception`
- `needs` contains `rescue`, `medical`, or `aid_payment`

`extract` reads caller turns only. A negator in the three words before a match drops it. Aid phrases and minimising phrases are exempt: "we cannot get the payment" and "not eligible" stay aid signals. Suggested flags are `conflicting_evidence` (minimising language plus danger, rescue, medical, or a child, elderly person, or immobile person), `safeguarding` (a child and an alone-phrase), and `aid_exception` (an aid phrase plus a refusal). Water at a door, step, or inside a room, or in the street, adds danger `rising_water`. That also adds need `rescue` when a child, elderly person, immobile person, or oxygen-dependent person was extracted, or when the water is at the building and evacuation was not already a need. "bus shelter" is not a shelter need.

To match the chooser, Melanie must leave those field names and flag strings as they are when she builds a non-fixture case. Moly must keep `extract` English-only and must not treat operator turns as evidence. `system1.extraction_method` is `rules-only`. `system1.extraction_model` stays `TODO_HUMAN` and the rules do not read it.

Minimal fields the fast path can accept:

```json
{
  "location": "Mae Tha District, Lampang",
  "location_confidence": 0.93,
  "people_count": 3,
  "vulnerable": [],
  "medical": false,
  "danger": [],
  "needs": ["food"]
}
```

Mismatch: `make extract-eval` scores extract against hand-filled fixture fields, and again against the scripted sim callers. An unsafe answer is a case whose true fields go to System 2 while the extracted fields get a System 1 answer with `requires_human` false. Fixture cases on the phone never take the extract path, so the demo does not show that score. `F15` hand fields include `vulnerable: child`, but the word "child" is only in an operator turn ("I can hear a child crying"). Caller text says "They are upset" and "invented bus shelter", which extract does not treat as a child or a shelter need. Graduation fixtures `G01`–`G04` are labelled `expected.system` `system_1` with need `rescue`. The precheck routes `rescue` to System 2. The town labels are not that set. Town `calls[].expected_system` is the fixture label, not the chooser's result.

### 3.3 Memory items to System 1 and the router

Producer: Melanie `memory.adapter.retrieve(case) -> list[MemoryItem]`. Consumer: Moly `system1.decide` (duplicate rule) and `router.merge` (correction notes). The gateway assigns the list onto `case.memory_context` before the chooser.

`MemoryItem` required: `memory_id`, `kind`, `summary`, `relevance` (0–1). Optional `source_case_id`. `kind`: `similar_case`, `prior_failure`, `policy`, `correction`.

`MEMORY_IMPL=mock` (default) reads `mocks/memory_context/{case_id}.json`, or an empty list when the file is missing. `MEMORY_IMPL=mubit` calls `memory.mubit.retrieve`, which raises.

To match System 1, Melanie must provide `kind=similar_case`, a non-empty `source_case_id`, and `relevance` ≥ 0.9 when the call is the same household again. Moly treats that as `route=duplicate_merge` inside `decide`. Below 0.9 it is not a duplicate. Moly must copy `kind=correction` summaries into `RouterDecision.policy_notes` (the note prefix is `retrieved correction memory:`).

Minimal duplicate item (this is `mocks/memory_context/F09.json`):

```json
{
  "memory_id": "mem-F09-open-case",
  "kind": "similar_case",
  "summary": "Open case F08 from the same synthetic household: drinking water, Song District, Phrae. Not yet delivered.",
  "relevance": 0.95,
  "source_case_id": "F08"
}
```

Mismatch: `ui/sim/data/town.json` `calls[].memory` is only `kind` and `summary`. It has no `memory_id` or `relevance`, so it is not a `MemoryItem`. The feed placeholder `{memory_count}` uses that array's length, not `case.memory_context`. `tests/test_town_sim.py` locks `buildings[].fixture` (`expected_route`, `expected_priority`, `expected_system`, `location`, `people_count`) and `calls[].opening` to `fixtures/scenarios/`. Those summaries omit `needs`, `medical`, `danger`, and the transcript. The gateway never reads `town.json`.

`memory.adapter.store_record` is not called anywhere in the gateway. Mock mode raises. See 3.6 for what a `MemoryRecord` needs.

### 3.4 One Outcome into the router

Producer of a System 1 outcome: Moly `system1.decide` when the real switch is on, otherwise `mocks/s1_stub/{id}.json` or `_fallback_outcome`. Producer of a System 2 outcome: Melanie `system2.decide`, which today raises before Sapling. Consumer: Moly `router.merge.merge(case, outcome, extra_notes)`.

`Outcome` required: `system` (`system_1` or `system_2`), `outcome` (`fast_route`, `reasoned_recommendation`, or `escalate`), `priority` (`P1`–`P4`), `needs`, `route`, `confidence` (0–1), `reason` (non-empty), `requires_human`, `escalate`. Optional: `reasoning`, `missing_evidence`, `next_question`, `latency_ms`.

`Route`: `rescue_coordination`, `medical_response`, `welfare_distribution`, `shelter_placement`, `aid_caseworker`, `information_only`, `duplicate_merge`, `supervisor_escalation`.

System 1 `decide` order when it runs: System 2 triggers → escalate; else similar-case duplicate → `duplicate_merge`; else needs outside `NEEDS_TABLE` (`water`, `food`, `shelter`, `evacuation`, `power`, `information`) or no needs → escalate; else location confidence under `system_1_min_confidence` (0.80) → escalate; else missing `people_count` → `next_question` `How many people are with you?`; else `fast_route`. `rescue`, `medical`, and `aid_payment` are not in the table. System 1 sets `reasoning` null and does not call Sapling.

The gateway does not call System 2 after System 1 returns `escalate=true`. The chooser already picked one system. `merge` turns `outcome.escalate` into `next_action=escalate_to_supervisor`. That is a human next action, not a second system.

To match the router, Melanie must return one `Outcome` from `system2.decide` with those required fields, `system=system_2`, and `outcome=reasoned_recommendation` when she has reasoned. She must not assume the gateway will call her after a System 1 escalate. Moly must pass that single outcome to `merge` and must not call both systems.

Minimal System 1 outcome:

```json
{
  "system": "system_1",
  "outcome": "fast_route",
  "priority": "P3",
  "needs": ["food"],
  "route": "welfare_distribution",
  "confidence": 0.93,
  "reason": "Clear fast-path request with a confident location.",
  "reasoning": null,
  "missing_evidence": [],
  "next_question": null,
  "requires_human": false,
  "escalate": false,
  "latency_ms": 1
}
```

`merge` next action, first match: `supervisor_escalation` or policy flag `safeguarding` → `escalate_to_supervisor`; `aid_caseworker` → `escalate_to_supervisor`; `escalate` → `escalate_to_supervisor`; `duplicate_merge` → `finalize_case`; any `missing_evidence`, a `next_question`, or no `fields.location` → `ask_next_question`; `information_only` → `finalize_case`; else `create_provisional_dispatch`.

Dispatch fan-out only for that last action, one `Dispatch` per mapped need: `rescue`→`boat`, `medical`→`ambulance`, `water` and `food`→`welfare_point`, `shelter` and `evacuation`→`shelter`. `power`, `information`, and `aid_payment` produce none. Same-district unit wins (district name contained in `fields.location`), else the first available unit, else `status=unfilled` and `resource_id` null. Stock is not decremented. Units come from `mocks/resources.json`.

`Dispatch` required: `need`, `resource_kind` (`boat`, `ambulance`, `shelter`, `welfare_point`), `status` (`provisional` or `unfilled`). Optional: `resource_id`, `same_district` (default false), `note`.

`RouterDecision` required: `case_id`, `next_action`, `final_priority`, `final_route`, `requires_human`, `source_outcomes` (length 1). `policy_notes` and `dispatches` default to empty lists. `NextAction`: `ask_next_question`, `create_provisional_dispatch`, `escalate_to_supervisor`, `finalize_case`, `request_more_evidence`.

`final_priority` and `final_route` copy the outcome. `requires_human` is true when the outcome says so, or the route is `supervisor_escalation` or `aid_caseworker`, or `safeguarding` is in `policy_flags`, or any dispatch is `unfilled`.

### 3.5 RouterDecision to the town phone

Producer: Moly `router.merge`. Consumer: Melanie's phone and feed in `ui/sim/sim.js`.

The phone reads these fields and no others for the reply, the light, and the feed placeholders:

- `final_priority`, `final_route`, `next_action`, `requires_human`
- `source_outcomes[0].system`, `.reason`, `.needs`, `.next_question`
- a `policy_notes` line matching `/selected/` (the trace step "System 1" / "System 2")
- `GET /cases/{id}/trace` stages `gateway` and `router` (`notes`)

`operatorReply` uses `final_priority`, `final_route`, `source_outcomes[0].needs`, `source_outcomes[0].next_question`, and `requires_human`. The vehicle comes from `ui/sim/data/rulebook.json` (`matchRule`), which looks at `final_priority`, `final_route`, outcome `needs`, the typed text, and whether the building's `water_m` is at least 0.25. The rulebook file says it is a draft and not repo policy.

To match the phone, Moly must keep those `RouterDecision` and `Outcome` fields populated on every turn, including stub turns. `source_outcomes` must have one entry. Melanie must keep reading `final_priority` for the house light. She must treat `dispatches` as absent from the picture until she reads them: `sim.js` never reads `dispatches`, `resource_id`, or `resource_kind`.

Minimal decision the phone can render:

```json
{
  "case_id": "F02",
  "next_action": "create_provisional_dispatch",
  "final_priority": "P3",
  "final_route": "welfare_distribution",
  "requires_human": false,
  "source_outcomes": [
    {
      "system": "system_1",
      "outcome": "fast_route",
      "priority": "P3",
      "needs": ["food"],
      "route": "welfare_distribution",
      "confidence": 0.94,
      "reason": "Clear same-day food request.",
      "requires_human": false,
      "escalate": false
    }
  ],
  "policy_notes": ["gateway selected system_1 exclusively"],
  "dispatches": [
    {
      "need": "food",
      "resource_kind": "welfare_point",
      "resource_id": "welfare-fictional-01",
      "status": "provisional",
      "same_district": false
    }
  ]
}
```

Mismatch: the feed's System 1 accept/reject is `sim_events.json` scores plus a page threshold of 0.75 (and pattern memory in `localStorage`). It can say ACCEPTED while `source_outcomes[0].system` is `system_2`, or the reverse. Sapling cards use a simulated `verdict` (`supported`, `violation`, `missing`, `unsure`). The gateway does not add `sapling_verdict` on the stub path. `contradicted` is a real Sapling label and is not one of the simulated card verdicts. There is no `GET /cases/{id}/events` stream. `BaanSafeSim.attachLiveFeed` is the unused hook.

### 3.6 Corrections to memory and to a MemoryRecord

Producer: Moly `ui/correct.js` `buildCorrectionBody`, posted by the town Reject button and by the transcript player. Consumer: Melanie `memory.adapter.store_correction` and `contracts.training.adapt_correction` → `training/log.py`. Endpoint: `POST /cases/{case_id}/corrections`.

`Correction` required: `correction_id`, `case_id`, `corrected_by` (`operator`, `supervisor`, `caseworker`), `field`, `reason`, `created_at`. The API fills `correction_id` and `created_at`. The UI sends `corrected_by=operator`, `field=<task>`, `reason`, `task`, `group_id`, `input_ref`, `output_correct`, `source=human`, `model_version`, and `old_value` / `output_model` when the decision maps to a closed label.

`task`: `s1_triage`, `s2_action`, `sapling_verdict`. `ui/correct.js` `inferTask`: System 2 plus an aid route, `aid_payment`, or flag `aid_eligibility` / `aid_exception` / `aid_denial` → `sapling_verdict`; other System 2 → `s2_action`; otherwise `s1_triage`. `output_correct` must be a closed label for that task (`contracts/training.py` `S1Label`, `S2Action`, `SaplingVerdict`). `S2Action` is the same five strings as `NextAction`.

`InputRef` required: `case_id`, `lang` (`th`, `en`, `mixed`). Optional: `turn_ids`, `policy_ids`, `memory_ref`. The UI sets `turn_ids` to `case_id:index:t_ms`, `memory_ref` to `memory_context[0].memory_id` or null, and `policy_ids` from flags or policy-kind memory ids that match `^[A-Z][A-Z0-9]+(?:-[A-Z0-9]+)+$`.

`TrainingEvent` required: `task`, `group_id`, `input_ref`, `output_correct`, `reason`, `source` (`human`, `coach`, `sim`), `model_version`, `policy_version`. `adapt_correction` fills `policy_version` from the corpus when the body omits it. A v1 body that fails adaptation is HTTP 422. A legacy body without v1 fields still stores a `Correction` and skips the log.

To match the training log, Moly must keep sending `task`, `input_ref`, `output_correct`, `source`, and `reason` as above. Melanie must keep `store_correction` accepting that `Correction`. She must not expect `output_model` for `s1_triage`: `outputModel` returns null unless the task is `s2_action` (the `next_action`) or `sapling_verdict` (a `sapling_verdict=` note). There is no such note on the stub path, so a Sapling correction has no `output_model`.

Minimal body the UI posts (the API adds id and time):

```json
{
  "corrected_by": "operator",
  "field": "s1_triage",
  "new_value": "sphere_food_short",
  "reason": "Food is the need, not a medical case.",
  "task": "s1_triage",
  "group_id": "F02",
  "input_ref": {
    "case_id": "F02",
    "turn_ids": ["F02:0:0"],
    "lang": "en",
    "policy_ids": [],
    "memory_ref": "mem-f02-similar"
  },
  "output_correct": "sphere_food_short",
  "source": "human",
  "model_version": "s1@stub"
}
```

`MemoryRecord` required: `record_id`, `case_id`, `case_summary`, `evidence` (`ExtractedFields`), `decision` (`RouterDecision`). Optional: `outcome_label`, `failure`, `corrections`.

To match a future `store_record`, Moly must provide the `ExtractedFields` he decided from and the `RouterDecision` `merge` returned, plus each `Correction` already stored. Melanie must accept that bundle in `memory.mubit.write`. Nothing in `gateway/` or `api/` builds a `MemoryRecord` today. `store_record` raises in mock mode. A System 1 correction therefore lands as a `Correction` JSONL line and, when v1 fields are present, as a `TrainingEvent`. It does not land inside a `MemoryRecord`.

Minimal record, if she wires the write:

```json
{
  "record_id": "rec-f02-1",
  "case_id": "F02",
  "case_summary": "Same-day food request, Mae Tha District.",
  "evidence": {
    "location": "Mae Tha District, Lampang",
    "location_confidence": 0.93,
    "people_count": 3,
    "needs": ["food"]
  },
  "decision": {
    "case_id": "F02",
    "next_action": "create_provisional_dispatch",
    "final_priority": "P3",
    "final_route": "welfare_distribution",
    "requires_human": false,
    "source_outcomes": [
      {
        "system": "system_1",
        "outcome": "fast_route",
        "priority": "P3",
        "needs": ["food"],
        "route": "welfare_distribution",
        "confidence": 0.93,
        "reason": "Clear fast-path request with a confident location.",
        "requires_human": false,
        "escalate": false
      }
    ]
  },
  "corrections": []
}
```

### 3.7 Aid eligibility and exceptions

Producer: Melanie `system1.aid_eligibility.check(case) -> AidEligibility` and `system2.aid_exceptions.propose(case) -> Outcome`. Consumer: the HTTP stubs. Moly's `gateway/route.py` does not call either function.

`AidEligibility` required: `case_id`. `status` is only `unset` or `needs_human` (default `unset`). Optional `policy_id`, `notes`. The model cannot store an approval.

Endpoints: `GET /aid/eligibility?case_id=` and `POST /aid/exceptions` with a `CaseState`. Both return HTTP 501.

To match the contract, Melanie must return `AidEligibility` with `status` `unset` or `needs_human` and must not add an approved status. Moly must not treat a welfare `RouterDecision` as an aid payment. `aid_payment` is a System 2 trigger and is not a System 1 needs-table row. `policies.authoritative_set` is `TODO_HUMAN`, so Sapling does not treat the corpus as the binding set unless the case names rule ids (`system2/sapling_policy.py`).

### 3.8 System 2 outcome to Sapling, then to the router

Producer: Melanie `system2.orchestrator.orchestrate` then `system2.sapling.verify_before_router`. Consumer: Moly `router.merge`, only after `decide` returns an `Outcome`.

Sapling runs only when `outcome.system` is `system_2`, `system2.use_banyan_sapling` is true, and the check is `aid_eligibility` or `denial` (`system2.sapling_scope`). `supported` leaves the outcome. `violation` sets `requires_human`, `route=supervisor_escalation`, and prefixes the reason. `unsure`, `missing`, and `contradicted` set `requires_human` and append `sapling_<verdict>` to `missing_evidence`. The committed client (`sapling.client=stub`) reads `mocks/sapling_stub/` and does not open a socket. `SAPLING_IMPL=live` raises while `sapling.hosting`, `sapling.gpu`, `sapling.model_id`, or `sapling.thai_handling` is `TODO_HUMAN`.

To match the router, Melanie must return the `Outcome` from `verify_before_router` unchanged in shape. A `violation` or a human handoff has to be visible as `requires_human`, `route`, or `missing_evidence`, because `merge` does not look for a `sapling_verdict` string. Moly must keep mapping `aid_caseworker` and `supervisor_escalation` to `escalate_to_supervisor`, and must keep mapping `missing_evidence` to `ask_next_question` before any dispatch. He must not call Sapling from `system1/decide.py`.

Today this boundary does not run on a request. `orchestrate` raises on `system2.orchestrator_model` and `system2.max_latency_ms` before `llm.complete` and before Sapling. `S2_IMPL=real` surfaces that as HTTP 501.

## 4. Open decisions

These leaves are `TODO_HUMAN` in `config/decisions.yaml`. Decided leaves, not open: `system1.extraction_method` `rules-only`, `gateway.route_chooser` `field precheck`, `system2.hosting` `openrouter via mubit gateway`, `system2.use_banyan_sapling` true, `system2.sapling_scope` `aid_eligibility,denial`, `sapling.client` `stub`, `llm.provider_route` `mubit`.

| Key | Who is blocked |
|---|---|
| `system1.extraction_model` | Nobody on the rules path. A model extractor is blocked. Moly owns that choice. |
| `system2.orchestrator_model` | Melanie. `orchestrate` and `aid_exceptions.propose` raise. `llm.complete` also raises when `model` is empty. |
| `system2.max_latency_ms` | Melanie. Same raise as the model id. The gateway never reaches System 2's real decide. |
| `sapling.hosting`, `sapling.gpu`, `sapling.model_id`, `sapling.thai_handling` | Melanie, only for `SAPLING_IMPL=live`. The stub client does not read them. |
| `gateway.auth` | Moly, for a scheme that can reject a request. Calls are not blocked. |
| `memory.mubit_project`, `memory.retrieval_top_k`, `memory.token_budget` | Melanie. `memory.mubit` raises. Mock retrieval still works. |
| `llm.token_price_usd` | Melanie's cost column. `eval/compare.py` leaves `cost_usd` null. Calls are not blocked. |
| `speech_to_text.provider` | The phone demo. A clip with no browser transcript is not sent. |
| `ui.framework` | Nobody for the static town page. A framework choice is blocked. |
| `data.demo_event` | Anyone claiming the picture is a specific flood. The page stays a placeholder. |
| `data.production_db` | A production database. SQLite remains the store. |
| `correction_loop.graduation_threshold` | Melanie. The correction loop does not promote a rule into System 1. |
| `learning_eval.promotion`, `learning_eval.freeze_mubit_auto_adapters` | Melanie. Eval records the unset value and does not promote. Setting either key without an implementation makes the gate raise. |
| `latte_bench.license_confirmation` | Melanie. Use beyond the reference checkout stays blocked. |
| `sim.caller_model`, `sim.caller_gpu` | Melanie's model caller. The scripted simulator still runs. |
| `policies.authoritative_set` | Melanie. Sapling will not treat the corpus as the binding policy set. Rules still load by id. |
| `modal.s1_gpu`, `modal.s1_model_id`, `modal.s2_gpu`, `modal.s2_model_id`, `modal.nemotron_size`, `modal.s2_quant`, `modal.finetune_gpu`, `modal.finetune_base_model`, `modal.stt_gpu`, `modal.stt_model_id` | Whoever deploys that app. The apps refuse `TODO_HUMAN`. The API process does not need them. |

## 5. Changelog

- 2026-10-24 `1e4ca79` — First PRD. Field precheck, System 1 rules, and `router.merge` are live on the default turn only as described above. System 2, the Sapling client, and Mubit memory remain stubs.
- 2026-10-24 `11e0859` — Extractor covers water at or inside the door, immobility, a child alone, aid refusals, and minimising. Aid and minimising matches are not dropped for a negator. `F15` still hides the child in an operator turn.
