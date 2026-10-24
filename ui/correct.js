/* Operator correction.

The closed label lists are the values of S1Label, S2Action, and SaplingVerdict
in contracts/training.py. This file does not define a second schema. tests/
test_correct_ui.py fails if a value drifts.

The operator picks output_correct and types a reason. task and input_ref are
filled from the case and the gateway decision.
*/

export const TASKS = {
  s1_triage: [
    "niems_red_critical",
    "niems_yellow_urgent",
    "niems_green_not_severe",
    "niems_white_general",
    "niems_black_not_a_patient",
    "niems_not_conscious_or_breathing",
    "sphere_water_short",
    "sphere_food_short",
    "sphere_shelter_crowded",
    "safeguarding_child",
    "safeguarding_older_person",
    "safeguarding_disability",
    "safeguarding_serious_health",
    "safeguarding_protection_referral",
    "flood_water_depth",
    "flood_trapped",
  ],
  s2_action: [
    "ask_next_question",
    "create_provisional_dispatch",
    "escalate_to_supervisor",
    "finalize_case",
    "request_more_evidence",
  ],
  sapling_verdict: ["supported", "violation", "missing", "contradicted", "unsure"],
};

const MODEL_VERSION = {
  s1_triage: "s1@stub",
  s2_action: "s2@stub",
  sapling_verdict: "sapling@stub",
};

const THAI = /[\u0E00-\u0E7F]/;
const LATIN = /[A-Za-z]/;
const RULE_ID = /^[A-Z][A-Z0-9]+(?:-[A-Z0-9]+)+$/;

export function detectLang(texts) {
  const blob = texts.join("\n");
  const thai = THAI.test(blob);
  const latin = LATIN.test(blob);
  if (thai && latin) return "mixed";
  if (thai) return "th";
  return "en";
}

export function turnId(caseId, turn, index) {
  if (turn && typeof turn.turn_id === "string" && turn.turn_id) return turn.turn_id;
  const stamp = turn && Number.isFinite(turn.t_ms) ? turn.t_ms : index;
  return caseId + ":" + index + ":" + stamp;
}

export function policyIds(caseState) {
  const found = [];
  const push = (value) => {
    if (typeof value === "string" && RULE_ID.test(value) && !found.includes(value)) found.push(value);
  };
  for (const flag of caseState.policy_flags || []) push(flag);
  for (const item of caseState.memory_context || []) {
    if (item && item.kind === "policy") push(item.memory_id);
  }
  return found;
}

export function memoryRef(caseState) {
  const items = caseState.memory_context || [];
  if (!items.length || !items[0] || typeof items[0].memory_id !== "string" || !items[0].memory_id) {
    return null;
  }
  return items[0].memory_id;
}

export function buildInputRef(caseState) {
  const turns = caseState.transcript || [];
  return {
    case_id: caseState.case_id,
    turn_ids: turns.map((turn, index) => turnId(caseState.case_id, turn, index)),
    lang: detectLang(turns.map((turn) => (turn && turn.text) || "")),
    policy_ids: policyIds(caseState),
    memory_ref: memoryRef(caseState),
  };
}

function aidOrDenial(caseState, outcome) {
  const flags = new Set(caseState.policy_flags || []);
  const needs = new Set([...(outcome.needs || []), ...((caseState.fields && caseState.fields.needs) || [])]);
  return (
    outcome.route === "aid_caseworker" ||
    needs.has("aid_payment") ||
    flags.has("aid_eligibility") ||
    flags.has("aid_exception") ||
    flags.has("aid_denial")
  );
}

export function inferTask(caseState, decision) {
  const outcome = (decision.source_outcomes || [])[0] || null;
  if (outcome && outcome.system === "system_2" && aidOrDenial(caseState, outcome)) return "sapling_verdict";
  if (outcome && outcome.system === "system_2") return "s2_action";
  return "s1_triage";
}

function closedOrNull(task, value) {
  if (typeof value !== "string" || !TASKS[task].includes(value)) return null;
  return value;
}

export function outputModel(task, decision) {
  if (task === "s2_action") return closedOrNull(task, decision.next_action);
  if (task !== "sapling_verdict") return null;
  const notes = [
    ...(decision.policy_notes || []),
    ...(decision.source_outcomes || []).flatMap((item) => [item && item.reasoning, item && item.reason]),
  ];
  for (const line of notes) {
    const match = String(line || "").match(/sapling_verdict=([a-z_]+)/);
    if (match) {
      const label = closedOrNull(task, match[1]);
      if (label) return label;
    }
  }
  return null;
}

