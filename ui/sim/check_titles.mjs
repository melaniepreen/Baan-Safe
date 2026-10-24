import { callSummary } from "./call_title.js";

function assert(cond, message) {
  if (!cond) throw new Error(message);
}

assert(
  callSummary({ title: "Oxygen-dependent elderly person, rising water", text: "hello" }) ===
    "Oxygen-dependent elderly person, rising water",
  "fixture title wins"
);
assert(
  callSummary({ summary: "Asking for rice", title: "Rice finished, no danger", text: "rice" }) === "Asking for rice",
  "summary wins over title"
);

const oxygen = callSummary({ text: "My grandmother needs oxygen. The water is rising in the lane." });
assert(oxygen === "Grandmother needs oxygen, water rising", oxygen);
assert(!/rice|shelter|clinic/i.test(oxygen), oxygen);

const rice = callSummary({ text: "Can someone bring rice and drinking water today?" });
assert(rice === "Asking for rice and drinking water", rice);
assert(!/grandmother|oxygen/i.test(rice), rice);

const plain = callSummary({ text: "Please call me back when you can later this afternoon thanks" });
assert(plain.endsWith("…"), plain);
assert(plain.split(" ").length === 8 || plain.split("…")[0].split(" ").length === 8, plain);
assert(!/oxygen|rice|boat/i.test(plain), plain);

console.log("call titles ok");
