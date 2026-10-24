/* Simulated pattern memory for the town demo.

   Mirrors correction_loop.escalation_threshold: after enough consistent
   repeats the pattern graduates to System 2 as complex_situation.
   This is not RL_OVERLAY promotion into System 1, and it does not change
   the stub gateway outcome.
*/
export const PATTERN_KEY = "baansafe.sim.pattern-memory";

function round3(value) {
  return Math.round(value * 1000) / 1000;
}

export function learnedTop(base, timesBefore, promoteAfter, threshold) {
  const n = Math.max(0, Number(timesBefore) || 0) + 1;
  const start = Number(base) || 0;
  const after = Math.max(2, Number(promoteAfter) || 2);
  const limit = Number(threshold) || 0.75;
  if (n >= after) {
    return round3(Math.min(0.96, Math.max(start, limit - 0.04)));
  }
  if (n <= 1) return round3(start);
  const target = Math.max(start, limit - 0.08);
  const t = (n - 1) / (after - 1);
  return round3(start + (target - start) * t);
}

export function decidePath({
  base,
  timesBefore,
  promoteAfter,
  threshold,
  learns,
  lifeSafety,
  confirmed,
  consistent,
}) {
  const prior = consistent === false ? 0 : Math.max(0, Number(timesBefore) || 0);
  const after = Math.max(2, Number(promoteAfter) || 2);
  const limit = Number(threshold) || 0.75;
  const raw = learnedTop(base, prior, after, limit);
  const seen = prior + 1;
  if (learns === false) {
    return {
      accepted: false,
      confidence: Math.min(raw, round3(limit - 0.04)),
      owner: "system_2",
      hold: "aid",
      explain:
        "Flood relief aid stays with System 2 and Sapling. This pattern is remembered, and the fast path does not take it.",
      timesBefore: prior,
    };
  }
  if (lifeSafety && !confirmed) {
    return {
      accepted: false,
      confidence: Math.min(raw, round3(limit - 0.04)),
      owner: "system_2",
      hold: "life_safety",
      explain:
        "This is a life-safety call. It stays with System 2 until an operator confirms the same outcome.",
      timesBefore: prior,
    };
  }
  if (lifeSafety && confirmed) {
    return {
      accepted: true,
      confidence: Math.min(0.96, Math.max(raw, round3(limit + 0.04))),
      owner: "system_1",
      hold: null,
      explain: "An operator confirmed this life-safety pattern, so the fast path can take the same outcome now.",
      timesBefore: prior,
    };
  }
  if (seen >= after) {
    return {
      accepted: false,
      confidence: Math.min(raw, round3(limit - 0.04)),
      owner: "system_2",
      hold: "escalated",
      explain:
        "This pattern has " +
        after +
        " consistent corrections, so it graduates to System 2 as a complex situation. It does not enter the System 1 fast path (RL_OVERLAY is off on this desk).",
      timesBefore: prior,
    };
  }
  const accepted = raw >= limit;
  return {
    accepted,
    confidence: raw,
    owner: accepted ? "system_1" : "system_2",
    hold: null,
    explain: "",
    timesBefore: prior,
  };
}

export function withTop(scores, topKey, topValue) {
  const source = scores || {};
  const keys = Object.keys(source);
  if (!keys.includes(topKey)) keys.push(topKey);
  const capped = Math.max(0, Math.min(0.96, Number(topValue) || 0));
  const others = keys.filter((key) => key !== topKey);
  const rest = others.reduce((sum, key) => sum + Math.max(0, Number(source[key]) || 0), 0);
  const remain = Math.max(0, 1 - capped);
  const next = {};
  next[topKey] = others.length ? capped : 1;
  for (const key of others) {
    const weight = rest > 0 ? Math.max(0, Number(source[key]) || 0) / rest : 1 / others.length;
    next[key] = weight * remain;
  }
  return next;
}
