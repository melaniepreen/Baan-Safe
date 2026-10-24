import { acceptGate, gateState, needsOperatorApproval, rejectGate } from "./approval.js";

const fast = { accepted: true, owner: "system_1" };
const handedOff = { accepted: false, owner: "system_2" };
const boat = { id: "p1-medical", vehicle: "boat" };
const none = { id: "aid-review", vehicle: "none" };
const s1 = { source_outcomes: [{ system: "system_1" }] };
const s2 = { source_outcomes: [{ system: "system_2" }] };
const cascade = { source_outcomes: [{ system: "system_2" }, { system: "system_1" }] };

function assert(cond, message) {
  if (!cond) throw new Error(message);
}

assert(needsOperatorApproval(s1, fast) === false, "System 1 above the threshold dispatches on its own");
assert(needsOperatorApproval(s2, fast) === false, "a confirmed fast path still dispatches when the stub label is system_2");
assert(needsOperatorApproval(s1, handedOff) === true, "System 1 under the threshold waits");
assert(needsOperatorApproval(s2, handedOff) === true, "System 2 waits");
assert(needsOperatorApproval(cascade, fast) === true, "a cascade waits even if the score would accept");
assert(needsOperatorApproval(s2, { accepted: false, owner: "system_2", hold: "aid" }) === true, "Sapling aid via System 2 waits");

const pending = gateState(s2, handedOff, boat);
assert(pending.phase === "pending", pending.phase);
assert(pending.vehicles === 0, "no vehicle before Accept");
assert(pending.log.includes("dispatched") === false, "no dispatched log before Accept");
assert(pending.phone === "reviewing", pending.phone);

const accepted = acceptGate(pending, boat);
assert(accepted.phase === "dispatched", accepted.phase);
assert(accepted.vehicles === 1, "Accept sends the boat");
assert(accepted.log[0] === "dispatched", accepted.log.join(","));
assert(accepted.phone === "eta", accepted.phone);

const rejected = rejectGate(pending);
assert(rejected.phase === "rejected", rejected.phase);
assert(rejected.vehicles === 0, "Reject sends no vehicle");
assert(rejected.log.includes("dispatched") === false, "Reject is not a dispatch");
assert(rejected.phone === "reassigning", rejected.phone);

const aid = acceptGate(gateState(s2, handedOff, none), none);
assert(aid.vehicles === 0, "an aid decision still has no vehicle after Accept");
assert(aid.log[0] === "dispatched", "Accept still records the decision");

const auto = gateState(s1, fast, { vehicle: "van" });
assert(auto.phase === "dispatched" && auto.vehicles === 1, "System 1 van leaves immediately");

console.log("approval gate ok");
