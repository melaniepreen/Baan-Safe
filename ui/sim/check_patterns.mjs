import { decidePath, learnedTop } from "./patterns.js";

const threshold = 0.75;
const promoteAfter = 3;

if (learnedTop(0.36, 0, promoteAfter, threshold) !== 0.36) {
  throw new Error("first look should stay at the base score");
}
const second = learnedTop(0.36, 1, promoteAfter, threshold);
if (Math.abs(second - 0.525) > 0.001) throw new Error("second look " + second);

const seen = [];
let times = 0;
for (let call = 1; call <= 4; call += 1) {
  const path = decidePath({
    base: 0.36,
    timesBefore: times,
    promoteAfter,
    threshold,
    learns: true,
    lifeSafety: false,
    confirmed: false,
    consistent: true,
  });
  seen.push(path);
  times += 1;
}
if (seen[0].accepted || seen[1].accepted) throw new Error("says-fine accepted too early");
if (!seen[2].accepted || Math.abs(seen[2].confidence - 0.79) > 0.001) {
  throw new Error("third look should accept at 0.79");
}
if (!seen[2].explain.includes("handled the same way 3 times")) throw new Error(seen[2].explain);
if (!seen[3].accepted || seen[3].confidence <= seen[2].confidence) throw new Error("fourth look should stay accepted");

let life = 0;
for (let call = 1; call <= 4; call += 1) {
  const path = decidePath({
    base: 0.61,
    timesBefore: life,
    promoteAfter,
    threshold,
    learns: true,
    lifeSafety: true,
    confirmed: false,
    consistent: true,
  });
  if (path.accepted) throw new Error("life-safety accepted without confirmation");
  if (path.confidence > threshold - 0.04 + 0.001) throw new Error("life-safety cap " + path.confidence);
  if (!path.explain.includes("until an operator confirms")) throw new Error(path.explain);
  life += 1;
}

const confirmed = decidePath({
  base: 0.61,
  timesBefore: 0,
  promoteAfter,
  threshold,
  learns: true,
  lifeSafety: true,
  confirmed: true,
  consistent: true,
});
if (!confirmed.accepted) throw new Error("confirmed life-safety should take the fast path");

const aid = decidePath({
  base: 0.55,
  timesBefore: 5,
  promoteAfter,
  threshold,
  learns: false,
  lifeSafety: false,
  confirmed: true,
  consistent: true,
});
if (aid.accepted || aid.hold !== "aid") throw new Error("aid theme must stay with System 2");

const reset = decidePath({
  base: 0.36,
  timesBefore: 4,
  promoteAfter,
  threshold,
  learns: true,
  lifeSafety: false,
  confirmed: false,
  consistent: false,
});
if (reset.accepted || reset.confidence !== 0.36) throw new Error("a new priority restarts the streak");

console.log("patterns ok");
