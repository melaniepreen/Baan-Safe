/* The About dialog's system diagram: one inline SVG, no renderer, no assets.
   `aboutDiagramSvg()` is a pure string builder so node can check it. */

const FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, sans-serif";
const BG = "#0c1220";
const BOX = "#121a28";
const EDGE = "#314056";
const INK = "#e6edf5";
const SUB = "#9aa8bb";
const LINE = "#5b6b85";
const TEAL = "#12A594";
const VIOLET = "#8E4EC6";
const AMBER = "#FFC53D";

function esc(value) {
  return String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function label(text, dy, extra) {
  return { text, dy, size: 12, fill: INK, weight: 600, ...(extra || {}) };
}

function sub(text, dy, extra) {
  return { text, dy, size: 10, fill: SUB, weight: 400, ...(extra || {}) };
}

function textLine(cx, y, line) {
  const fit = line.fit ? ` textLength="${line.fit}" lengthAdjust="spacingAndGlyphs"` : "";
  return (
    `<text x="${cx}" y="${y}" text-anchor="middle" font-size="${line.size}"` +
    ` font-weight="${line.weight}" fill="${line.fill}"${fit}>${esc(line.text)}</text>`
  );
}

function box({ x, y, w, h, stroke = EDGE, dashed = false, lines }) {
  const dash = dashed ? ` stroke-dasharray="4 3"` : "";
  const parts = [
    `<rect x="${x}" y="${y}" width="${w}" height="${h}" rx="6" fill="${BOX}"` +
      ` stroke="${stroke}" stroke-width="1.25"${dash}/>`,
  ];
  const cx = x + w / 2;
  for (const line of lines) parts.push(textLine(cx, y + line.dy, line));
  return parts.join("");
}

function arrow(d, stroke, marker) {
  return `<path d="${d}" fill="none" stroke="${stroke}" stroke-width="1.5" marker-end="url(#${marker})"/>`;
}

function marker(id, fill) {
  return (
    `<marker id="${id}" viewBox="0 0 10 10" refX="10" refY="5" markerWidth="8" markerHeight="8"` +
    ` markerUnits="userSpaceOnUse" orient="auto"><path d="M0 0L10 5L0 10z" fill="${fill}"/></marker>`
  );
}

export function aboutDiagramSvg() {
  const row = { y: 40, h: 64 };
  const parts = [];
  parts.push(`<rect width="640" height="220" rx="6" fill="${BG}"/>`);

  // Main row, left to right.
  parts.push(
    box({ x: 6, w: 74, ...row, lines: [label("Call", 24), sub("phone · text", 39), sub("saved prompt", 51)] })
  );
  parts.push(
    box({
      x: 94,
      w: 104,
      ...row,
      lines: [label("Gateway", 24), sub("extract · enrich", 39), sub("case memory", 51)],
    })
  );
  parts.push(
    box({
      x: 394,
      w: 120,
      ...row,
      stroke: AMBER,
      lines: [label("A person approves", 28, { fit: 108 }), sub("every P1 · every denial", 43, { fit: 108 })],
    })
  );
  parts.push(
    box({
      x: 528,
      w: 108,
      ...row,
      lines: [
        label("Boat · information", 19, { fit: 98 }),
        label("· merged", 33),
        sub("stock held", 47),
        sub("no second boat", 59),
      ],
    })
  );

  // Fork column: System 1 on top, System 2 below, Mubit gateway under System 2.
  parts.push(
    box({
      x: 228,
      y: 14,
      w: 150,
      h: 46,
      stroke: TEAL,
      lines: [label("System 1 · rules", 19), sub("deterministic · ms · no model", 34, { fit: 138 })],
    })
  );
  parts.push(
    box({
      x: 228,
      y: 72,
      w: 150,
      h: 64,
      stroke: VIOLET,
      lines: [
        label("System 2 · Nemotron", 18),
        label("via Mubit", 32),
        sub("open-weight · traced", 46),
        sub("a person approves", 58),
      ],
    })
  );
  parts.push(
    `<path d="M303 136V145" fill="none" stroke="${VIOLET}" stroke-width="1.25" stroke-dasharray="3 3"/>`
  );
  parts.push(
    box({
      x: 228,
      y: 146,
      w: 150,
      h: 46,
      stroke: VIOLET,
      dashed: true,
      lines: [label("Mubit gateway", 17), sub("records every call", 30), sub("trains a per-task adapter", 41)],
    })
  );

  // Forward arrows.
  parts.push(arrow("M80 72H93", LINE, "bs-arrow"));
  parts.push(arrow("M198 72C213 72 213 37 227 37", LINE, "bs-arrow"));
  parts.push(arrow("M198 72C213 72 213 104 227 104", LINE, "bs-arrow"));
  parts.push(arrow("M378 37C386 37 386 64 393 64", LINE, "bs-arrow"));
  parts.push(arrow("M378 104C386 104 386 80 393 80", LINE, "bs-arrow"));
  parts.push(arrow("M514 72H527", LINE, "bs-arrow"));

  // Return loop along the bottom, Boat back into System 1, hopping the Gateway -> System 2 arrow.
  parts.push(
    arrow(
      "M582 104V192Q582 202 572 202H230Q220 202 220 192V107A6.5 6.5 0 0 1 220 94V50H227",
      TEAL,
      "bs-arrow-teal"
    )
  );
  parts.push(
    textLine(401, 216, {
      text: "corrections → training log → fine-tune · RL graduation into rules",
      size: 10,
      fill: TEAL,
      weight: 500,
    })
  );

  return (
    `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 640 220" width="640" height="220"` +
    ` role="img" aria-labelledby="bs-about-diagram-title" style="font-family:${FONT}">` +
    `<title id="bs-about-diagram-title">How a call moves through BaanSafe</title>` +
    `<defs>${marker("bs-arrow", LINE)}${marker("bs-arrow-teal", TEAL)}</defs>` +
    parts.join("") +
    `</svg>`
  );
}

function wireStart() {
  const start = document.getElementById("about-start");
  if (!start || start.dataset.wired) return;
  start.dataset.wired = "1";
  start.addEventListener("click", () => {
    document.getElementById("about").close();
    document.getElementById("prompts-toggle")?.click();
  });
}

export async function mountAbout(host) {
  if (host) {
    host.replaceChildren();
    host.insertAdjacentHTML("afterbegin", aboutDiagramSvg());
  }
  wireStart();
}

export function stopAbout() {
  // Nothing to tear down: the diagram is static markup. Safe to call any number of times.
}
