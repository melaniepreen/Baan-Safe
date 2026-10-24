/* Operator gate for System 2.

   A System 1 fast path the confidence threshold accepts dispatches on its
   own. That includes a life-safety theme an operator has already confirmed:
   the stub fixture may still be labelled system_2, and the fast path still
   goes out. Everything else waits: a System 2 decision, a cascade (more
   than one source outcome), a Sapling aid decision, and a System 1 score
   under the threshold.
*/

export function needsOperatorApproval(decision, path) {
  const outcomes = (decision && decision.source_outcomes) || [];
  if (outcomes.length > 1) return true;
  if (path && path.accepted === true && path.owner === "system_1") return false;
  return true;
}

export function gateState(decision, path, rule) {
  const vehicle = rule && rule.vehicle && rule.vehicle !== "none" ? 1 : 0;
  if (!needsOperatorApproval(decision, path)) {
    return { phase: "dispatched", vehicles: vehicle, log: ["dispatched"], phone: "eta" };
  }
  return { phase: "pending", vehicles: 0, log: [], phone: "reviewing" };
}

export function acceptGate(state, rule) {
  if (!state || state.phase !== "pending") return state;
  const vehicle = rule && rule.vehicle && rule.vehicle !== "none" ? 1 : 0;
  return { phase: "dispatched", vehicles: vehicle, log: ["dispatched"], phone: "eta" };
}

export function rejectGate(state) {
  if (!state || state.phase !== "pending") return state;
  return { phase: "rejected", vehicles: 0, log: ["rejected"], phone: "reassigning" };
}
