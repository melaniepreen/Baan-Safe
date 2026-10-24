# latte-bench (third party, no license)

[MubitLabs/latte-bench](https://github.com/MubitLabs/latte-bench) publishes no license. BaanSafe does not copy its source. The checkout is a git submodule at `third_party/latte-bench`, pinned to `3828bd8c201c272c8eb021608631f2217316ec33`.

`latte_bench.license_confirmation` in `config/decisions.yaml` is `TODO_HUMAN`. Confirm the terms with Mubit before any use beyond this reference.

```bash
git submodule update --init third_party/latte-bench
make latte-bench
```

`make latte-bench` runs the free calibrated reference: `bun install`, then a short runner that imports the checkout and replays the heart witness on the default milk. That path makes no API call and writes `eval/out/latte-reference.json` (gitignored). It exits 0 without doing that work when `bun` is missing or the submodule directory has no `package.json`.

The upstream UI command, from inside the checkout, is:

```bash
bun install
bun run dev
```

Open http://127.0.0.1:3000 and use **Try without an API → Run calibrated reference**. The same UI from the repo root is `make latte-bench LATTE_SERVE=1`. That process strips `MUBIT_API_KEY` so the free server cannot spend a key that happened to be in the environment.

A live server is `make latte-bench LATTE_LIVE=1`. It needs `MUBIT_BASE_URL`, `MUBIT_API_KEY`, `MUBIT_MODEL`, and `FRONTIER_MODEL`. `MUBIT_BASE_URL` may be the gateway root this repo already uses (`https://api.mubit.ai`), which the runner maps to `https://api.mubit.ai/openai/v1`, or a compat prefix such as `https://api.mubit.ai/compat/openrouter/v1`, which is kept. Latte-bench appends `/chat/completions`. Any other host is refused. The key is passed to the child process and is not printed. Optional `FRONTIER_BASE_URL` must also be a `mubit.ai` host.

`make eval-learning` appends **External sanity check: does the model learn from feedback**. That section reads the local reference result when it exists, and `docs/model-study/summary.json` from the pinned checkout (notes versus no notes). Those figures are the benchmark's, and its own write-up says they do not establish learning. They do not change the BaanSafe promotion rule.
