# Adding a country

Until `countries/REFACTOR_PROPOSAL.md` is implemented, stop after the pack exists on disk. A new directory under `countries/` changes nothing at runtime. Do not edit `system1/`, `ingest/`, `policies/`, `config/`, `contracts/`, `router/`, `ui/`, `tests/`, or `frontend-prototype/` in the same change.

People are synthetic. No subscriber numbers, no national ids, no PromptPay, no bank accounts, no secrets. Do not fetch ReliefWeb. Do not add DDPM, `disaster.go.th`, or `ddpm.go.th` as a source. A short public code may cite an official page. That citation is not an ingest client.

## 1. Read

- `countries/README.md`
- `countries/THAILAND_ASSUMPTIONS.md` — what not to copy: `admin_level` 6 with `ISO3166-2=TH-`, `+66`, 13-digit ids, `Asia/Bangkok`, GISTDA, ThaiWater, baht, the NIEMS colours as if they were P1–P4
- `countries/TEMPLATE/providers.yaml` — the only fallback URLs
- `countries/ph/` — a flood country with the national slots left empty

## 2. Copy the template

Copy `countries/TEMPLATE/` to `countries/<iso2>/`. `<iso2>` is lowercase ISO 3166-1 alpha-2. Set `iso2`, `iso3`, `default_demo: false`, `runtime: unloaded`. Do not recreate `countries/th`.

## 3. Locale

Fill timezone (IANA), currency (ISO 4217), and the phone description only from a page you opened. `status: verified` needs that URL and the day. Otherwise leave the value null and `unverified`.

Do not reuse the Thai `+66` / leading-zero scanner or the 13-digit id rule as if they were universal. `scripts/validate.py:28` stays the Thai check until the refactor adds a pattern beside it.

`rain` stays millimetres. That is what Open-Meteo and `config/escalation.yaml` count.

## 4. Hotlines

One object per service: medical, fire, police, disaster, other.

1. Open a government page or the national numbering list. A blog or a memory of a number is not a `source_url`.
2. Copy the digits into `number` as a string. Set `retrieved`. Quote `name` as the page prints the agency.
3. If two official pages use the same digits and a different scope, keep both notes. Do not pick a winner. Thailand's 199 is that case.
4. If you did not open the page, `number: null` and `status: unverified`. Do not copy an office trunk. The Philippines pack leaves NDRRMC trunks null for that reason.
5. `wired: false`. The router does not dial.

## 5. Triage and aid

1. Retrieve the national scale and the assistance instrument. `source_excerpt` comes from that page only.
2. Map a level onto P1–P4 only with `mapping_status: unverified`, unless the document itself names those priorities. `system1/decide.py` does not read colours.
3. Point the baseline at `policies/sphere.yaml` and `policies/safeguarding.yaml`. Do not paste the handbooks. The Sphere PDF returned HTTP 403; the wording already in the corpus was read from the archive capture named in `TEMPLATE/policy-pack.yaml`.
4. Leave the aid slot empty rather than invent a ceiling. Do not repair a damaged digit into an amount. Do not convert a local era into a Gregorian date unless both are printed.
5. `policies/flood.yaml` holds international depth figures. None of them is a 1669 colour. Do not copy 6, 12, or 18 inches into another country as its rule.
6. `system1/aid_eligibility.py` does not approve a payment.

## 6. Admin levels

Read the OSM wiki page for that country and the HDX COD-AB dataset page. Record `osm_admin_level` separately from the COD-AB level. Pick `gazetteer.grain`. Do not assume Thailand's level 6. A matching integer in another country is not the same unit. The Philippines note in `docs/agents/country-packs.md` says level 6 there is a city or municipality.

## 7. Providers

For each capability in `countries/PROVIDERS.md`, either cite a national endpoint you opened or set `national: null` and name a global fallback id from `TEMPLATE/providers.yaml`. A product page is not an API path. A forecast is not an extent. GDACS for a new country does not reuse `country=THA` or August–December 2025 (`ingest/gdacs.py:25`).

## 8. Labels

Write one hypothesis sentence per language in `system1_labels.yaml`. They are full sentences a zero-shot model, including Laya, can score one at a time. They are not priorities. Mark drafts `quotation: false`. Do not translate a statute you did not read. An empty sentence is not scored.

## 9. Tests, later

Do not add them until a loader exists. A test that imports a pack will fail while `runtime` is `unloaded`.

When the refactor lands, add:

- The loader returns Thailand when no country is set, and extract on the existing fixtures matches today's output.
- An unknown `iso2` raises and names the code.
- A hotline with `status: unverified` is not copied into a dispatch.
- `admin_level` 6 for `ph` is not queried with `ISO3166-2=TH-`.
- The personal-data scan still rejects a Thai-shaped number, and it also rejects the new country's pattern.
- `policies/corpus.py` still refuses a ReliefWeb or DDPM URL.
- `make test` and `make validate` stay green.

## 10. Check a pack-only change

```bash
python3 -c '
import yaml
from pathlib import Path
root = Path("countries")
files = sorted(root.rglob("*.yaml"))
assert files, "no country yaml"
for path in files:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path} is not a mapping")
    print(f"ok {path}")
'
make validate
```

`make validate` does not parse `countries/`. It does check `docs/agents/country-packs.md`. Push straight to `main`. Do not open a pull request.
