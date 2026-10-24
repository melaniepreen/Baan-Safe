/* Learning loop panel for the town demo.

   Reads GET /rl/run — the report written by `make rl-loop` or
   `python -m eval.rl`. On a 404 it shows "No run yet — run `make rl-loop`".
   This is a read-only viewer; the loop itself is off the live path.
*/

const THEME_NAMES = {
  "RL-ROAD": "road-info",
  "RL-COLD": "cold-hall",
  "RL-GRAN": "quiet-grandmother",
  "RL-UP": "upstairs-water",
  "RL-WEAK": "weak-grandfather-water",
  "RL-RICE": "rice",
  "RL-AID": "aid-list",
  "RL-DOOR": "fine-but-door",
};

const SHORT_KEYS = [
  ["needs=", "needs "],
  ["vuln=", "vulnerable "],
  ["danger=", "danger "],
  ["medical=", "medical "],
  ["loc=", "location "],
  ["people=", "people "],
  ["flags=", "flags "],
  ["|text=", " · text "],
];

let state = { run: null, epoch: null, status: "idle", error: null };

function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

function themeName(caseId) {
  for (const prefix of Object.keys(THEME_NAMES)) {
    if (String(caseId || "").startsWith(prefix)) return THEME_NAMES[prefix];
  }
  return String(caseId || "");
}

function shortSignature(sig) {
  let text = String(sig || "");
  for (const [long, short] of SHORT_KEYS) text = text.split(long).join(short);
  if (text.length > 80) text = text.slice(0, 77) + "…";
  return text;
}

function epochs(run) {
  return (run && run.epochs) || [];
}

function episodesFor(run, epoch) {
  const rows = (run && run.episodes) || [];
  if (epoch == null) return rows;
  return rows.filter((row) => row.epoch === epoch);
}

function eventsFor(run, epoch) {
  const rows = (run && run.events) || [];
  if (epoch == null) return rows;
  return rows.filter((row) => row.epoch === epoch);
}

function describeEvent(event) {
  const name = themeName(event.case_id);
  if (event.kind === "graduate") {
    return `${name} graduated to System 1 after ${event.wins || 2} matching System 2 decisions`;
  }
  if (event.kind === "demote") {
    return `${name} demoted to System 2: System 1 said ${event.priority || "?"}, truth was different`;
  }
  if (event.kind === "recommend") {
    return `${name} is complex: System 1 now passes System 2 a recommendation`;
  }
  return `${event.kind} on ${name}`;
}

function shareBar(rows) {
  const total = rows.length || 1;
  const counts = { s1: 0, cascade: 0, s2: 0 };
  for (const row of rows) {
    if (row.cascaded) counts.cascade += 1;
    else if ((row.systems || [])[0] === "system_2") counts.s2 += 1;
    else counts.s1 += 1;
  }
  const bar = el("div", "rl-share-bar");
  const legend = el("p", "muted");
  const parts = [
    ["S1 only", counts.s1, "s1"],
    ["S1→S2 cascade", counts.cascade, "cascade"],
    ["S2 direct", counts.s2, "s2"],
  ];
  const labels = [];
  for (const [label, count, cls] of parts) {
    const seg = el("span", "rl-seg " + cls);
    seg.style.width = `${(count / total) * 100}%`;
    seg.title = `${label}: ${count}`;
    bar.append(seg);
    labels.push(`${label} ${Math.round((count / total) * 100)}%`);
  }
  legend.textContent = labels.join(" · ");
  const wrap = el("div");
  wrap.append(bar, legend);
  return wrap;
}

