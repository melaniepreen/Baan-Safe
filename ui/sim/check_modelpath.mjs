import {
  handlingPath,
  isLearnedRule,
  lastTurn,
  memoryRows,
  metricsParts,
  modelPathRows,
  parseGatewayNote,
  parseMemoryNote,
  parseMemoryWriteNote,
  parseMubitNote,
  routerDetail,
  splitTurns,
  systemPath,
} from "./modelpath.js";

const at = "2026-10-25T00:00:00Z";
const s1Escalate = {
  system: "system_1",
  outcome: "escalate",
  priority: "P2",
  needs: [],
  route: "supervisor_escalation",
  confidence: 0,
  reason: "No extracted needs for the fast path.",
  reasoning: null,
  missing_evidence: [],
  next_question: null,
  requires_human: false,
  escalate: true,
  latency_ms: 3,
};
const s2Reasoned = {
  system: "system_2",
  outcome: "reasoned_recommendation",
  priority: "P3",
  needs: ["water"],
  route: "welfare_distribution",
  confidence: 0.8,
  reason: "Nemotron reasoned over the case.",
  reasoning: "...",
  missing_evidence: [],
  next_question: null,
  requires_human: false,
  escalate: false,
  latency_ms: 420,
};
const cascadeTrace = [
  { case_id: "case-1", stage: "gateway", started_at: at, latency_ms: 0, notes: "mubit gateway: auth scheme is TODO_HUMAN; request was not rejected; safeguarding and escalation rules were not evaluated; memory via adapter; cascade route system_1; triggers: none" },
  { case_id: "case-1", stage: "memory", started_at: at, latency_ms: 1, notes: "memory via adapter mode=local; items=1" },
  { case_id: "case-1", stage: "system_1", started_at: at, latency_ms: 3, outcome: s1Escalate, notes: "real interface" },
  { case_id: "case-1", stage: "mubit_chat", started_at: at, latency_ms: 412, model: "nvidia/nemotron-3-nano-30b-a3b", tokens_in: 900, tokens_out: 120, notes: "mubit chat host=api.mubit.ai status=ok" },
  { case_id: "case-1", stage: "system_2", started_at: at, latency_ms: 420, outcome: s2Reasoned, notes: "real interface; mubit_chat hop traced in llm.complete" },
  { case_id: "case-1", stage: "router", started_at: at, latency_ms: 0, notes: "router.merge ran on the selected outcome(s)" },
  { case_id: "case-1", stage: "memory_write", started_at: at, latency_ms: 1, notes: "status=ok; kind=case_record; mode=local; lane=baansafe-case; corrections=0" },
];
const cascadeDecision = {
  case_id: "case-1",
  next_action: "create_provisional_dispatch",
  final_priority: "P3",
  final_route: "welfare_distribution",
  requires_human: false,
  source_outcomes: [s2Reasoned, s1Escalate],
  dispatches: [{ need: "water", resource_kind: "welfare_point", resource_id: "welfare-01", status: "provisional" }],
};

const gw = parseGatewayNote(cascadeTrace[0].notes);
if (gw.route !== "system_1" || gw.triggers.length !== 0 || gw.demoted) throw new Error("gateway note " + JSON.stringify(gw));
const gw2 = parseGatewayNote("mubit gateway: x; cascade route system_2; triggers: need:rescue, vulnerable:immobile, learned:demoted; graduated: door, elderly");
if (gw2.route !== "system_2" || gw2.triggers.join("|") !== "need:rescue|vulnerable:immobile|learned:demoted") throw new Error(JSON.stringify(gw2));
if (!gw2.demoted || gw2.graduated !== "door, elderly") throw new Error("demoted/graduated " + JSON.stringify(gw2));

const mem = parseMemoryNote("memory via adapter mode=local; items=2; retrieve_error=Timeout");
if (mem.mode !== "local" || mem.items !== 2 || mem.retrieve_error !== "Timeout") throw new Error(JSON.stringify(mem));
if (parseMemoryNote("memory via adapter mode=mock; items=0").retrieve_error !== null) throw new Error("no error expected");

