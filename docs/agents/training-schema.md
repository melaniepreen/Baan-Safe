# Training schema

- Owner: Agent A (CONTRACT)
- Status: landed (schema v1)
- Spec: shared training schema v1. Import `contracts/training.py`. Do not redefine these types.

## Purpose

Corrections, coach notes, and simulator outcomes are one append-only event log. Per-model training files are exported from that log by later agents. Ontology, the gateway, S1/S2 routing, the Decision Router, the policies API, and the Mubit-only rule are unchanged. Decisions in `config/decisions.yaml` stay `TODO_HUMAN`.

Callers import `TrainingEvent`, `InputRef`, `S1Label`, `S2Action`, and `SaplingVerdict` from `contracts.training`. The log writer is `training.log.append_event`.

## Contract

`TrainingEvent` is one JSON object, Pydantic v2, `extra=forbid`. `schema_version` is `1`.

| Field | Rule |
|---|---|
| `schema_version` | `1` |
| `event_id` | UUID string. The model fills one when the caller omits it. |
| `created_at` | Timezone-aware UTC. A naive datetime is read as UTC. |
| `task` | `s1_triage`, `s2_action`, or `sapling_verdict` |
| `group_id` | Same call across Thai, English, and paraphrases. Splits use this, not the row id. |
| `input_ref` | `case_id`, `turn_ids`, `lang` (`th`, `en`, or `mixed`), `policy_ids`, `memory_ref` (string or null) |
| `output_model` | Closed label for `task`, or null |
| `output_correct` | Closed label for `task` |
| `reason` | Non-empty string |
| `source` | `human`, `coach`, or `sim` |
| `corrected_by` | `operator`, `supervisor`, or `caseworker`. Required when `source` is `human`. |
| `weight` | Float, default human `1.0`, coach `0.5`, sim `0.25`. An explicit value wins. Then a table passed to `adapt_correction`. Then `TRAINING_WEIGHT_HUMAN`, `TRAINING_WEIGHT_COACH`, or `TRAINING_WEIGHT_SIM`. |
| `model_version` | Non-empty string, for example `s1@v3` |
| `policy_version` | Policies API corpus version (the pin hash) |
| `content_hash` | SHA-256 hex of `task` + `input_ref` + `output_correct`. The model fills it. A caller-supplied hash that does not match is rejected. |

Closed enums, in `contracts/training.py`:

- `s1_triage`: `S1Label`. The member values are the policies API label ids (`PolicyService.labels`).
- `s2_action`: `S2Action`. The member values are `RouterDecision.next_action` (`NextAction`).
- `sapling_verdict`: `SaplingVerdict`. `supported`, `violation`, `missing`, `contradicted`, `unsure`. This enum is the label. `system2.sapling_client.SaplingVerdict` is the runtime result and is a different type.

`content_hash_for(task, input_ref, output_correct)` is the only hash. It is the SHA-256 hex digest of UTF-8 JSON `{"task", "input_ref", "output_correct"}` with sorted keys and separators `(",", ":")`. `input_ref` is the `InputRef` JSON object. `output_correct` is the label string. Weight, reason, source, and event id are not part of the hash.

`Correction` keeps its original fields. v1 adds optional `schema_version`, `task`, `group_id`, `turn_ids`, `lang`, `policy_ids`, `memory_ref`, `output_model`, `output_correct`, `source`, `weight`, `model_version`, and `policy_version`. A row without those fields still validates.

## Files

| Path | What it owns |
|---|---|
| `contracts/training.py` | `TrainingEvent`, closed enums, `content_hash_for`, `adapt_correction` |
| `contracts/models.py` | `Correction` v1 fields. The memory shape. |
| `contracts/schemas/` | JSON Schemas exported from the models, including the training types. |
| `training/log.py` | Append-only log. Dedup on `content_hash`. No edit and no delete. |
| `training/events/events.jsonl` | Default log file. `TRAINING_EVENTS_PATH` overrides it. Runtime lines are gitignored. |
| `api/routes/endpoints.py` | `CorrectionIn` accepts the legacy body and the v1 fields, then the adapter. |
| `eval/correction_loop.py` | Writes one event through the adapter and the log. `corrections.jsonl` and `sft.jsonl` are still written. |

## Behaviour

`adapt_correction` copies a `Correction` into a `TrainingEvent`. `source` defaults to `human`. The task is the v1 `task` field, or it is inferred from `field`:

| `field` | task |
|---|---|
| `s1_triage`, `s1`, `s1_label`, `label`, `triage`, `priority`, `route` | `s1_triage` |
| `s2_action`, `s2`, `action`, `next_action` | `s2_action` |
| `sapling_verdict`, `sapling`, `verdict` | `sapling_verdict` |

`output_correct` is the v1 field when it is set, otherwise `new_value`. `output_model` is the v1 field when it is set. A legacy `old_value` is kept only when it is already a closed label. `group_id` defaults to `case_id`. `lang` defaults to `en`. `model_version` defaults to `legacy@unversioned`. `policy_version` defaults to the current policies API pin.

A priority or a route is not a closed label. `adapt_correction` raises `AdaptError` for those legacy rows. They stay on `corrections.jsonl` and are not invented into a label. `POST /cases/{case_id}/corrections` still stores that memory correction and returns 200. If the body set any v1 field and the adapter raises, the route returns 422 and writes nothing.

`training.log.append_event` opens the log for append under an exclusive lock. It does not rewrite earlier lines. When `content_hash` is already present, the new line is skipped and `AppendResult.written` is false. `read_events` validates every line as a `TrainingEvent`.

`eval/correction_loop.py` still stores the synthetic route correction and still writes `sft.jsonl`. It also appends one `s1_triage` event for case `CORR-LOOP-1`: `output_model` is null, `output_correct` is `sphere_water_short`, `source` is `human`, `model_version` is `s1@stub-0`. The route names `information_only` and `welfare_distribution` are not s1 labels, so they stay on the memory row.

Exporters (later) read this log. They dedup on `content_hash` as well. They do not edit the log. Export shapes, when they land, are: s1 `{text, label, group_id, weight}`, s2 chat messages to an action plus a short reason, sapling `{policy, evidence, claim, verdict}`, and prefs `{prompt, chosen, rejected}` where `output_model` is not `output_correct`. Each export writes a manifest with `schema_version`, event count, `policy_version`, and a hash.

## Proposed changes

No open proposals. An agent who needs a schema change adds it below and does not edit `contracts/training.py` or `contracts/models.py`.

- id:
- model:
- proposed change:
- why:
- from:
- status: open