function sparkline(run) {
  const list = epochs(run);
  const wrap = el("div", "rl-spark");
  if (!list.length) {
    wrap.append(el("p", "muted", "No epochs."));
    return wrap;
  }
  const w = 220;
  const h = 56;
  const rewards = list.map((row) => row.mean_reward);
  const min = Math.min(...rewards);
  const max = Math.max(...rewards);
  const span = max - min || 1;
  const points = list
    .map((row, i) => {
      const x = (i / Math.max(1, list.length - 1)) * (w - 8) + 4;
      const y = h - 6 - ((row.mean_reward - min) / span) * (h - 14);
      return `${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", `0 0 ${w} ${h}`);
  svg.setAttribute("class", "rl-sparkline");
  const line = document.createElementNS("http://www.w3.org/2000/svg", "polyline");
  line.setAttribute("points", points);
  svg.append(line);
  for (const [i, row] of list.entries()) {
    const x = (i / Math.max(1, list.length - 1)) * (w - 8) + 4;
    const y = h - 6 - ((row.mean_reward - min) / span) * (h - 14);
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", String(x.toFixed(1)));
    dot.setAttribute("cy", String(y.toFixed(1)));
    dot.setAttribute("r", "3");
    svg.append(dot);
  }
  wrap.append(svg);
  const caption = list
    .map(
      (row) =>
        `epoch ${row.epoch}: reward ${row.mean_reward}, ` +
        `under-triage ${row.under_triage}, critical-under ${row.critical_under}`,
    )
    .join("  ·  ");
  wrap.append(el("p", "muted", caption));
  return wrap;
}

function overlayTable(overlay) {
  const wrap = el("div");
  const sections = [
    ["Graduated to System 1", overlay && overlay.graduated],
    ["Recommendations passed to System 2", overlay && overlay.recommendations],
    ["Demoted to System 2", overlay && overlay.demoted],
  ];
  for (const [title, entries] of sections) {
    wrap.append(el("h3", null, title));
    const rows = Object.entries(entries || {});
    if (!rows.length) {
      wrap.append(el("p", "muted", "None."));
      continue;
    }
    const table = el("table", "rl-table");
    const body = el("tbody");
    for (const [sig, entry] of rows) {
      const tr = el("tr");
      tr.append(el("td", "rl-sig", shortSignature(sig)));
      const detail = entry.priority
        ? `${entry.priority} · ${entry.route || ""}` +
          (entry.requires_human ? " · human" : "")
        : entry.reason || "";
      tr.append(el("td", null, detail));
      body.append(tr);
    }
    table.append(body);
    wrap.append(table);
  }
  return wrap;
}

function render(root) {
  const panel = document.getElementById("rl-panel");
  if (!panel) return;
  panel.replaceChildren();
  if (state.status === "loading") {
    panel.append(el("p", "loading", "Loading the learning loop report…"));
    return;
  }
  if (state.status === "missing") {
    panel.append(el("p", "loading", "No run yet — run `make rl-loop`."));
    return;
  }
  if (state.status === "error") {
    panel.append(el("p", "loading", "Could not load /rl/run: " + state.error));
    return;
  }
  const run = state.run;
  const head = el("div", "feed-head");
  const title = el("div");
  title.append(el("p", "kicker", "Learning loop"), el("h2", null, "RL run"));
  const badge = el("span", "sim-badge rl-badge");
  badge.textContent =
    `${run.s2 || "?"} mode` +
    (run.notes && run.notes.length ? "" : "");
  head.append(title, badge);
  panel.append(head);
  panel.append(
    el(
      "p",
      "muted",
      `model nvidia/nemotron-3.5-lightning:free · epochs ${epochs(run).length} · seed ${run.seed}`,
    ),
  );

  const stepper = el("div", "wordmark-actions rl-stepper");
  const prev = el("button", null, "← epoch");
  const all = el("button", null, "all");
  const next = el("button", null, "epoch →");
  const label = el("span", "muted rl-epoch-label");
  const mark = () => {
    label.textContent = state.epoch == null ? "all epochs" : `epoch ${state.epoch}`;
  };
  const move = (delta) => {
    const list = epochs(run);
    if (!list.length) return;
    const ids = list.map((row) => row.epoch);
    const index = state.epoch == null ? -1 : ids.indexOf(state.epoch);
    const nextIndex = (index + delta + list.length) % list.length;
    state.epoch = ids[nextIndex];
    mark();
    render(root);
  };
  prev.type = "button";
  all.type = "button";
  next.type = "button";
  prev.addEventListener("click", () => move(-1));
  next.addEventListener("click", () => move(1));
  all.addEventListener("click", () => {
    state.epoch = null;
    mark();
    render(root);
  });
  stepper.append(prev, all, next, label);
  panel.append(stepper);
  mark();

  panel.append(el("h3", null, "Who answered"));
  panel.append(shareBar(episodesFor(run, state.epoch)));
  panel.append(el("h3", null, "Reward and triage"));
  panel.append(sparkline(run));
  panel.append(el("h3", null, "Learning events"));
  const list = el("ol", "rl-events");
  for (const event of eventsFor(run, state.epoch)) {
    list.append(el("li", null, describeEvent(event)));
  }
  panel.append(list);
  panel.append(el("h3", null, "Final overlay"));
  panel.append(overlayTable(run.final_overlay));
}

async function loadRun(root) {
  state.status = "loading";
  render(root);
  try {
    const response = await fetch("/rl/run");
    if (response.status === 404) {
      state = { ...state, status: "missing", run: null };
    } else if (!response.ok) {
      state = { ...state, status: "error", error: `HTTP ${response.status}` };
    } else {
      state = { ...state, status: "ok", run: await response.json(), epoch: null };
    }
  } catch (err) {
    state = { ...state, status: "error", error: String(err && err.message ? err.message : err) };
  }
  render(root);
}

export function initRlPanel(root) {
  const button = document.getElementById("rl-open");
  const panel = document.getElementById("rl-panel");
  if (!button || !panel) return;
  button.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    if (!panel.hidden && !state.run) loadRun(root);
  });
  const refresh = document.getElementById("rl-refresh");
  if (refresh) refresh.addEventListener("click", () => loadRun(root));
}
