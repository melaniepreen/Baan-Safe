// Training page polish. Plain JS, no dependencies, loaded after training.js.
// Adds a Hugging Face Hub link to every fine-tune version row and a per-label
// held-out table for the newest s1_triage version that carries
// metrics.heldout.per_label. training.js keeps its fetched document private, so
// this file reads GET /training once more. Nothing here calls a model, and the
// Hub links are plain anchors: a blocked or private repo only changes what the
// browser shows after the click, never this page.

(function () {
  "use strict";

  var HUB = {
    s1_triage: "https://huggingface.co/baansafe/baansafe-s1-triage-setfit",
    s2_lora: "https://huggingface.co/baansafe/baansafe-s2-nemotron-nano-4b-lora",
  };
  var HUB_TEXT = "Hub";

  function el(tag, attrs, children) {
    var node = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (key) {
      var value = attrs[key];
      if (key === "class") node.className = value;
      else if (key === "text") node.textContent = value;
      else node.setAttribute(key, value);
    });
    (children || []).forEach(function (child) {
      if (child === null || child === undefined) return;
      node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
    });
    return node;
  }

  function fmtNum(value, digits) {
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return Number(value).toFixed(digits === undefined ? 3 : digits);
  }

  function fmtPlain(value) {
    // 0.875 -> "0.875", 0.9 -> "0.9": the caption quotes the number, not a padded figure.
    if (value === null || value === undefined || Number.isNaN(Number(value))) return "—";
    return String(Math.round(Number(value) * 1000) / 1000);
  }

  // ---- hub links -----------------------------------------------------------

  function hubUrl(version) {
    if (!version) return null;
    var task = String(version.task || "").toLowerCase();
    var role = String(version.role || "").toLowerCase();
    if (task === "s1_triage") return HUB.s1_triage;
    if (task === "sft" || role.indexOf("s2") >= 0) return HUB.s2_lora;
    return null;
  }

  function hubCell(version) {
    var url = hubUrl(version);
    if (!url) return el("td", { class: "hub", text: "—" });
    var link = el("a", {
      class: "hub-link",
      href: url,
      target: "_blank",
      rel: "noopener noreferrer",
      title: url,
      text: HUB_TEXT,
    });
    return el("td", { class: "hub" }, [link]);
  }

  function decorateVersionsTable(host, versions) {
    var table = host.querySelector("table");
    if (!table || table.dataset.hubLinks === "done") return;
    var headRow = table.tHead && table.tHead.rows[0];
    if (!headRow) return;
    var byId = {};
    versions.forEach(function (v) { byId[String(v.version_id)] = v; });
    headRow.appendChild(el("th", { text: "Hub" }));
    var body = table.tBodies[0];
    if (body) {
      Array.prototype.forEach.call(body.rows, function (tr) {
        var id = tr.cells[0] ? tr.cells[0].textContent.trim() : "";
        tr.appendChild(hubCell(byId[id] || null));
      });
    }
    table.dataset.hubLinks = "done";
  }

  // ---- held-out per-label table ---------------------------------------------

  function newestHeldout(versions) {
    // versions arrive newest first; keep that order and take the first s1_triage
    // row with a per-label block.
    for (var i = 0; i < versions.length; i += 1) {
      var v = versions[i];
      var heldout = v && v.metrics && v.metrics.heldout;
      if (String(v.task || "") !== "s1_triage") continue;
      if (!heldout || !heldout.per_label || !Object.keys(heldout.per_label).length) continue;
      return v;
    }
    return null;
  }

  function perLabelRows(perLabel) {
    return Object.keys(perLabel)
      .map(function (label) {
        var row = perLabel[label] || {};
        return {
          label: label,
          support: row.support === undefined ? null : Number(row.support),
          precision: row.precision === undefined ? null : row.precision,
          recall: row.recall === undefined ? null : row.recall,
        };
      })
      .sort(function (a, b) {
        var diff = (b.support || 0) - (a.support || 0);
        return diff !== 0 ? diff : a.label.localeCompare(b.label);
      });
  }

  function caption(heldout) {
    var rows = heldout.rows === undefined || heldout.rows === null ? "?" : Number(heldout.rows).toLocaleString("en-US");
    return rows + " held-out synthetic rows, accuracy " + fmtPlain(heldout.accuracy);
  }

  function renderHeldout(version) {
    var existing = document.getElementById("heldout-labels");
    var anchor = document.getElementById("loss-chart") || document.getElementById("finetune-table");
    if (!anchor) return;
    var host = existing || el("div", { class: "chart heldout-labels", id: "heldout-labels" });
    if (!existing) anchor.insertAdjacentElement("afterend", host);
    if (!version) {
      host.replaceChildren(
        el("h3", { text: "Held-out per label" }),
        el("p", { class: "empty", text: "no s1_triage version with metrics.heldout.per_label yet" }),
      );
      return;
    }
    var heldout = version.metrics.heldout;
    var rows = perLabelRows(heldout.per_label);
    var head = el("tr", {}, [
      el("th", { text: "Label" }),
      el("th", { class: "num", text: "Support" }),
      el("th", { class: "num", text: "Precision" }),
      el("th", { class: "num", text: "Recall" }),
    ]);
    var body = el("tbody", {}, rows.map(function (r) {
      return el("tr", {}, [
        el("td", { class: "mono", text: r.label }),
        el("td", { class: "num", text: r.support === null ? "—" : String(r.support) }),
        el("td", { class: "num", text: fmtNum(r.precision) }),
        el("td", { class: "num", text: fmtNum(r.recall) }),
      ]);
    }));
    var hub = hubUrl(version);
    host.replaceChildren(
      el("h3", { text: "Held-out per label · " + version.version_id }),
      el("p", { class: "meta heldout-caption", text: caption(heldout) + (hub ? " · " : "") }, [
        hub ? el("a", { class: "hub-link", href: hub, target: "_blank", rel: "noopener noreferrer", text: HUB_TEXT }) : null,
      ]),
      el("div", { class: "scroll" }, [el("table", {}, [el("thead", {}, [head]), body])]),
    );
  }

  // ---- load -----------------------------------------------------------------

  function apply(versions) {
    var host = document.getElementById("finetune-table");
    if (!host) return;
    decorateVersionsTable(host, versions);
    // training.js may not have drawn the table yet, or may redraw it later.
    var observer = new MutationObserver(function () { decorateVersionsTable(host, versions); });
    observer.observe(host, { childList: true });
    renderHeldout(newestHeldout(versions));
  }

  async function load() {
    try {
      var response = await fetch("/training");
      if (!response.ok) return;
      var body = await response.json();
      var versions = (body.finetune && body.finetune.versions) || [];
      apply(versions);
    } catch (error) {
      // training.js already reports the fetch error in #status; stay quiet here.
    }
  }

  load();
})();
