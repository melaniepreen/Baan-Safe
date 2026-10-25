/* Model path readout for one call, built from GET /cases/{id}/trace.

   Pure functions, no DOM. sim.js renders the rows; check_modelpath.mjs
   runs them under node. Trace notes are the `; `-separated strings the
   gateway writes (gateway/route.py, llm/client.py). Nothing here invents
   a value that is not in the trace or the decision.
*/

export const STAGE_ORDER = [
  "enrich",
  "memory",
  "gateway",
  "system_1",
  "cascade",
  "mubit_chat",
  "system_2",
  "router",
  "memory_write",
];

export const STAGE_LABEL = {
  enrich: "Enrich",
  memory: "Memory",
  gateway: "Mubit gateway",
  system_1: "System 1",
  cascade: "Cascade",
  mubit_chat: "Mubit chat",
  system_2: "System 2 · Nemotron",
  router: "Decision router",
  memory_write: "Memory write",
};

export const PATH_HEX = {
  system_1: 0x2e7d32,
  system_2: 0x3949ab,
  learned: 0x7e57c2,
  human: 0xb8860b,
};

export const PATH_LABEL = {
  system_1: "System 1",
  system_2: "System 2",
  learned: "Learned rule",
  human: "Human required",
};

export const LEARNED_PREFIX = "Graduated pattern:";

function text(value) {
  return value == null ? "" : String(value);
}

function kv(notes) {
  const out = {};
  const pattern = /([A-Za-z_][A-Za-z0-9_]*)=([^\s;]*)/g;
  let hit;
  while ((hit = pattern.exec(text(notes)))) out[hit[1]] = hit[2];
  return out;
}

export function truncate(value, max = 96) {
  const line = text(value).trim();
  if (line.length <= max) return line;
  return line.slice(0, Math.max(0, max - 1)).trimEnd() + "…";
}

export function isLearnedRule(outcome) {
  return !!outcome && text(outcome.reason).startsWith(LEARNED_PREFIX);
}

export function parseGatewayNote(notes) {
  const line = text(notes);
  const route = /\broute (system_[12])/.exec(line);
  let triggers = [];
  const at = line.indexOf("triggers:");
  if (at >= 0) {
    const rest = line.slice(at + "triggers:".length).split(";")[0].trim();
    if (rest && rest !== "none") triggers = rest.split(",").map((item) => item.trim()).filter(Boolean);
  }
  const graduated = /;\s*graduated:\s*(.+)$/.exec(line);
  return {
    route: route ? route[1] : null,
    mode: /\bcascade route\b/.test(line) ? "cascade" : null,
    triggers,
    demoted: triggers.includes("learned:demoted"),
    graduated: graduated ? graduated[1].trim() : null,
  };
}

export function parseMemoryNote(notes) {
  const bag = kv(notes);
  const items = Number(bag.items);
  return {
    mode: bag.mode || null,
    items: Number.isFinite(items) ? items : 0,
    retrieve_error: bag.retrieve_error || null,
  };
}

export function parseMubitNote(notes) {
  const bag = kv(notes);
  const status = bag.status || null;
  let tone = "error";
  let label = status ? "error " + status : "no status";
  if (status === "ok") {
    tone = "live";
    label = "live via Mubit";
  } else if (status === "cache_hit") {
    tone = "cache";
    label = "CACHE HIT";
  }
  const requestId = /^mreq_[0-9a-f]{32}$/.test(bag.request_id || "") ? bag.request_id : null;
  return {
    host: bag.host || null,
    status,
    tone,
    label,
    requestId,
    recorded: requestId !== null && /\(recorded\)/.test(text(notes)),
  };
}

export function parseMemoryWriteNote(notes) {
  const bag = kv(notes);
  const status = bag.status || null;
  return {
    status,
    ok: status === "ok",
    kind: bag.kind || null,
    mode: bag.mode || null,
    lane: bag.lane || null,
    error: bag.error || null,
  };
}

function outcomeDetail(outcome) {
  if (!outcome) return "";
  return [outcome.priority, text(outcome.route).replaceAll("_", " "), truncate(outcome.reason, 110)]
    .filter(Boolean)
    .join(" · ");
}

function outcomeBadges(outcome, stage) {
  const badges = [];
  if (!outcome) return badges;
  const missing = (outcome.missing_evidence || []).map(String);
  if (stage === "system_1" && isLearnedRule(outcome)) badges.push({ tone: "learned", text: "LEARNED RULE" });
  if (missing.includes("fixture_stub")) badges.push({ tone: "muted", text: "no stub for this case id (S2 stub mode)" });
  if (missing.includes("system2_unavailable")) badges.push({ tone: "amber", text: "System 2 unavailable → safe fallback" });
  if (outcome.requires_human === true) badges.push({ tone: "amber", text: "requires human" });
  if (outcome.escalate === true) badges.push({ tone: "muted", text: "escalate" });
  return badges;
}