if (parseMubitNote("mubit chat host=api.mubit.ai status=ok").tone !== "live") throw new Error("ok is live");
if (parseMubitNote("mubit chat host=api.mubit.ai status=cache_hit").label !== "CACHE HIT") throw new Error("cache hit label");
const bad = parseMubitNote("mubit chat host=api.mubit.ai status=http_429");
if (bad.tone !== "error" || !bad.label.includes("http_429")) throw new Error(JSON.stringify(bad));
if (parseMubitNote("mubit chat host=api.mubit.ai status=timeout").tone !== "error") throw new Error("timeout is error");

const write = parseMemoryWriteNote("status=error; error=ConnectionError; kind=case_record; mode=mubit");
if (write.ok || write.error !== "ConnectionError" || write.mode !== "mubit") throw new Error(JSON.stringify(write));
if (!parseMemoryWriteNote(cascadeTrace[6].notes).ok) throw new Error("ok write");

const rows = modelPathRows(cascadeTrace, cascadeDecision);
const stages = rows.map((row) => row.stage);
if (stages.join(",") !== "memory,gateway,system_1,cascade,mubit_chat,system_2,router,memory_write") {
  throw new Error("row order " + stages.join(","));
}
const divider = rows.find((row) => row.stage === "cascade");
if (!divider || !divider.divider || divider.label !== "CASCADE → System 2") throw new Error("cascade divider");
const chat = rows.find((row) => row.stage === "mubit_chat");
if (chat.latency_ms !== 412 || !chat.detail.includes("nvidia/nemotron-3-nano-30b-a3b") || !chat.detail.includes("900 in / 120 out")) {
  throw new Error("mubit row " + JSON.stringify(chat));
}
if (chat.badges[0].tone !== "live" || chat.badges[0].text !== "live via Mubit") throw new Error("mubit badge");
const routerRow = rows.find((row) => row.stage === "router");
if (!routerRow.detail.includes("create provisional dispatch") || !routerRow.detail.includes("water → welfare point welfare-01 (provisional)")) {
  throw new Error("router row " + routerRow.detail);
}
if (!routerDetail({ next_action: "finalize_case", final_priority: "P3", final_route: "duplicate_merge", requires_human: false, dispatches: [] }).includes("duplicate merge")) {
  throw new Error("router detail without dispatches");
}
const memRow = rows.find((row) => row.stage === "memory");
if (memRow.detail !== "mode local · 1 item") throw new Error("memory row " + memRow.detail);

const noCascade = modelPathRows(cascadeTrace.filter((event) => event.stage !== "system_1"), cascadeDecision);
if (noCascade.some((row) => row.stage === "cascade")) throw new Error("no divider without system_1 escalate");

const twoTurns = [...cascadeTrace, ...cascadeTrace];
if (splitTurns(twoTurns).length !== 2 || lastTurn(twoTurns).length !== cascadeTrace.length) throw new Error("turn split");
const chatTwice = [cascadeTrace[0], cascadeTrace[3], cascadeTrace[3], cascadeTrace[5]];
if (splitTurns(chatTwice).length !== 1) throw new Error("mubit_chat may repeat inside one turn");

const stubOutcome = { ...s2Reasoned, reason: "No stub outcome for case-9. Human decision logic is not implemented.", missing_evidence: ["fixture_stub"], requires_human: true };
const stubRows = modelPathRows([{ case_id: "c", stage: "system_2", started_at: at, latency_ms: 0, outcome: stubOutcome, notes: "stub interface" }], null);
if (!stubRows[0].badges.some((badge) => badge.text === "no stub for this case id (S2 stub mode)")) throw new Error("fixture_stub badge");
const downOutcome = { ...s2Reasoned, missing_evidence: ["system2_unavailable"] };
const downRows = modelPathRows([{ case_id: "c", stage: "system_2", started_at: at, latency_ms: 0, outcome: downOutcome }], null);
if (downRows[0].tone !== "amber" || !downRows[0].badges.some((badge) => badge.text === "System 2 unavailable → safe fallback")) throw new Error("unavailable badge");

