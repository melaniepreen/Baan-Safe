/* Readout for Moly's 25 Oct live Mubit RL run.

   The numbers and pattern rows come from
   eval/snapshots/rl/20261025T0600Z-memory-local (run.json events and
   final_overlay). This module does not call Mubit.
*/

export function evalHeadline(report) {
  const hop = (report && report.mubit) || {};
  const via = hop.via || "Mubit";
  const live = hop.live_ok == null ? "?" : hop.live_ok;
  const cache = hop.cache_hits == null ? "?" : hop.cache_hits;
  const errors = hop.errors == null ? "?" : hop.errors;
  const label = (report && report.label) || "Mubit eval";
  const outcome = (report && report.outcome) || "";
  return (
    label +
    ". Live System 2 via " +
    via +
    ". " +
    live +
    " live calls, " +
    cache +
    " cache hits, " +
    errors +
    " errors. " +
    outcome
  ).trim();
}

export function evalRows(report) {
  return ((report && report.patterns) || []).map((row) => ({
    id: row.id || "",
    label: row.label || row.id || "",
    status: row.status || "",
    detail: row.detail || "",
  }));
}
