import { chooserSubtitle } from "./subtitle.js";

const hosted = chooserSubtitle({
  impl: { S1_IMPL: "real", S2_IMPL: "cache", MEMORY_IMPL: "local" },
  memory: { mode: "local", dormant: false },
});
for (const piece of ["rules in milliseconds", "replaying recorded answers", "BaanSafe's own store"]) {
  if (!hosted.includes(piece)) throw new Error("hosted shape missing: " + piece);
}
if (!hosted.endsWith("scripted.")) throw new Error("hosted shape does not end with 'scripted.'");

const stubs = chooserSubtitle({
  impl: { S1_IMPL: "stub", S2_IMPL: "stub", MEMORY_IMPL: "mock" },
});
if ((stubs.match(/fixture outcomes/g) || []).length !== 2) throw new Error("stub shape should say fixture twice");
if (stubs.includes("Mubit gateway")) throw new Error("stub shape must not name the Mubit gateway");

const dormant = chooserSubtitle({
  impl: { S1_IMPL: "real", S2_IMPL: "real", MEMORY_IMPL: "mubit" },
  memory: { mode: "mubit", dormant: true },
});
if (!dormant.includes("switched off")) throw new Error("dormant memory must say 'switched off'");

const empty = chooserSubtitle(null);
if (!empty || empty.includes("undefined")) throw new Error("null health must still produce a sentence");

console.log("subtitle ok");
