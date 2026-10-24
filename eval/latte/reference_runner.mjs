// Headless calibrated reference. Imports the pinned checkout. Does not copy it.
// No gateway call. The plan vector is not written out.

import { readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const root = process.argv[2];
const out = process.argv[3];
if (!root || !out) {
  console.error("usage: reference_runner.mjs <latte-bench-dir> <output.json>");
  process.exit(2);
}

const plans = await import(pathToFileURL(join(root, "src/plans.js")).href);
const bench = await import(pathToFileURL(join(root, "src/benchmark.js")).href);
const conditions = await import(pathToFileURL(join(root, "src/conditions.js")).href);
const calibration = JSON.parse(readFileSync(join(root, "tasks/calibration.json"), "utf8"));

const taskId = "heart";
const gate = plans.calibrationStatus({ replay: true, taskId });
const task = bench.taskSpec(taskId, 42);
const result = plans.runPlan({
  plan: calibration.tasks[taskId].referencePlan,
  task,
  conditions: conditions.NOMINAL_CONDITIONS,
  evidence: false,
});
const evaluation = result.evaluation ?? {};
const number = (value) => (typeof value === "number" && Number.isFinite(value) ? value : null);
const payload = {
  mode: "calibrated-reference",
  task: taskId,
  seed: 42,
  passed: evaluation.passed === true,
  score: number(evaluation.score),
  shape_iou: number(evaluation.shapeIoU),
  boundary_f1: number(evaluation.boundaryF1),
  precision: number(evaluation.precision),
  outcome: typeof result.outcome === "string" ? result.outcome : null,
  api_calls: 0,
  calibration_ready: gate.ready === true,
  commit: process.env.LATTE_PIN || null,
};
writeFileSync(out, JSON.stringify(payload, null, 2) + "\n");
const ok = payload.calibration_ready && payload.passed;
console.log(
  `calibrated reference task=${taskId} seed=42 passed=${payload.passed} score=${payload.score} api_calls=0`,
);
process.exit(ok ? 0 : 1);
