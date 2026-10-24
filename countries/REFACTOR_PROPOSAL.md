# Refactor proposal

Post-hackathon. This is not a diff. `runtime: unloaded` stays until a human accepts this list and a later change implements it. Thailand remains the default path. Existing fixtures keep their labels. Do not do this in a docs-only change.

No decision in `config/decisions.yaml` moves. `sapling.thai_handling`, `speech_to_text.provider`, `modal.stt_model_id`, `data.demo_event`, and `policies.authoritative_set` stay `TODO_HUMAN`. A pack must not fill them.

Out of scope: a second model host (`llm/client.py` refuses anything but Mubit), a ReliefWeb client, a DDPM client, and `frontend-prototype/`.

## Top five

Do these before any other country can affect a call. After each one, the Thai fixtures still match today's labels.

### 1. No country on the request path

Effort: small for a dormant loader, medium to thread it through the gateway. Risk: medium on the hot path, high if a contract field is required.

- `config/settings.py:20` reads only `config/<name>`.
- `gateway/route.py:201` calls `extract` with the transcript and no country.
- `contracts/models.py:203` has a district label and no country field.

Later: an optional country code, default `th`, and a loader that nothing calls until a later step. Leave the field off the contract until a human accepts a schema change.

### 2. Extractor, language, and gazetteer

Effort: medium. Risk: high. Fixture labels move if a phrase shifts.

- `system1/extract.py:20` keeps Latin tokens.
- `system1/extract.py:279` reads `admin_districts`.
- `system1/extract.py:337` builds `Name, Province`.

A pack-driven phrase list has to reproduce today's English table on the current fixtures before it accepts another language.

### 3. Ingest providers, clock, and admin level

Effort: large. Risk: high. These clients write SQLite and honour robots rules.

- `ingest/open_meteo.py:26` — `Asia/Bangkok`
- `ingest/gistda.py:22` — GISTDA
- `ingest/thaiwater.py:21` — ThaiWater public JSON
- `ingest/gdacs.py:25` — `country=THA`
- `ingest/hdx.py:86` — `thailand flood`
- `ingest/admin_districts.py:51` — `TH-{code}` and `admin_level` 6
- `config/ingest.yaml:42` — eight province codes

A registry calls today's functions for `th` and refuses a national URL whose pack status is `unverified`. A missing national provider may name a fallback from `countries/TEMPLATE/providers.yaml`. It does not invent a path. No ReliefWeb. No DDPM.

### 4. Policy jurisdiction, languages, and the file list

Effort: medium. Risk: high. The corpus hash is the file bytes.

- `policies/schema.py:8` allows only `TH` and `intl`.
- `policies/schema.py:9` allows only `en` and `th`.
- `policies/sources/local_yaml.py:35` maps jurisdiction by filename.
- `policies/corpus.py:20` lists five files, including `flood.yaml`.

Add a country by a new adapter pointed at `countries/<iso2>/policy-pack.yaml`. Do not move the Thailand YAML. Do not widen `contracts/training.py` `Lang` in the same change. That literal is `th`, `en`, or `mixed`. A pack may name another language before the contract allows it. The API should reject that code until a contract note says otherwise.

### 5. Personal-data scanners

Effort: small. Risk: medium. A looser pattern lets a real number through. A narrower one misses a Thai number.

- `scripts/validate.py:28` and `ingest/textutil.py:9` know `+66` and a leading `0`.
- `scripts/validate.py:29` treats 13 digits as an id.

A new pattern is added beside the Thai one, not instead of it. Patterns reject. They do not store the match. `contracts/models.py` `Person` does not grow a phone field.

## Later, still post-hackathon

Only after the five above keep the Thai fixtures green.

- Speech default. `infra/modal/stt_app.py:62` posts `language=th`. Read the pack language only when the request omitted one. Risk stays low if the default remains `th`. `modal.stt_model_id` stays `TODO_HUMAN`.
- Sapling language gate. `system2/sapling_client.py:199` refuses non-English. Do not send another language until `sapling.thai_handling` is decided. Removing the gate is high risk.
- Router district match. `router/merge.py:144` uses a substring of the location string, and `router/merge.py:27` sends rescue to a boat. Boats are a resource kind for this flood demo, not a national rule.
- Enrichment thresholds. `config/escalation.yaml:32` flags 30 mm in 24 hours for every caller. A pack may name a different flag later. It must not change the Thai flag in the same change.

## What not to change

- `memory/adapter.py` has no locale.
- `llm/client.py` stays Mubit-only.
- `gateway/chooser.py` and the clinical triggers in `config/escalation.yaml` do not grow a country branch. A national colour becomes a trigger only when a sourced rule says so, and then as data, not as a one-country `if`.
- `config/routing.yaml` stays exclusive System 1 or System 2.
- `system1/aid_eligibility.py` keeps raising. A table of ceilings is not an approval.

## Acceptance

- Default pack `th` reproduces today's extract output, today's ingest URLs, and today's policy jurisdiction.
- `make test` and `make validate` pass.
- Unverified hotlines are not dialed. Unverified rules are not authority.
- No secret in the pack. No ReliefWeb request. No DDPM client.
