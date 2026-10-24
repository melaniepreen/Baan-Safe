import { MAX_DRAW_PX_PER_S, MIN_TRIP_MS, phaseDurationMs } from "./pace.js";

function assert(cond, message) {
  if (!cond) throw new Error(message);
}

assert(phaseDurationMs(0) === MIN_TRIP_MS, "empty path uses the minimum");
assert(phaseDurationMs(40) === MIN_TRIP_MS, "short path uses the minimum");
const twoSois = phaseDurationMs(215);
const fourSois = phaseDurationMs(430);
assert(twoSois >= 3900 && twoSois <= 8000, "two sois " + twoSois);
assert(fourSois >= 4000 && fourSois <= 8000, "four sois " + fourSois);
assert(phaseDurationMs(900) > fourSois, "longer paths stay slower than the cap");
assert(MAX_DRAW_PX_PER_S === 54, "cap");
console.log("pace ok");
