/* Plain-language subtitle under the phone number: what this deploy actually does,
   from GET /health. Pure so check_subtitle.mjs can run it under node. */
export const FALLBACK = "Operator replies are scripted. The routing decision is live from the gateway.";

export function chooserSubtitle(health) {
  const impl = (health && health.impl) || {};
  const s1 = String(impl.S1_IMPL || "").toLowerCase();
  const s2 = String(impl.S2_IMPL || "").toLowerCase();
  const memMode = String((health && health.memory && health.memory.mode) || impl.MEMORY_IMPL || "").toLowerCase();
  const dormant = !!(health && health.memory && health.memory.dormant);
  const parts = [];
  parts.push(s1 === "real"
    ? "Routine requests are decided by rules in milliseconds"
    : "Routine requests replay recorded fixture outcomes");
  if (s2 === "real") parts.push("complex ones go to Nemotron through the Mubit gateway, live");
  else if (s2 === "cache") parts.push("complex ones go to Nemotron through the Mubit gateway, replaying recorded answers and calling live on a miss");
  else parts.push("complex ones replay recorded fixture outcomes");
  let memory;
  if (dormant) memory = "Memory is switched off on this deploy (the Mubit memory API is not available), so repeat callers are not recognised.";
  else if (memMode === "local") memory = "Every case is remembered in BaanSafe's own store, so a repeat caller at the same place merges instead of sending a second boat.";
  else if (memMode === "mubit") memory = "Case memory is kept by Mubit.";
  else memory = "Case memory comes from fixture files.";
  return parts.join("; ") + ". " + memory + " Operator replies on this phone are scripted.";
}
