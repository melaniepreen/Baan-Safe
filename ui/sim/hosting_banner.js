/* Hosting banner: one line at the top of the town page that says which
   backends this deploy runs. Reads GET /hosting (the Modal gateway) and falls
   back to GET /health (every build). sim.js is untouched; this module owns
   #hosting-banner only. The label builder is pure so check_hosting_banner.mjs
   can run it under node. Tones match modelpath.js: live, cache, error, muted.
*/

export const S2_LABEL = {
  real: "live via Mubit",
  cache: "replaying saved answers, live via Mubit on new calls",
  stub: "sample answers, no model call",
};

/* Plain words for the memory backend. `dormant` wins: that deploy remembers nothing. */
export function MEMORY_LABEL(mode, dormant) {
  if (dormant) return "off (Mubit memory API unavailable)";
  if (mode === "local") return "on (BaanSafe store)";
  if (mode === "mubit") return "on (Mubit)";
  if (mode === "mock") return "sample files";
  return "checking…";
}

function text(value) {
  return value == null ? "" : String(value);
}

function implOf(hosting, health) {
  const fromHosting = hosting && hosting.impl && typeof hosting.impl === "object" ? hosting.impl : {};
  const fromHealth = health && health.impl && typeof health.impl === "object" ? health.impl : {};
  return { ...fromHealth, ...fromHosting };
}

/* Which System 2 this deploy runs: S2_IMPL first, then the /hosting backends
   word. Unknown values are shown as given rather than guessed. */
export function system2Mode(hosting, health) {
  const impl = implOf(hosting, health);
  const s2 = text(impl.S2_IMPL).toLowerCase();
  if (s2) return s2;
  const backends = text(hosting && hosting.backends).toLowerCase();
  if (backends === "live") return "real";
  if (backends === "cache") return "cache";
  if (backends === "s1-real" || backends === "stub") return "stub";
  return null;
}

export function memoryMode(hosting, health) {
  const impl = implOf(hosting, health);
  return (
    text(impl.MEMORY_IMPL).toLowerCase() ||
    text(hosting && hosting.memory).toLowerCase() ||
    text(health && health.memory && health.memory.mode).toLowerCase() ||
    null
  );
}

export function memoryDormant(hosting, health) {
  if (health && health.memory && health.memory.dormant === true) return true;
  return memoryMode(hosting, health) === "mubit";
}

/* Build the banner. Returns { text, tone, parts, warning, source }.
   tone: "live" | "cache" | "muted" | "error". */
export function hostingLabel(hosting, health) {
  if (!hosting && !health) {
    return {
      text: "Hosting: API not connected (/hosting and /health did not answer)",
      tone: "muted",
      parts: [],
      warning: null,
      source: null,
    };
  }
  const s2 = system2Mode(hosting, health);
  const s2Label = s2 ? S2_LABEL[s2] || s2 : "checking…";
  const memory = memoryMode(hosting, health);
  const dormant = memoryDormant(hosting, health);
  const warning = dormant
    ? text(health && health.memory && health.memory.warning) ||
      "MEMORY_IMPL=mubit is dormant: Mubit has no memory API today. Set MEMORY_IMPL=local."
    : null;
  let credentials = "checking…";
  if (hosting && typeof hosting.secrets === "boolean") credentials = hosting.secrets ? "connected" : "not connected";
  const parts = [
    "System 2 (Nemotron): " + s2Label,
    "Case memory: " + MEMORY_LABEL(memory, dormant),
    "Mubit: " + credentials,
  ];
  let tone = "muted";
  if (dormant) tone = "error";
  else if (s2 === "real") tone = "live";
  else if (s2 === "cache") tone = "cache";
  return {
    text: parts.join(" · ") + (warning ? " — " + warning : ""),
    tone,
    parts,
    warning,
    source: hosting ? "/hosting" : "/health",
  };
}

async function fetchJson(url) {
  try {
    const response = await fetch(url, { headers: { Accept: "application/json" } });
    if (!response.ok) return null;
    return await response.json();
  } catch (error) {
    return null;
  }
}

function render(label) {
  let node = document.getElementById("hosting-banner");
  if (!node) {
    node = document.createElement("div");
    node.id = "hosting-banner";
    document.body.prepend(node);
  }
  node.className = "hosting-banner tone-" + label.tone;
  node.setAttribute("role", label.tone === "error" ? "alert" : "status");
  node.title = label.text + (label.source ? " (" + label.source + ")" : "");
  node.replaceChildren();
  const dot = document.createElement("span");
  dot.className = "hosting-dot";
  dot.setAttribute("aria-hidden", "true");
  node.append(dot);
  label.parts.forEach((part, index) => {
    if (index > 0) {
      const sep = document.createElement("span");
      sep.className = "hosting-sep";
      sep.textContent = "·";
      node.append(sep);
    }
    const span = document.createElement("span");
    span.className = "hosting-part";
    span.textContent = part;
    node.append(span);
  });
  if (!label.parts.length) {
    const span = document.createElement("span");
    span.className = "hosting-part";
    span.textContent = label.text;
    node.append(span);
  }
  if (label.warning) {
    const warn = document.createElement("span");
    warn.className = "hosting-warning";
    warn.textContent = label.warning;
    node.append(warn);
  }
  if (label.source) {
    const src = document.createElement("span");
    src.className = "hosting-source";
    src.textContent = label.source;
    node.append(src);
  }
}

export async function loadHostingBanner() {
  const hosting = await fetchJson("/hosting");
  const health = await fetchJson("/health");
  const label = hostingLabel(hosting, health);
  render(label);
  return label;
}

if (typeof document !== "undefined" && typeof fetch === "function") {
  const start = () => { loadHostingBanner(); };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start, { once: true });
  else start();
}
