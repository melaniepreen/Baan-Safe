# Frontend prototypes

Static HTML. Nothing here calls the API. Every baht figure, dollar cost, water level, and caller is simulated. Fixture ids and the ingest counts in the footers are the ones already in the repo.

Open `index.html` for the gallery.

| Folder | Reference | What you should notice |
|---|---|---|
| `v0-dark/` | Earlier dark console, kept as given | Near-black, violet Mubit, green System 1, amber System 2 |
| `v1/` | [HyperAktiv](https://styles.refero.design/style/d19c6fc3-1fc6-44a0-9c22-a0a82f7f79b4) — Swiss editorial broadsheet. White canvas, black rules, electric blue `#0000ff` as the only colour, sharp corners | Numbered sections. Ontology, shape legend, and the animated loop, with blue only on the live mark |
| `v2/` | [Vercel](https://styles.refero.design/style/f24daf3a-d43f-4dec-85a9-8ac1d5148a03) — typeset terminal on white paper. `#fafafa`, hairline `#eaeaea`, black accent, 6px radius, no decorative colour | The same diagrams in a product notebook: hairlines, chips, monospace metadata |
| `v3/` | [Stripe](https://styles.refero.design/style/48e5de76-05d5-4c4e-a269-c7c245b291ec) — indigo ledger on a cool wash. Navy type at a light weight, `#533afd`, cards on `#f6f9fc`, depth from tint not shadow | The same diagrams on white cards. Indigo only on the live mark |
| `v4/` | [Operate](https://styles.refero.design/style/f682f0ea-632d-4d09-bfdf-6a43f5e5a7d8) — botanist’s data terminal, used here as a light Bloomberg-style instrument. Sage paper, forest type, mint `#0b7a32`, compact tables | The allocation matrix is the whole top of the screen |
| `v5/` | [Ventriloc](https://styles.refero.design/style/f99aca3e-5289-4595-a7cc-77a72052f4b8) — editorial data observatory on warm paper, one orange ember | A relief desk: ivory ground, a short lede, orange rules |

v1, v2, and v3 were iterated in place. Each keeps its reference style and adds the same three diagrams: an interactive ontology taken from `contracts/models.py`, one shape legend (circle people and cases, square resources, triangle hazards, diamond decisions and policy, hexagon Mubit), and an end-to-end flow with moving tokens. The dashed return re-enters System 1 and System 2 and is not promoted. v4 and v5 are unchanged.

Each light variation shows the same simulated machine, arranged differently:

- Mubit gateway: auth (scheme still `TODO_HUMAN`, request not rejected), memory hits, policy flag, exclusive route, audit line.
- System 1 is deterministic and spends no tokens. System 2 is the Nemotron orchestrator stub, with plan / tools / outcome spans. Only one of them runs.
- Decision router returns one next action. `merge()` is not called.
- Budgets: simulated Thai central fund, DDPM reserve, Lampang, Phrae, Nan, and Phayao envelopes, plus NGO, public, and corporate donations. The solver moves money across shelter, boats, medical, food, and cash. It stops on budget caps, the simulated ฿9,000 household rule, eligibility unset (the F17/F18 pattern), boat and crew caps, closed roads, and time-to-reach.
- Relearning runs on a timer: operator correction, memory write, JSONL row, LoRA job stub, version `stub-N`, replay of accuracy, latency, and cost. Every fourth version drifts. The 0.90 line is a demo mark. `graduation_threshold` stays `TODO_HUMAN` and nothing is promoted into System 1.
- Traces are waterfalls with a trace id, milliseconds per span, tokens, a simulated cost, the policy decision, memory hits, and the model version on that call.

Screenshots at 1440×900 are `v1/screenshot.png` through `v5/screenshot.png`, plus `v0-dark/screenshot.png`.
