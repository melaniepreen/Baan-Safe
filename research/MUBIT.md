# Mubit, from the public docs

Notes for Saturday. This is a reading of the public site, not a client. The repo does not call Mubit unless `MUBIT_API_KEY` and `MUBIT_BASE_URL` are set, and `llm/client.py` still refuses while `llm.provider_route` is `TODO_HUMAN`. Nothing here picks a model or a project id.

The docs are enough to stand up a gateway and a memory client. They are thin on the thing the hackathon demo has to show: a correction becoming a weight update. That gap is called out at the end.

## What the product says it is

Mubit is an API gateway in front of model providers, plus a memory layer. The getting-started and quickstart pages are the two entry points.

- https://docs.mubit.ai/getting-started
- https://docs.mubit.ai/quickstart

The gateway idea matches the revised architecture: the app talks to Mubit, and Mubit talks to the model. Mubit is not the reasoner. In this repo that reasoner, when a human picks one, is the System 2 orchestrator.

## Calling a model

The OpenAI-compatible prefix is `https://api.mubit.ai/openai/v1`. The same host also documents Anthropic, Gemini, and a generic compat prefix.

- https://docs.mubit.ai/guides/connect-openai
- https://docs.mubit.ai/reference/api

The reference describes prefixes `/openai/v1`, `/anthropic`, `/gemini`, and `/compat/{service}/v1`. Keys are minted in the console and start with `mbt_`. Provider keys stay in the console. The docs say to call from a server: the API does not offer browser CORS. `llm/client.py` only posts to `{MUBIT_BASE_URL}/openai/v1/chat/completions`, and only when the host is `api.mubit.ai` or a subdomain of `mubit.ai`.

The docs name example model ids, including ids that look like current closed models. Those names are examples on a docs page. They are not a choice for BaanSafe. `system2.orchestrator_model` stays `TODO_HUMAN`. Options are in `research/MODELS.md`.

## SDK configuration

- https://docs.mubit.ai/sdk/sdk-configuration

The environment variables described there:

| Variable | Role |
|---|---|
| `MUBIT_API_KEY` | Required. Not printed by this repo. |
| `MUBIT_ENDPOINT` | Default `https://api.mubit.ai`. This repo's switch is `MUBIT_BASE_URL`, same idea. |
| `MUBIT_TRANSPORT` | `auto`, `http`, or `grpc`. |
| `MUBIT_GRPC_ENDPOINT` | `grpc.api.mubit.ai:443` when gRPC is used. |

We have not wired the SDK. The HTTP client above is the only model path, and it is still closed by the unset decision.

## Memory and the control API

SDK methods are documented as remember, recall, reflect, get_context, and record_outcome.

- https://docs.mubit.ai/sdk/sdk-methods

The control HTTP surface, which is the closer match to a memory write from our gateway, is listed as POST endpoints under `/v2/control/`: ingest, batch_insert, query, context, activity, activity/export, archive, dereference, diagnose, memory_health, reflect, and lessons.

- https://docs.mubit.ai/api-reference/control-http

`memory/mubit.py` does not call any of these. It raises, names the unset `memory.*` decisions, and says so when `MUBIT_API_KEY` is missing. `memory/adapter.py` is the switch: `MEMORY_IMPL=mock` reads the fixture files, `MEMORY_IMPL=mubit` hits that raising client. The gateway is the only retrieval caller.

## Learning loop versus a model update

Two different mechanisms show up in the docs, and they are easy to mix up.

The learning loop is memory, not training. The concept page describes a cycle of experience, attribution, distillation, injection, and promotion. A later call can see a lesson. The weights do not change.

- https://docs.mubit.ai/concepts/learning-loop

Adapters are the closer public story to "the model changed". Requests are grouped into tasks. Kept examples train an adapter version. The docs list result states along the lines of Passed, Below target, Malformed tool calls, Prompt only, and Not tested.

- https://docs.mubit.ai/concepts
- https://docs.mubit.ai/guides/first-adapter

## Where the docs are thin

I could not find a public HTTP call that means "take this human correction and start a LoRA or SFT job, then register the new weights". The public mechanisms are: store the episode in memory, and, separately, keep examples so an adapter version can be trained. The wire format of that training job, the dataset schema, and how a new version is addressed at inference are not spelled out on the pages above.

That is why `make demo-correction-loop` is a stub. It stores a synthetic correction, writes a JSONL file in the messages shape used for SFT and LoRA, records a training job with status `stub`, and registers `stub-1`. It does not claim to have called either the learning loop or the adapter trainer. Replacing the stub means a human reads the adapter guide against a live project and decides whether the demo's "model update" is an adapter version, a fine-tune, or only a memory promotion. `memory.mubit_project` is still `TODO_HUMAN`.

## Hackathon rule

The Night Shift event requires every LLM call to go through Mubit. The event page is https://luma.com/nightshift-london. The judging line that matters for this file: the demo has to show a correction turning into a model update. Usefulness, technical execution, and the live demo are the other three, at equal weight. Tracks are options in `research/DEMO_PLAN.md`.