export function describeInput(inputRef) {
  const turns = inputRef.turn_ids.length === 1 ? "1 turn" : inputRef.turn_ids.length + " turns";
  const policies = inputRef.policy_ids.length ? inputRef.policy_ids.join(", ") : "none";
  return (
    inputRef.case_id +
    " · " +
    turns +
    " · " +
    inputRef.lang +
    " · policies " +
    policies +
    " · memory " +
    (inputRef.memory_ref || "none")
  );
}

export function buildCorrectionBody({ caseState, decision, outputCorrect, reason, policyVersion }) {
  const task = inferTask(caseState, decision);
  const inputRef = buildInputRef(caseState);
  const model = outputModel(task, decision);
  const body = {
    corrected_by: "operator",
    field: task,
    new_value: outputCorrect,
    reason: reason.trim(),
    task,
    group_id: caseState.case_id,
    input_ref: inputRef,
    output_correct: outputCorrect,
    source: "human",
    model_version: MODEL_VERSION[task],
  };
  if (model) {
    body.old_value = model;
    body.output_model = model;
  }
  if (policyVersion) body.policy_version = policyVersion;
  return body;
}

export async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  let payload = {};
  try {
    payload = await response.json();
  } catch (error) {
    payload = {};
  }
  if (!response.ok) {
    const detail = payload && payload.detail;
    throw new Error(typeof detail === "string" && detail ? detail : url + " returned " + response.status);
  }
  return payload;
}

export async function submitCorrection({ fixtureId, caseState, decision, outputCorrect, reason, policyVersion }) {
  const body = buildCorrectionBody({ caseState, decision, outputCorrect, reason, policyVersion });
  let caseId = body.input_ref.case_id;
  if (fixtureId) {
    const created = await postJson("/cases", { fixture_id: fixtureId });
    caseId = created.case.case_id;
    if (caseId !== body.input_ref.case_id) {
      body.input_ref = { ...body.input_ref, case_id: caseId };
      body.group_id = caseId;
    }
  }
  return postJson("/cases/" + encodeURIComponent(caseId) + "/corrections", body);
}

function optionText(task, value, labelNames) {
  if (task === "s1_triage" && labelNames && labelNames[value]) return labelNames[value];
  return value.replaceAll("_", " ");
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

export function mountCorrectForm(parent, options) {
  const task = inferTask(options.caseState, options.decision);
  const inputRef = buildInputRef(options.caseState);
  const form = document.createElement("form");
  form.className = "correct-form";
  form.setAttribute("aria-label", "Correct this");
  form.dataset.task = task;
  form.dataset.inputRef = JSON.stringify(inputRef);

  form.append(el("h3", null, "Correct this"));
  form.append(el("p", "correct-auto", "Task and the case link are filled from this call."));
  const facts = document.createElement("dl");
  facts.className = "correct-facts";
  facts.append(el("dt", null, "Task"));
  facts.append(el("dd", null, task));
  facts.append(el("dt", null, "Input"));
  facts.append(el("dd", null, describeInput(inputRef)));
  form.append(facts);

  const valueLabel = el("label", "correct-field");
  valueLabel.append(el("span", null, "Correct value"));
  const select = document.createElement("select");
  select.name = "output_correct";
  select.required = true;
  const blank = document.createElement("option");
  blank.value = "";
  blank.textContent = "Choose the correct value";
  select.append(blank);
  for (const value of TASKS[task]) {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = optionText(task, value, options.labelNames);
    select.append(option);
  }
  valueLabel.append(select);
  form.append(valueLabel);

  const reasonLabel = el("label", "correct-field");
  reasonLabel.append(el("span", null, "Reason"));
  const reason = document.createElement("textarea");
  reason.name = "reason";
  reason.required = true;
  reason.rows = 3;
  reasonLabel.append(reason);
  form.append(reasonLabel);

  const button = el("button", null, "Correct this");
  button.type = "submit";
  form.append(button);
  const status = el("p", "correct-status", options.note ? options.note.text : "");
  if (options.note && options.note.ok === false) status.classList.add("correct-error");
  form.append(status);

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    button.disabled = true;
    status.classList.remove("correct-error");
    status.textContent = "Sending the correction.";
    try {
      const result = await submitCorrection({
        fixtureId: options.fixtureId,
        caseState: options.caseState,
        decision: options.decision,
        outputCorrect: select.value,
        reason: reason.value,
        policyVersion: options.policyVersion || "",
      });
      const logged = result.correction && result.correction.output_correct;
      status.textContent = logged ? "Logged " + logged + "." : "Logged.";
      if (options.onResult) {
        options.onResult({ ok: true, text: status.textContent, decision: result.decision || null });
      }
    } catch (error) {
      status.classList.add("correct-error");
      status.textContent = error.message;
      button.disabled = false;
      if (options.onResult) options.onResult({ ok: false, text: error.message, decision: null });
    }
  });

  parent.append(form);
  return form;
}
