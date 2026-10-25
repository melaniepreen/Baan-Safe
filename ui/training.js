// Training page. Plain JS, no dependencies. Reads GET /training and draws
// cards, tables, and two inline SVG charts (loss per version, reward per epoch).
// A second fetch, GET /training/compare, draws the "Memory off vs on" card from
// two committed RL snapshots; if it fails the rest of the page still renders.
// Nothing here calls Mubit; the numbers come from the API's trace and file reads.

(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  function fmtInt(value) {
    if (value === null || value === undefined) return "—";
    return Number(value).toLocaleString("en-US");
  }

  function fmtNum(value, digits) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return Number(value).toFixed(digits === undefined ? 3 : digits);
  }

  function fmtMs(value) {
    if (value === null || value === undefined) return "—";
    return Math.round(Number(value)).toLocaleString("en-US") + " ms";
  }

  function fmtPct(value) {
    if (value === null || value === undefined) return "—";
    return Math.round(Number(value) * 100) + "%";
  }

  function fmtTime(iso) {
    if (!iso) return "—";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return String(iso);
    return date.toISOString().replace("T", " ").slice(0, 16) + "Z";
  }

  function fmtDelta(value, digits) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    const text = digits === undefined ? fmtInt(value) : fmtNum(value, digits);
    return Number(value) > 0 ? "+" + text : text;
  }

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else node.setAttribute(key, value);
    }
    for (const child of children || []) {
      if (child === null || child === undefined) continue;
      node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    }
    return node;
  }

  function card(label, value, sub, alert) {
    const valueNode = el("div", { class: "value" + (String(value).length > 9 ? " small" : ""), text: value });
    return el("div", { class: "card" + (alert ? " alert" : "") }, [
      el("div", { class: "label", text: label }),
      valueNode,
      sub ? el("div", { class: "sub", text: sub }) : null,
    ]);
  }

  function table(columns, rows, onPick) {
    if (!rows.length) return el("p", { class: "empty", text: "nothing recorded yet" });
    const head = el("tr", {}, columns.map((c) => el("th", { class: c.num ? "num" : "", text: c.label })));
    const body = el("tbody");
    rows.forEach((row, index) => {
      const tr = el("tr", { class: onPick ? "pick" : "" }, columns.map((c) => {
        const raw = typeof c.get === "function" ? c.get(row) : row[c.key];
        return el("td", { class: c.num ? "num" : "", text: raw === undefined || raw === null ? "—" : String(raw) });
      }));
      if (onPick) tr.addEventListener("click", () => onPick(row, index, tr));
      body.appendChild(tr);
    });
    return el("table", {}, [el("thead", {}, [head]), body]);
  }

  // ---- SVG line chart -------------------------------------------------------

  function lineChart(points, options) {
    const width = 720;
    const height = options.height || 260;
    const pad = { left: 56, right: 16, top: 16, bottom: 36 };
    const svgNS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(svgNS, "svg");
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    svg.setAttribute("role", "img");
    svg.setAttribute("aria-label", options.title || "chart");
    if (!points.length) {
      const text = document.createElementNS(svgNS, "text");
      text.setAttribute("x", width / 2);
      text.setAttribute("y", height / 2);
      text.setAttribute("text-anchor", "middle");
      text.setAttribute("fill", "#666");
      text.textContent = options.emptyText || "no data";
      svg.appendChild(text);
      return svg;
    }
    const xs = points.map((p) => p.x);
    const ys = points.map((p) => p.y);
    const xMin = Math.min(...xs);
    const xMax = Math.max(...xs);
    let yMin = Math.min(...ys);
    let yMax = Math.max(...ys);
    if (options.zeroLine) { yMin = Math.min(yMin, 0); yMax = Math.max(yMax, 0); }
    if (yMax === yMin) { yMax += 1; yMin -= 1; }
    const span = yMax - yMin;
    yMin -= span * 0.05;
    yMax += span * 0.05;
    const plotW = width - pad.left - pad.right;
    const plotH = height - pad.top - pad.bottom;
    const sx = (x) => pad.left + (xMax === xMin ? plotW / 2 : ((x - xMin) / (xMax - xMin)) * plotW);
    const sy = (y) => pad.top + plotH - ((y - yMin) / (yMax - yMin)) * plotH;

    function add(tag, attrs, text) {
      const node = document.createElementNS(svgNS, tag);
      for (const [k, v] of Object.entries(attrs)) node.setAttribute(k, v);
      if (text !== undefined) node.textContent = text;
      svg.appendChild(node);
      return node;
    }

    // axes + gridlines
    const ticks = 4;
    for (let i = 0; i <= ticks; i += 1) {
      const y = yMin + ((yMax - yMin) * i) / ticks;
      add("line", { x1: pad.left, x2: width - pad.right, y1: sy(y), y2: sy(y), stroke: "#e4e4e4", "stroke-width": 1 });
      add("text", { x: pad.left - 8, y: sy(y) + 4, "text-anchor": "end", "font-size": 12, fill: "#666" }, y.toFixed(options.yDigits === undefined ? 2 : options.yDigits));
    }
    if (options.zeroLine) {
      add("line", { x1: pad.left, x2: width - pad.right, y1: sy(0), y2: sy(0), stroke: "#999", "stroke-dasharray": "4 4" });
    }
    add("line", { x1: pad.left, x2: pad.left, y1: pad.top, y2: pad.top + plotH, stroke: "#1b1b1b" });
    add("line", { x1: pad.left, x2: width - pad.right, y1: pad.top + plotH, y2: pad.top + plotH, stroke: "#1b1b1b" });
    const xLabels = points.length <= 12 ? points : [points[0], points[Math.floor(points.length / 2)], points[points.length - 1]];
    for (const p of xLabels) {
      add("text", { x: sx(p.x), y: height - 12, "text-anchor": "middle", "font-size": 12, fill: "#666" }, String(p.x));
    }
    add("text", { x: width / 2, y: height - 0, "text-anchor": "middle", "font-size": 12, fill: "#666" }, options.xLabel || "");

    // line + points
    const d = points.map((p, i) => `${i === 0 ? "M" : "L"}${sx(p.x).toFixed(1)},${sy(p.y).toFixed(1)}`).join(" ");
    add("path", { d, fill: "none", stroke: "#0b3d91", "stroke-width": 2.5 });
    if (points.length <= 60) {
      for (const p of points) add("circle", { cx: sx(p.x), cy: sy(p.y), r: 3.5, fill: "#0b3d91" });
    }
    return svg;
  }

  // ---- sections -------------------------------------------------------------

  function renderMubit(m) {
    const host = $("mubit-cards");
    host.replaceChildren(
      card("Requests", fmtInt(m.call_count), "mubit_chat trace rows"),
      card("Sessions", fmtInt(m.distinct_sessions), "distinct case ids (session_id)"),
      card("OK", fmtInt(m.ok_count), m.cache_hit_count ? fmtInt(m.cache_hit_count) + " cache hits" : "live replies"),
      card("Errors", fmtInt(m.error_count), "http_* or no reply", Number(m.error_count) > 0),
      card("Latency p50", fmtMs(m.p50_latency_ms), "p95 " + fmtMs(m.p95_latency_ms)),
      card("Tokens", fmtInt((m.tokens_in_total || 0) + (m.tokens_out_total || 0)), fmtInt(m.tokens_in_total) + " in · " + fmtInt(m.tokens_out_total) + " out"),
    );
    const models = Object.entries(m.models || {}).map(([name, n]) => `${name} ×${n}`).join(", ");
    $("mubit-window").textContent = m.first_call_at ? `${fmtTime(m.first_call_at)} → ${fmtTime(m.last_call_at)}` : "";
    $("mubit-note").textContent = (models ? "Model: " + models + ". " : "") + (m.note || "") +
      (m.kept_example_threshold ? ` Mubit keeps an example once it clears the ${m.kept_example_threshold}-example threshold.` : "");
  }

  function renderFinetune(f) {
    $("finetune-decided").textContent = `base ${f.decided.base_model} · gpu ${f.decided.gpu} · ${f.registry_path}`;
    const columns = [
      { label: "Version", key: "version_id" },
      { label: "Task", key: "task" },
      { label: "Role", key: "role" },
      { label: "Base model", key: "base_model" },
      { label: "GPU", key: "gpu" },
      { label: "Steps", key: "steps", num: true },
      { label: "Rows", key: "rows", num: true },
      { label: "First loss", num: true, get: (r) => fmtNum(r.first_loss) },
      { label: "Last loss", num: true, get: (r) => fmtNum(r.last_loss) },
      { label: "Min loss", num: true, get: (r) => fmtNum(r.min_loss) },
      { label: "Held-out acc", num: true, get: (r) => fmtPct(r.heldout_accuracy) },
      { label: "Status", key: "status" },
      { label: "Created", get: (r) => fmtTime(r.created_at) },
    ];
    let selectedRow = null;
    const node = table(columns, f.versions, (row, _index, tr) => {
      if (selectedRow) selectedRow.classList.remove("selected");
      selectedRow = tr;
      tr.classList.add("selected");
      renderLoss(row);
    });
    $("finetune-table").replaceChildren(node);
    const first = f.versions.find((v) => v.loss_curve && v.loss_curve.length) || f.versions[0] || null;
    renderLoss(first);
    if (first && node.tBodies && node.tBodies[0]) {
      const index = f.versions.indexOf(first);
      const tr = node.tBodies[0].rows[index];
      if (tr) { tr.classList.add("selected"); selectedRow = tr; }
    }
  }

  function renderLoss(version) {
    const host = $("loss-chart");
    if (!version) {
      host.replaceChildren(
        el("h3", { text: "Loss curve" }),
        el("p", { class: "empty", text: "no fine-tune version on the registry yet — make modal-finetune writes one" }),
      );
      return;
    }
    const curve = (version.loss_curve || []).map((p) => ({ x: Number(p.step), y: Number(p.loss) }));
    const title = `Loss · ${version.version_id} · ${version.task || "?"} · ${version.trainer || ""}`;
    const subtitle = [
      version.steps !== null && version.steps !== undefined ? `${version.steps} steps` : null,
      version.rows !== null && version.rows !== undefined ? `${version.rows} rows` : null,
      version.wall_seconds ? `${fmtNum(version.wall_seconds, 1)} s` : null,
      version.metrics && version.metrics.loss_source ? `source ${version.metrics.loss_source}` : null,
      version.heldout_accuracy !== null && version.heldout_accuracy !== undefined ? `held-out ${fmtPct(version.heldout_accuracy)}` : null,
    ].filter(Boolean).join(" · ");
    host.replaceChildren(
      el("h3", { text: title }),
      el("p", { class: "meta", text: subtitle || version.notes || "" }),
      lineChart(curve, { title, xLabel: "step", yDigits: 3, emptyText: "this version has no loss_curve (dry run or older job)" }),
    );
  }

  function renderRl(rl) {
    $("rl-meta").textContent = rl.schema ? `${rl.s2 || ""} · ${rl.model || ""} · ${rl.run_path}` : rl.run_path || "";
    const columns = [
      { label: "Epoch", key: "epoch", num: true },
      { label: "Episodes", key: "episodes", num: true },
      { label: "Mean reward", num: true, get: (r) => fmtNum(r.mean_reward) },
      { label: "Correct", key: "correct", num: true },
      { label: "Under", key: "under_triage", num: true },
      { label: "Critical under", key: "critical_under", num: true },
      { label: "S1", num: true, get: (r) => fmtPct(r.share_s1_only) },
      { label: "Cascade", num: true, get: (r) => fmtPct(r.share_cascade) },
      { label: "S2", num: true, get: (r) => fmtPct(r.share_s2_only) },
      { label: "Fallbacks", key: "s2_fallbacks", num: true },
    ];
    $("rl-table").replaceChildren(table(columns, rl.epochs));
    const overlay = rl.overlay || {};
    const mubit = rl.mubit || {};
    $("overlay-cards").replaceChildren(
      card("Graduated", fmtInt(overlay.graduated), `threshold ${fmtInt(overlay.graduation_threshold)}`),
      card("Recommended", fmtInt(overlay.recommendations), "P1 / complex, back to S2"),
      card("Demoted", fmtInt(overlay.demoted), "coarse signatures to S2"),
      card("Mubit in run", fmtInt(mubit.live_ok), `${fmtInt(mubit.cache_hits)} cache · ${fmtInt(mubit.errors)} errors · ${fmtMs(mubit.avg_latency_ms)}`),
    );
    const points = rl.epochs.map((e) => ({ x: Number(e.epoch), y: Number(e.mean_reward) })).filter((p) => !Number.isNaN(p.y));
    $("reward-chart").replaceChildren(
      el("h3", { text: "Mean reward per epoch" }),
      el("p", { class: "meta", text: rl.finetune ? `fine-tune: ${rl.finetune}` : (rl.training && rl.training.status ? `training export: ${rl.training.status}` : "") }),
      lineChart(points, { title: "Mean reward per epoch", xLabel: "epoch", zeroLine: true, yDigits: 2, height: 200, emptyText: "no RL run yet — make rl-loop or make rl-loop-replay" }),
    );
  }

  // Memory off vs on: two RL snapshots, last epoch of each. `lowerIsBetter`
  // decides which direction of the delta turns the card red.
  const COMPARE_METRICS = [
    { key: "critical_under", label: "Critical under-triage", lowerIsBetter: true },
    { key: "mean_reward", label: "Mean reward", digits: 3 },
    { key: "correct", label: "Correct" },
  ];

  function renderCompare(result) {
    const a = result.a || {};
    const b = result.b || {};
    const headline = result.headline || {};
    $("compare-meta").textContent = `A ${a.name || "?"} · B ${b.name || "?"}`;
    const cards = COMPARE_METRICS.map((metric) => {
      const cell = headline[metric.key] || {};
      const fmt = (v) => (metric.digits === undefined ? fmtInt(v) : fmtNum(v, metric.digits));
      const delta = cell.delta;
      const worse = delta !== null && delta !== undefined && (metric.lowerIsBetter ? Number(delta) > 0 : Number(delta) < 0);
      return card(
        metric.label,
        `${fmt(cell.a)} → ${fmt(cell.b)}`,
        `Δ ${fmtDelta(delta, metric.digits)} · ${metric.lowerIsBetter ? "lower" : "higher"} is better`,
        worse,
      );
    });
    $("compare-cards").replaceChildren(...cards);
    const side = (row, key, digits) => {
      if (!row) return "—";
      return digits === undefined ? fmtInt(row[key]) : fmtNum(row[key], digits);
    };
    const columns = [
      { label: "Epoch", key: "epoch", num: true },
      { label: "Critical under A", num: true, get: (r) => side(r.a, "critical_under") },
      { label: "Critical under B", num: true, get: (r) => side(r.b, "critical_under") },
      { label: "Reward A", num: true, get: (r) => side(r.a, "mean_reward", 3) },
      { label: "Reward B", num: true, get: (r) => side(r.b, "mean_reward", 3) },
      { label: "Correct A", num: true, get: (r) => side(r.a, "correct") },
      { label: "Correct B", num: true, get: (r) => side(r.b, "correct") },
      { label: "Under A", num: true, get: (r) => side(r.a, "under_triage") },
      { label: "Under B", num: true, get: (r) => side(r.b, "under_triage") },
    ];
    $("compare-table").replaceChildren(table(columns, result.per_epoch || []));
  }

  function renderCompareEmpty(message) {
    $("compare-meta").textContent = "";
    $("compare-cards").replaceChildren(el("p", { class: "empty", text: message }));
    $("compare-table").replaceChildren();
  }

  function renderEvents(ev) {
    const cards = [card("Events", fmtInt(ev.total), ev.events_path)];
    for (const [task, n] of Object.entries(ev.by_task || {})) cards.push(card(task, fmtInt(n), "by task"));
    for (const [source, n] of Object.entries(ev.by_source || {})) cards.push(card(source, fmtInt(n), "by source"));
    $("event-cards").replaceChildren(...cards);
    const columns = [
      { label: "Manifest", key: "path" },
      { label: "Events", key: "event_count", num: true },
      { label: "Schema", key: "schema_version", num: true },
      { label: "Policy pin", get: (r) => (r.policy_version ? String(r.policy_version).slice(0, 12) : "—") },
      { label: "Hash", get: (r) => (r.hash ? String(r.hash).slice(0, 12) : "—") },
    ];
    $("manifests").replaceChildren(el("h3", { text: "Export manifests", class: "meta" }), table(columns, ev.manifests || []));
  }

  function renderMissing(list) {
    const host = $("missing");
    host.replaceChildren();
    if (!list.length) {
      host.appendChild(el("li", { text: "every optional file was present" }));
      return;
    }
    for (const path of list) host.appendChild(el("li", { class: "mono", text: path }));
  }

  async function load() {
    try {
      const response = await fetch("/training");
      if (!response.ok) throw new Error("/training returned " + response.status);
      const body = await response.json();
      renderMubit(body.mubit_traffic || {});
      renderFinetune(body.finetune || { versions: [], decided: {} });
      renderRl(body.rl || { epochs: [] });
      renderEvents(body.events || {});
      renderMissing(body.missing || []);
      $("status").textContent = "";
    } catch (error) {
      $("status").textContent = error.message;
    }
  }

  // Separate from load(): a missing snapshot folder must not blank the page.
  async function loadCompare() {
    try {
      const response = await fetch("/training/compare");
      if (!response.ok) throw new Error("/training/compare returned " + response.status);
      renderCompare(await response.json());
    } catch (error) {
      renderCompareEmpty("no snapshots — make rl-snapshot after make rl-loop (" + error.message + ")");
    }
  }

  load();
  loadCompare();
})();
