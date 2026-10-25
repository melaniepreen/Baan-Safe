import { aboutDiagramSvg, mountAbout, stopAbout } from "./about.js";

function assert(cond, message) {
  if (!cond) throw new Error(message);
}

const svg = aboutDiagramSvg();
assert(svg.startsWith("<svg"), "diagram starts with <svg");
assert(svg.includes("<marker"), "arrowheads come from a <marker>");
assert(svg.includes("<title"), "diagram carries a <title>");
assert(svg.includes('role="img"'), "diagram is role=img");
for (const needle of ["System 1", "System 2", "Mubit gateway", "A person approves", "corrections"]) {
  assert(svg.includes(needle), `diagram names ${needle}`);
}
assert(typeof mountAbout === "function" && typeof stopAbout === "function", "sim.js API kept");
stopAbout();
stopAbout();

console.log("about ok");