/* A turn is one run of stages. Only mubit_chat repeats inside a turn, so a
   stage seen twice starts the next turn. */
export function splitTurns(trace) {
  const turns = [];
  let current = [];
  let seen = new Set();
  for (const event of trace || []) {
    const stage = text(event && event.stage);
    if (!stage) continue;
    if (stage !== "mubit_chat" && seen.has(stage)) {
      turns.push(current);
      current = [];
      seen = new Set();
    }
    current.push(event);
    seen.add(stage);
  }
  if (current.length) turns.push(current);
  return turns;
}

export function lastTurn(trace) {
  const turns = splitTurns(trace);
  return turns.length ? turns[turns.length - 1] : [];
}

function dispatchLine(row) {
  const kind = text(row.resource_kind).replaceAll("_", " ");
  const id = row.resource_id ? " " + row.resource_id : "";
  return text(row.need) + " → " + kind + id + " (" + text(row.status || "unfilled") + ")";
}

export function routerDetail(decision) {
  if (!decision) return "";
  const bits = [
    text(decision.next_action).replaceAll("_", " "),
    decision.final_priority,
    text(decision.final_route).replaceAll("_", " "),
    decision.requires_human === true ? "requires human" : "no human required",
  ].filter(Boolean);
  const dispatches = (decision.dispatches || []).map(dispatchLine);
  return bits.join(" · ") + (dispatches.length ? " · " + dispatches.join("; ") : "");
}

export function modelPathRows(trace, decision) {
  const events = lastTurn(trace);
  const rows = [];
  const byStage = {};
  for (const event of events) {
    const stage = text(event.stage);
    (byStage[stage] = byStage[stage] || []).push(event);
  }
  const s1 = (byStage.system_1 || [])[0];
  const s2 = (byStage.system_2 || [])[0];
  const cascaded = !!(s1 && s2 && s1.outcome && s1.outcome.escalate === true);
  for (const stage of STAGE_ORDER) {
    if (stage === "cascade") {
      if (cascaded) rows.push({ stage, label: "CASCADE → System 2", latency_ms: null, detail: "", badges: [], divider: true });
      continue;
    }
    for (const event of byStage[stage] || []) {
      const row = {
        stage,
        label: STAGE_LABEL[stage] || stage,
        latency_ms: Number.isFinite(event.latency_ms) ? event.latency_ms : null,
        detail: "",
        badges: [],
        tone: null,
        divider: false,
      };
      if (stage === "enrich") {
        row.detail = text(event.notes) || "enrich";
      } else if (stage === "memory") {
        const mem = parseMemoryNote(event.notes);
        row.detail = "mode " + (mem.mode || "?") + " · " + mem.items + " item" + (mem.items === 1 ? "" : "s");
        if (mem.retrieve_error) {
          row.tone = "error";
          row.badges.push({ tone: "error", text: "retrieve_error=" + mem.retrieve_error });
        }
      } else if (stage === "gateway") {
        const gw = parseGatewayNote(event.notes);
        row.detail =
          "route " + (gw.route || "?") + " · triggers: " + (gw.triggers.length ? gw.triggers.join(", ") : "none");
        if (gw.demoted) row.badges.push({ tone: "learned", text: "demoted → System 2" });
        if (gw.graduated) row.badges.push({ tone: "learned", text: "graduated: " + gw.graduated });
      } else if (stage === "system_1" || stage === "system_2") {
        row.detail = outcomeDetail(event.outcome) || text(event.notes);
        row.badges = outcomeBadges(event.outcome, stage);
        if (stage === "system_1" && isLearnedRule(event.outcome)) row.tone = "learned";
        if ((event.outcome && (event.outcome.missing_evidence || []).includes("system2_unavailable"))) row.tone = "amber";
      } else if (stage === "mubit_chat") {
        const chat = parseMubitNote(event.notes);
        const bits = [event.model || "model ?"];
        if (event.tokens_in != null || event.tokens_out != null) {
          bits.push("tokens " + (event.tokens_in == null ? "?" : event.tokens_in) + " in / " + (event.tokens_out == null ? "?" : event.tokens_out) + " out");
        }
        if (chat.host) bits.push(chat.host);
        if (chat.requestId) bits.push(chat.requestId + (chat.recorded ? " (recorded)" : ""));
        row.detail = bits.join(" · ");
        row.badges.push({ tone: chat.tone, text: chat.label });
        row.tone = chat.tone;
      } else if (stage === "router") {
        row.detail = routerDetail(decision) || text(event.notes);
      } else if (stage === "memory_write") {
        const write = parseMemoryWriteNote(event.notes);
        row.detail = (write.ok ? "ok" : "error") + (write.kind ? " · " + write.kind : "") + (write.mode ? " · mode " + write.mode : "");
        if (!write.ok) {
          row.tone = "error";
          row.badges.push({ tone: "error", text: write.error ? "error " + write.error : "write error" });
        }
      }
      rows.push(row);
    }
  }
  return rows;
}

