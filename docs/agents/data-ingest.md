---
title: Data ingest
tags: [ingest, sqlite, reliefweb, ddpm, sources]
files:
  - ingest/__main__.py
  - ingest/reliefweb.py
  - ingest/db.py
  - data/SOURCES.md
---

## Purpose

Pull public flood context into SQLite and write `data/SOURCES.md`. ReliefWeb is retired. DDPM was not added.

## Key files

- `ingest/__main__.py` — `make ingest`, `make ingest-refresh`.
- `ingest/report.py` — `make data-report`.
- `ingest/db.py` — `data/processed/baansafe.sqlite`.
- `ingest/gdacs.py`, `ingest/gistda.py`, `ingest/hdx.py`, `ingest/open_meteo.py`, `ingest/overpass.py`, `ingest/thaiwater.py` — active clients.
- `ingest/reliefweb.py` — `RETIRED`. `ingest()` records status and does not send a request.
- `data/SOURCES.md` — row counts. Raw bodies are gitignored under `data/raw/`.
- `enrich/context.py` — flags for the gateway. Not a priority.

## Interfaces/contracts

- `make ingest` uses the cache. `make ingest-refresh` ignores it.
- ReliefWeb status text is the `RETIRED` string: robots.txt on `api.reliefweb.int` disallows `/v2/`, and the API wants a pre-approved appname.
- `GET /map/flood`, `GET /map/facilities`, and `GET /context` read the processed DB (`api/routes/endpoints.py`).

## Invariants

- Do not fetch ReliefWeb. Do not bypass robots.txt.
- Do not add DDPM situation reports or scrape `disaster.go.th`. The owner left DDPM out. `data/SOURCES.md` says so.
- Do not hardcode a relief-payment amount from an old flood.
- Production database is `data.production_db` (`TODO_HUMAN`). SQLite is the overnight store.
- Synthetic people only. Ingest text is scanned for phones, 13-digit ids, and the banned words in `scripts/validate.py`.

## How to test

- `make validate` — `check_database` and the personal-data scan.
- `tests/test_robots.py` — ReliefWeb stays retired.
- `tests/test_enrich.py` — flags, not priorities.
- `make data-report` rewrites `data/SOURCES.md` from the DB. Do not hand-edit counts you did not regenerate.

## Common pitfalls

- Re-enabling `ingest/reliefweb.py` with an HTTP call. The module's job is to refuse.
- Treating research notes (`research/thai-flood-management.md`) as permission to scrape DDPM. They describe agencies. They are not a client.
- Committing `data/raw/` or a filled `.env` (`GISTDA_API_KEY`, `RELIEFWEB_APPNAME`).

## Open TODO_HUMAN keys

- `data.demo_event`
- `data.production_db`
