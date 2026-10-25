import { S2_LABEL, hostingLabel, memoryDormant, memoryMode, system2Mode } from "./hosting_banner.js";

function assert(cond, message) {
  if (!cond) throw new Error(message);
}

// Shapes follow infra/modal/gateway_app.py hosting() and api/routes/endpoints.py health().
const hostedCache = {
  app: "baansafe-gateway",
  backends: "cache",
  secrets: true,
  memory: "local",
  impl: { S1_IMPL: "real", S2_IMPL: "cache", MEMORY_IMPL: "local", SAPLING_IMPL: "stub", ENRICH_IMPL: "data" },
  writes: {},
  reads: {},
  note: "LLM via Mubit only.",
};
const healthLocal = {
  status: "ok",
  impl: { S1_IMPL: "real", S2_IMPL: "cache", MEMORY_IMPL: "local", ENRICH_IMPL: "data" },
  data_freshness: {},
  memory: { mode: "local", dormant: false, warning: null },
};

const cache = hostingLabel(hostedCache, healthLocal);
assert(cache.tone === "cache", "cache deploy wears the cache tone: " + cache.tone);
assert(cache.text === "System 2: cache (replays, Mubit on miss) · Memory: local · Mubit credentials: yes", cache.text);
assert(cache.parts.length === 3 && cache.warning === null && cache.source === "/hosting", JSON.stringify(cache));

const live = hostingLabel({ ...hostedCache, backends: "live", impl: { ...hostedCache.impl, S2_IMPL: "real" } }, healthLocal);
assert(live.tone === "live" && live.parts[0] === "System 2: " + S2_LABEL.real, JSON.stringify(live));

const stub = hostingLabel({ ...hostedCache, backends: "stub", secrets: false, impl: { ...hostedCache.impl, S1_IMPL: "stub", S2_IMPL: "stub" } }, null);
assert(stub.tone === "muted" && stub.parts[0] === "System 2: stub" && stub.parts[2] === "Mubit credentials: no", JSON.stringify(stub));

// S2_IMPL missing from impl: fall back to the backends word.
assert(system2Mode({ backends: "live" }, null) === "real", "backends live → real");
assert(system2Mode({ backends: "s1-real" }, null) === "stub", "backends s1-real → S2 stub");
assert(system2Mode({ backends: "cache", impl: {} }, null) === "cache", "backends cache → cache");
assert(system2Mode({}, null) === null, "nothing known → null");

// Dormant memory: MEMORY_IMPL=mubit on /hosting, or dormant on /health, is red and keeps the warning text.
const warning = "MEMORY_IMPL=mubit is dormant: current Mubit is an LLM gateway with no memory API. Set MEMORY_IMPL=local.";
const dormantHealth = { ...healthLocal, impl: { ...healthLocal.impl, MEMORY_IMPL: "mubit" }, memory: { mode: "mubit", dormant: true, warning } };
const dormant = hostingLabel({ ...hostedCache, memory: "mubit", impl: { ...hostedCache.impl, MEMORY_IMPL: "mubit" } }, dormantHealth);
assert(dormant.tone === "error", "dormant memory is red");
assert(dormant.parts[1] === "Memory: mubit (dormant!)", dormant.parts[1]);
assert(dormant.warning === warning && dormant.text.endsWith(" — " + warning), dormant.text);
assert(memoryDormant({ impl: { MEMORY_IMPL: "mubit" } }, null) === true, "hosting alone can flag dormant");
assert(memoryDormant(null, { memory: { mode: "mubit", dormant: true } }) === true, "health alone can flag dormant");
assert(memoryDormant(hostedCache, healthLocal) === false, "local memory is not dormant");
const dormantNoText = hostingLabel({ ...hostedCache, impl: { ...hostedCache.impl, MEMORY_IMPL: "mubit" } }, null);
assert(dormantNoText.tone === "error" && dormantNoText.warning.includes("MEMORY_IMPL=local"), "a fallback warning names the fix");

// Local `make serve`: /hosting 404s, /health answers. Credentials are unknown there.
const healthOnly = hostingLabel(null, healthLocal);
assert(healthOnly.source === "/health" && healthOnly.tone === "cache", JSON.stringify(healthOnly));
assert(healthOnly.parts[2] === "Mubit credentials: unknown", healthOnly.parts[2]);
assert(memoryMode(null, { memory: { mode: "mock" } }) === "mock", "health memory.mode is the last resort");
assert(hostingLabel(null, { ...healthLocal, impl: { S2_IMPL: "real", MEMORY_IMPL: "mock" } }).text === "System 2: live via Mubit · Memory: mock · Mubit credentials: unknown", "health-only live");

// Neither endpoint answered (python -m http.server): quiet, not red.
const offline = hostingLabel(null, null);
assert(offline.tone === "muted" && offline.parts.length === 0 && offline.source === null, JSON.stringify(offline));
assert(offline.text.includes("API not connected"), offline.text);

// No secret names, ever.
for (const label of [cache, live, stub, dormant, healthOnly, offline]) {
  for (const banned of ["MUBIT_API", "OPENROUTER", "Bearer", "sk-"]) {
    assert(!label.text.includes(banned), "banner must not name " + banned);
  }
}

console.log("hosting banner ok");