/* Which system settled the turn, before the human override. */
export function systemPath(decision) {
  const outcomes = (decision && decision.source_outcomes) || [];
  if (!outcomes.length) return null;
  if (outcomes.some((row) => text(row.system) === "system_2")) return "system_2";
  const deciding = outcomes[0];
  if (isLearnedRule(deciding)) return "learned";
  return "system_1";
}

export function handlingPath(decision) {
  const path = systemPath(decision);
  if (!path) return null;
  if (decision.requires_human === true) return "human";
  return path;
}

export function memoryRows(memoryContext, decision) {
  const merged = !!decision && text(decision.final_route) === "duplicate_merge";
  return (memoryContext || []).map((item) => {
    const relevance = Number(item.relevance);
    const pct = Number.isFinite(relevance) ? Math.round(relevance * 100) : null;
    return {
      memory_id: item.memory_id || null,
      kind: text(item.kind) || "memory",
      pct,
      source_case_id: item.source_case_id || null,
      summary: truncate(item.summary, 140),
      merged: merged && item.kind === "similar_case" && relevance >= 0.9,
    };
  });
}

function count(value) {
  return value == null ? null : Number(value);
}

export function metricsParts(metrics) {
  const parts = [];
  if (!metrics || typeof metrics !== "object") return parts;
  if (metrics.cases_traced != null) parts.push("Cases traced " + metrics.cases_traced);
  const s1 = count(metrics.system_1_count != null ? metrics.system_1_count : metrics.handled_by_system_1);
  const s2 = count(metrics.system_2_count != null ? metrics.system_2_count : metrics.handled_by_system_2);
  const cascade = count(metrics.cascade_count);
  if (s1 != null || s2 != null || cascade != null) {
    parts.push(
      ["S1 " + (s1 == null ? "—" : s1), "S2 " + (s2 == null ? "—" : s2), cascade == null ? null : "cascade " + cascade]
        .filter(Boolean)
        .join(" / ")
    );
  } else {
    const share1 = metrics.pct_handled_by_system_1;
    const share2 = metrics.pct_handled_by_system_2;
    if (share1 != null || share2 != null) {
      parts.push(
        "S1 " + (share1 == null ? "—" : Math.round(Number(share1) * 100) + "%") +
          " / S2 " + (share2 == null ? "—" : Math.round(Number(share2) * 100) + "%")
      );
    }
  }
  const mubit = metrics.mubit_chat;
  if (mubit && mubit.call_count != null) {
    parts.push(
      "Mubit chat " + mubit.call_count +
        " · ok " + (mubit.ok_count || 0) +
        " · cache " + (mubit.cache_hit_count || 0) +
        " · err " + (mubit.error_count || 0)
    );
  }
  const avgMubit = mubit && mubit.avg_latency_ms != null ? mubit.avg_latency_ms : (metrics.avg_latency_ms || {}).mubit_chat;
  if (avgMubit != null) parts.push("avg Mubit hop " + Math.round(Number(avgMubit)) + " ms");
  else if ((metrics.avg_latency_ms || {}).system_2 != null) parts.push("avg System 2 " + Math.round(Number(metrics.avg_latency_ms.system_2)) + " ms");
  const memory = metrics.memory;
  if (memory && typeof memory === "object") {
    const bits = [];
    if (memory.mode) bits.push("mode " + memory.mode);
    if (memory.hit_count != null && memory.retrieve_count != null) bits.push("hits " + memory.hit_count + "/" + memory.retrieve_count);
    if (memory.duplicate_merge_count != null) bits.push("duplicate merges " + memory.duplicate_merge_count);
    if (memory.write_error_count) bits.push("write errors " + memory.write_error_count);
    if (bits.length) parts.push("Memory " + bits.join(" · "));
  }
  if (metrics.correction_count != null) parts.push("corrections " + metrics.correction_count);
  return parts;
}
