# Template

Copy this directory to `countries/<iso2>/` with the lowercase ISO 3166-1 alpha-2 code. Set `default_demo: false` and leave `runtime: unloaded`.

- `pack.yaml` is locale, hotlines, the triage crosswalk, admin levels, and which provider each capability uses. Comments on the keys say what may be filled. A value with no opened page stays null and `unverified`.
- `policy-pack.yaml` points at Sphere and the IFRC protection standards already loaded from `policies/`. National triage and national aid slots start empty.
- `system1_labels.yaml` is one full sentence per language. That sentence is a System 1 hypothesis and a Laya-style question. `quotation: true` only when the source uses those words.
- `providers.yaml` is the shared fallback list. Do not invent a second endpoint. Cite a row from that file, or leave the national slot null.

Thailand is `countries/th/`, not a second copy of this template. A filled pack does not change `system1/`, `ingest/`, or `policies/` until `countries/REFACTOR_PROPOSAL.md` is implemented.