const learned = { ...s1Escalate, outcome: "fast_route", escalate: false, reason: "Graduated pattern: System 2 decided this the same way 3 times." };
if (!isLearnedRule(learned) || isLearnedRule(s1Escalate) || isLearnedRule(null)) throw new Error("isLearnedRule");
const learnedRows = modelPathRows([{ case_id: "c", stage: "system_1", started_at: at, latency_ms: 0, outcome: learned }], null);
if (learnedRows[0].tone !== "learned" || learnedRows[0].badges[0].text !== "LEARNED RULE") throw new Error("learned row");
const demotedRows = modelPathRows([{ case_id: "c", stage: "gateway", started_at: at, latency_ms: 0, notes: "mubit gateway: a; cascade route system_2; triggers: learned:demoted" }], null);
if (!demotedRows[0].badges.some((badge) => badge.text === "demoted → System 2" && badge.tone === "learned")) throw new Error("demoted badge");

if (handlingPath({ requires_human: false, source_outcomes: [{ system: "system_1", reason: "Clear fast-path request." }] }) !== "system_1") throw new Error("s1 path");
if (handlingPath({ requires_human: false, source_outcomes: [learned] }) !== "learned") throw new Error("learned path");
if (handlingPath(cascadeDecision) !== "system_2") throw new Error("cascade is system_2");
if (handlingPath({ requires_human: false, source_outcomes: [s2Reasoned] }) !== "system_2") throw new Error("s2 only");
if (handlingPath({ requires_human: true, source_outcomes: [learned] }) !== "human") throw new Error("human overrides");
if (systemPath({ requires_human: true, source_outcomes: [learned] }) !== "learned") throw new Error("systemPath ignores the human flag");
if (systemPath({ requires_human: true, source_outcomes: [s2Reasoned, s1Escalate] }) !== "system_2") throw new Error("systemPath cascade");
if (handlingPath({ source_outcomes: [] }) !== null || handlingPath(null) !== null) throw new Error("no path without outcomes");

const memory = memoryRows(
  [
    { memory_id: "rec-F02-8", kind: "similar_case", summary: "Case F02: needs=food", relevance: 0.9, source_case_id: "F02" },
    { memory_id: "c-1", kind: "correction", summary: "Operator moved F10 to P1", relevance: 0.4, source_case_id: null },
  ],
  { final_route: "duplicate_merge" }
);
if (memory[0].pct !== 90 || !memory[0].merged || memory[0].source_case_id !== "F02") throw new Error(JSON.stringify(memory[0]));
if (memory[1].merged || memory[1].pct !== 40) throw new Error(JSON.stringify(memory[1]));
if (memoryRows(memory.slice(0, 1).map((row) => ({ ...row, relevance: 0.9 })), { final_route: "welfare_distribution" })[0].merged) throw new Error("merge needs duplicate_merge");
if (memoryRows([], null).length !== 0) throw new Error("empty memory");

const parts = metricsParts({
  cases_traced: 3,
  pct_handled_by_system_1: 0.6667,
  pct_handled_by_system_2: 0.3333,
  avg_latency_ms: { system_1: 0.5, system_2: 88, mubit_chat: null },
  mubit_chat: { call_count: 2, ok_count: 1, cache_hit_count: 1, error_count: 0, avg_latency_ms: 300 },
  memory: { mode: "local", retrieve_count: 3, hit_count: 1, duplicate_merge_count: 1, write_error_count: 0 },
  correction_count: 1,
});
const joined = parts.join(" · ");
for (const needle of ["Cases traced 3", "S1 67% / S2 33%", "Mubit chat 2 · ok 1 · cache 1 · err 0", "avg Mubit hop 300 ms", "duplicate merges 1", "corrections 1"]) {
  if (!joined.includes(needle)) throw new Error("metrics missing " + needle + " in " + joined);
}
if (joined.includes("write errors")) throw new Error("zero write errors stay quiet");
const counted = metricsParts({ system_1_count: 4, system_2_count: 2, cascade_count: 1 });
if (counted.join(" ") !== "S1 4 / S2 2 / cascade 1") throw new Error("counts " + counted.join(" "));
if (metricsParts({}).length !== 0 || metricsParts(null).length !== 0) throw new Error("only render keys that exist");

console.log("modelpath ok");
