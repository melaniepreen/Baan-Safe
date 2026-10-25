import { readFileSync } from "node:fs";
import { evalHeadline, evalRows } from "./mubit_eval.js";

const report = JSON.parse(readFileSync(new URL("./data/mubit_eval.json", import.meta.url), "utf8"));
const headline = evalHeadline(report);
if (!headline.includes("api.mubit.ai")) throw new Error(headline);
if (!headline.includes("187 live calls")) throw new Error(headline);
if (!headline.includes("238 cache hits")) throw new Error(headline);
if (report.source !== "eval/snapshots/rl/20261025T0600Z-memory-local") {
  throw new Error(report.source);
}
const rows = evalRows(report);
const byId = Object.fromEntries(rows.map((row) => [row.id, row]));
if (rows.length !== 3) throw new Error("expected the three overlay patterns");
if (byId["RL-UP-2"].status !== "Recommendation" || byId["RL-UP-2"].label !== "upstairs-water") {
  throw new Error(JSON.stringify(byId["RL-UP-2"]));
}
if (byId["RL-COLD-2"].status !== "Recommendation") throw new Error(byId["RL-COLD-2"].status);
if (!byId["RL-WEAK-1"].detail.includes("predicted P3, truth P2")) throw new Error(byId["RL-WEAK-1"].detail);
if (rows.some((row) => row.status === "Graduated")) throw new Error("this run graduated nothing");
