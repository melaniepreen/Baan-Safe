---
title: Data ingest
tags: [ingest, sqlite, json, reliefweb, ddpm, sources]
files:
  - ingest/__main__.py
  - ingest/admin_districts.py
  - ingest/reliefweb.py
  - ingest/db.py
  - ingest/store.py
  - ingest/export.py
  - data/SOURCES.md
  - ingest/demo_sources.py
  - ingest/snapshots.py
---

## Purpose

Pull public flood context into the committed JSON/GeoJSON in `data/processed/` and write `data/SOURCES.md`. `ingest/store.py` is the runtime reader; SQLite is only the `make ingest` build cache at `data/raw/ingest.sqlite`. ReliefWeb is retired. DDPM was not added.

## Key files

- `ingest/__main__.py` — `make ingest`, `make ingest-refresh`.
- `ingest/admin_districts.py` — fills `admin_districts`, the full admin_level=6 gazetteer for the 8 `gistda.province_codes` provinces (one province boundary `out geom` plus one districts bbox query per province; district centre inside the province polygon decides attribution). `districts` is untouched: enrichment, weather, and facilities key to it.
- `ingest/report.py` — `make data-report`.
- `ingest/store.py` — runtime reader of `data/processed/*.json` and `*.geojson`, with an mtime cache.
- `ingest/export.py` — writes the data files from the cache; `seed_db` loads them back for `make ingest --from`.
- `ingest/db.py` — SQLite build cache at `data/raw/ingest.sqlite` (gitignored).
- `ingest/gdacs.py`, `ingest/gistda.py`, `ingest/hdx.py`, `ingest/open_meteo.py`, `ingest/overpass.py`, `ingest/thaiwater.py` — active clients.
- `ingest/reliefweb.py` — `RETIRED`. `ingest()` records status and does not send a request.
- `data/SOURCES.md` — row counts. Raw bodies are gitignored under `data/raw/`.
- `enrich/context.py` — flags for the gateway. Not a priority. Matches `districts` first, then `admin_districts` for points and flags.
- `ingest/demo_sources.py` — live checks for the fixture provinces, with committed snapshots. See `docs/agents/data-sources.md`. `make sources-status` sends no request.

## Interfaces/contracts

- `make ingest` uses the cache. `make ingest-refresh` ignores it.
- ReliefWeb status text is the `RETIRED` string: robots.txt on `api.reliefweb.int` disallows `/v2/`, and the API wants a pre-approved appname.
- `GET /map/flood`, `GET /map/facilities`, and `GET /context` read the committed files (`api/routes/endpoints.py`, `ingest/store.py`).
- Runtime never opens SQLite. Gateway, enrich, extract, and the API use `ingest.store` (`store.available()` / JSON). `BAANSAFE_DB_PATH` only redirects the ingest build cache; Modal does not set it.

## Invariants

- Do not fetch ReliefWeb. Do not bypass robots.txt.
- Do not add DDPM situation reports or scrape `disaster.go.th`. The owner left DDPM out. `data/SOURCES.md` says so.
- Do not hardcode a relief-payment amount from an old flood.
- Production database is `data.production_db` (`TODO_HUMAN`). Committed JSON is the overnight store; SQLite is a gitignored build cache. Do not commit `*.sqlite`.
- Synthetic people only. Ingest text is scanned for phones, 13-digit ids, and the banned words in `scripts/validate.py`.

## How to test

- `make validate` — `check_data` (files exist, summary length, no `body` key) and the personal-data scan.
- `tests/test_robots.py` — ReliefWeb stays retired.
- `tests/test_enrich.py` — flags, not priorities.
- `make data-report` rewrites `data/SOURCES.md` from the data files. Do not hand-edit counts you did not regenerate.

## Common pitfalls

- Re-enabling `ingest/reliefweb.py` with an HTTP call. The module's job is to refuse.
- Treating research notes (`research/thai-flood-management.md`) as permission to scrape DDPM. They describe agencies. They are not a client.
- Committing `data/raw/` or a filled `.env` (`GISTDA_API_KEY`, `RELIEFWEB_APPNAME`).

## Open TODO_HUMAN keys

- `data.demo_event`
- `data.production_db`
