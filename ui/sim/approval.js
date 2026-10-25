/* Operator gate for System 2.

   A System 1 fast path the confidence threshold accepts dispatches on its
   own. That includes a life-safety theme an operator has already confirmed:
   the stub fixture may still be labelled system_2, and the fast path still
   goes out. Everything else waits: a System 2 decision, a cascade (more
   than one source outcome), a Sapling aid decision, and a System 1 score
   under the threshold.
*/

export function closedWithoutVehicle(decision) {
  const route = decision && decision.final_route;
  if (route === "information_only" || route === "duplicate_merge") return true;
  const dispatches = (decision && decision.dispatches) || [];
  return decision && decision.next_action === "finalize_case" && dispatches.length === 0;
}

export function needsOperatorApproval(decision, path) {
  if (closedWithoutVehicle(decision)) return false;
  const outcomes = (decision && decision.source_outcomes) || [];
  if (outcomes.length > 1) return true;
  if (outcomes.some((row) => row && row.system === "system_2")) return true;
  const route = decision && decision.final_route;
  if (route === "aid_caseworker" || route === "supervisor_escalation") return true;
  if (path && path.accepted === true && path.owner === "system_1") return false;
  if (decision && decision.next_action === "create_provisional_dispatch") return false;
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
