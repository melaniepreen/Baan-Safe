# Country packs

BaanSafe runs as a Thailand demo. This folder describes how another country would plug in. Nothing here is imported. `runtime` stays `unloaded`.

The schema is `baansafe.country_pack.v0`. Copy `TEMPLATE/` to `countries/<iso2>/`.

| Path | Role |
|---|---|
| `THAILAND_ASSUMPTIONS.md` | 49 assumptions the running tree encodes, with `file:line`. |
| `PROVIDERS.md` | Capability interface. Retrieved URLs are in `TEMPLATE/providers.yaml`. |
| `TEMPLATE/pack.yaml` | Commented pack. |
| `TEMPLATE/policy-pack.yaml` | Sphere and IFRC baseline, empty national slots. |
| `TEMPLATE/system1_labels.yaml` | One hypothesis sentence per language. |
| `TEMPLATE/providers.yaml` | Global fallbacks, each with a page that was opened. |
| `th/pack.yaml` | Today's Thailand. `default_demo: true`. |
| `ph/` | Philippines example. National cuts and aid amounts are empty on purpose. |
| `AGENT_INSTRUCTIONS.md` | Checklist for adding a country. |
| `REFACTOR_PROPOSAL.md` | Later code changes. Post-hackathon. Not this tree. |

The agent index summarises the same inventory in `docs/agents/country-packs.md`. That file is the indexed topic. This folder is the pack.

Hotlines, endpoints, and policy sentences are `verified` only with the URL they were read from. A missing number stays null. ReliefWeb is not a provider. DDPM is not a source. People stay synthetic.
