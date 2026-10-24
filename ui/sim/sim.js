/* Fixed-camera town, drawn with PixiJS.

   World metres: x east, y south (toward the camera), z up.
   Iso pixels: ((x - y), (x + y) / 2 - z). Pixi only pans and zooms that
   picture. The heading never changes.

   Houses, streets, flood polygons, and routes come from ./data.
*/
import { mountCorrectForm } from "../correct.js";
import { needsOperatorApproval } from "./approval.js";
import { callSummary } from "./call_title.js";
import { decidePath, PATTERN_KEY, withTop } from "./patterns.js";
import { legsFromPath, nearestNode, walk } from "./route_walk.js";
import { Application, Container, Graphics, Text } from "./vendor/pixi.min.mjs";

const STATUSES = ["clear", "at_risk", "flooded", "needs_help", "evacuated"];
const YELLOW = 0xd6ff3c;
const INK = 0x07090f;

const ROOF = {
  red: 0xe24b3a,
  blue: 0x3d7eb8,
  grey: 0x9aa3b2,
  pink: 0xf0a0b8,
  brown: 0x8a5534,
  brown_tiered: 0x6e4326,
  flat_white: 0xd5dbe8,
  flat_pink: 0xf2b3c4,
  stupa: 0xf4efe4,
};

const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const scene = document.getElementById("scene");

let town = null;
let streets = [];
let flood = null;
let streetById = {};
let nodeById = {};
let selected = null;
let floodLevel = 0;
let floodMax = 1;
let trips = [];
let moverClock = 0;
let responses = null;
let eventsFile = null;
let promptFile = null;
let rulebook = null;
let replies = null;
let clinicNode = null;
let hospitalCache = new Map();
let review = null;
let flowToken = 0;
let callStartedAt = 0;
let callTimerHandle = 0;
const LOG_KEY = "baansafe.sim.decision-log";
let phoneCases = new Map();
let caseStates = new Map();
let live = {
  health: null,
  resources: null,
  context: null,
  triage: null,
  triageError: null,
  labels: null,
  correctionNote: null,
};

let app;
let world;
let floodG;
let routeG;
let routeGroundG;
let selectG;
let records;
let markerG;
let didDrag = false;
let drag = null;
let labels = [];
let callResults = new Map();
let callCursor = 0;
let callPlaying = false;
let callToken = 0;
let callChain = Promise.resolve();
let callGeneration = 0;
let activeCallId = null;
let callLightG = null;

const PRIORITY_COLOR = { P1: "#ff4b3a", P2: "#ff9f1a", P3: "#d6ff3c", P4: "#8aa0ff" };
const PRIORITY_HEX = { P1: 0xff4b3a, P2: 0xff9f1a, P3: 0xd6ff3c, P4: 0x8aa0ff };
const PLAIN_PRIORITY = {
  P1: "urgent rescue",
  P2: "evacuation",
  P3: "welfare or shelter",
  P4: "information",
};
const STEP_META = {
  memory: { icon: "M", kicker: "Mubit" },
  tool: { icon: "T", kicker: "Tool" },
  system_1: { icon: "1", kicker: "System 1" },
  handoff: { icon: "→", kicker: "Handoff" },
  system_2: { icon: "2", kicker: "System 2 · Nemotron" },
  sapling: { icon: "S", kicker: "Sapling" },
  router: { icon: "R", kicker: "Decision router" },
  operator_approval: { icon: "A", kicker: "Operator approval" },
  dispatch: { icon: "D", kicker: "Dispatch" },
  rule: { icon: "D", kicker: "Dispatch" },
};

function hashId(id) {
  let h = 2166136261;
  for (let i = 0; i < id.length; i++) {
    h ^= id.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function shift(color, amount) {
  const ch = (shiftBy) => Math.max(0, Math.min(255, ((color >> shiftBy) & 255) + amount));
  return (ch(16) << 16) | (ch(8) << 8) | ch(0);
}

function mix(color, toward, t) {
  const ch = (shiftBy) =>
    Math.round(((color >> shiftBy) & 255) * (1 - t) + ((toward >> shiftBy) & 255) * t);
  return (ch(16) << 16) | (ch(8) << 8) | ch(0);
}

function project(x, y, z = 0) {
  return [(x - y), (x + y) * 0.5 - z];
}

function flat(points) {
  const out = [];
  for (const point of points) out.push(point[0], point[1]);
  return out;
}

function quad(x0, y0, z0, x1, y1, z1, x2, y2, z2, x3, y3, z3) {
  return [project(x0, y0, z0), project(x1, y1, z1), project(x2, y2, z2), project(x3, y3, z3)];
}

function pip(x, y, poly) {
  let inside = false;
  for (let i = 0, j = poly.length - 1; i < poly.length; j = i++) {
    const yi = poly[i][1];
    const yj = poly[j][1];
    if (yi > y !== yj > y) {
      const xCross = ((poly[j][0] - poly[i][0]) * (y - yi)) / (yj - yi + 1e-9) + poly[i][0];
      if (x < xCross) inside = !inside;
    }
  }
  return inside;
}

function fillPoly(g, points, color, alpha = 1) {
  g.poly(flat(points), true).fill({ color, alpha });
}

function strokePoly(g, points, color, width) {
  g.poly(flat(points), true).stroke({ color, width, join: "round", cap: "round" });
}

function glowPoly(g, points, color, width, alpha) {
  g.poly(flat(points), true).stroke({ color, width, alpha, join: "round", cap: "round" });
}

function mix3(a, b, t) {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t, a[2] + (b[2] - a[2]) * t];
}

function solidPath(g, pts, color, width) {
  if (pts.length < 2) return;
  g.moveTo(pts[0][0], pts[0][1]);
  for (let i = 1; i < pts.length; i++) g.lineTo(pts[i][0], pts[i][1]);
  g.stroke({ width, color, cap: "round", join: "round" });
}

function dashPath(g, pts, color, width, dash, gap, offset) {
  const period = dash + gap;
  let phase = ((offset % period) + period) % period;
  let drawing = phase < dash;
  let remain = drawing ? dash - phase : period - phase;
  let started = false;
  for (let i = 1; i < pts.length; i++) {
    let ax = pts[i - 1][0];
    let ay = pts[i - 1][1];
    const bx = pts[i][0];
    const by = pts[i][1];
    let seg = Math.hypot(bx - ax, by - ay);
    if (seg < 0.001) continue;
    const ux = (bx - ax) / seg;
    const uy = (by - ay) / seg;
    while (seg > 0.001) {
      const take = Math.min(seg, remain);
      const nx = ax + ux * take;
      const ny = ay + uy * take;
      if (drawing) {
        g.moveTo(ax, ay);
        g.lineTo(nx, ny);
        started = true;
      }
      ax = nx;
      ay = ny;
      seg -= take;
      remain -= take;
      if (remain <= 0.001) {
        drawing = !drawing;
        remain = drawing ? dash : gap;
      }
    }
  }
  if (started) g.stroke({ width, color, cap: "round" });
}

function pointAlong(pts, distance) {
  let left = distance;
  for (let i = 1; i < pts.length; i++) {
    const seg = Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
    if (left <= seg) {
      const t = seg === 0 ? 0 : left / seg;
      return [pts[i - 1][0] + (pts[i][0] - pts[i - 1][0]) * t, pts[i - 1][1] + (pts[i][1] - pts[i - 1][1]) * t];
    }
    left -= seg;
  }
  return pts[pts.length - 1];
}

function pathLength(pts) {
  let total = 0;
  for (let i = 1; i < pts.length; i++) total += Math.hypot(pts[i][0] - pts[i - 1][0], pts[i][1] - pts[i - 1][1]);
  return total;
}

function roofColor(building) {
  const base = ROOF[building.roof] || ROOF.grey;
  let color = shift(base, (hashId(building.id) % 11) - 5);
  if (building.sim_status === "evacuated") color = mix(color, 0x6a7080, 0.55);
  if (building.sim_status === "flooded") color = mix(color, 0x4a4038, 0.35);
  return color;
}

function wallPair(building) {
  if (building.wall === "wood" || building.kind === "wood_house" || building.kind === "temple" || building.kind === "jetty") {
    return [0x8a5a3c, 0x684228];
  }
  if (building.kind === "concrete" || building.kind === "school" || building.kind === "clinic" || building.roof === "flat_white" || building.roof === "flat_pink") {
    return [0xd5deee, 0xb7c3d6];
  }
  return [0x2c3d6b, 0x1b2948];
}

const ROOF_BANDS = [
  [0, 0.1, 0x9aa3b2],
  [0.1, 0.34, 0xc23b32],
  [0.34, 0.52, 0x1d4a38],
  [0.52, 0.68, 0xe2a23a],
  [0.68, 0.86, 0x1d4a38],
  [0.86, 1, 0xc23b32],
];

function bandSlope(g, eave0, eave1, ridge0, ridge1, shade) {
  for (const [t0, t1, color] of ROOF_BANDS) {
    const a = mix3(eave0, ridge0, t0);
    const b = mix3(eave1, ridge1, t0);
    const c = mix3(eave1, ridge1, t1);
    const d = mix3(eave0, ridge0, t1);
    fillPoly(g, [project(a[0], a[1], a[2]), project(b[0], b[1], b[2]), project(c[0], c[1], c[2]), project(d[0], d[1], d[2])], shift(color, shade));
  }
}

function chofa(g, eave, toward) {
  const dx = toward[0] - eave[0];
  const dy = toward[1] - eave[1];
  const len = Math.hypot(dx, dy) || 1;
  const ux = dx / len;
  const uy = dy / len;
  const px = -uy;
  const py = ux;
  const bend = [eave[0] + ux * 3.2 + px * 2.2, eave[1] + uy * 3.2 + py * 2.2];
  const tip = [eave[0] - ux * 1.2 + px * 4.2, eave[1] - uy * 1.2 + py * 4.2];
  g.moveTo(eave[0], eave[1]).lineTo(bend[0], bend[1]).lineTo(tip[0], tip[1]).stroke({ width: 1.45, color: 0xe2a23a, cap: "round", join: "round" });
  g.circle(tip[0], tip[1], 1.15).fill({ color: 0xe2a23a });
}

function paintBandedGable(g, box, z1, rise, overhang) {
  const x = box.x - overhang;
  const y = box.y - overhang * 0.35;
  const w = box.w + overhang * 1.45;
  const d = box.d + overhang * 1.15;
  const ridgeY = y + d * 0.46;
  const ridgeZ = z1 + rise;
  const eaveS0 = [x, y + d, z1];
  const eaveS1 = [x + w, y + d, z1];
  const eaveN0 = [x, y, z1];
  const eaveN1 = [x + w, y, z1];
  const ridge0 = [x, ridgeY, ridgeZ];
  const ridge1 = [x + w, ridgeY, ridgeZ];
  bandSlope(g, eaveN0, eaveN1, ridge0, ridge1, -30);
  bandSlope(g, eaveS0, eaveS1, ridge0, ridge1, 0);
  const south = [project(x, y + d, z1), project(x + w, y + d, z1), project(x + w, ridgeY, ridgeZ), project(x, ridgeY, ridgeZ)];
  const north = [project(x, y, z1), project(x + w, y, z1), project(x + w, ridgeY, ridgeZ), project(x, ridgeY, ridgeZ)];
  const east = [project(x + w, y, z1), project(x + w, y + d, z1), project(x + w, ridgeY, ridgeZ)];
  fillPoly(g, east, 0x8e2e28);
  const inner = [project(x + w, y + d * 0.18, z1 + rise * 0.08), project(x + w, y + d * 0.82, z1 + rise * 0.08), project(x + w, ridgeY, ridgeZ - rise * 0.08)];
  fillPoly(g, inner, 0xe2a23a);
  strokePoly(g, south, 0x9aa3b2, 1.15);
  const ridgeA = project(x, ridgeY, ridgeZ);
  const ridgeB = project(x + w, ridgeY, ridgeZ);
  g.moveTo(ridgeA[0], ridgeA[1]).lineTo(ridgeB[0], ridgeB[1]).stroke({ width: 1.5, color: 0xe2a23a, cap: "round" });
  chofa(g, project(x, y + d, z1), project(x, ridgeY, ridgeZ));
  chofa(g, project(x + w, y + d, z1), project(x + w, ridgeY, ridgeZ));
  chofa(g, project(x, y, z1), project(x, ridgeY, ridgeZ));
  chofa(g, project(x + w, y, z1), project(x + w, ridgeY, ridgeZ));
  chofa(g, ridgeA, project(x - 1.2, ridgeY, ridgeZ + 1.1));
  chofa(g, ridgeB, project(x + w + 1.2, ridgeY, ridgeZ + 1.1));
  return { south, north, east, topZ: ridgeZ, ridgeY, x, w };
}

function paintWat(g, building) {
  const x = building.x;
  const y = building.y;
  const w = building.w;
  const d = building.d;
  const tiers = building.tiers || 3;
  const pad = Math.min(1.1, w * 0.06);
  const zP = 0.9;
  const plinthS = quad(x - pad, y + d + pad, 0, x + w + pad, y + d + pad, 0, x + w + pad, y + d + pad, zP, x - pad, y + d + pad, zP);
  const plinthE = quad(x + w + pad, y - pad, 0, x + w + pad, y + d + pad, 0, x + w + pad, y + d + pad, zP, x + w + pad, y - pad, zP);
  const plinthTop = quad(x - pad, y - pad, zP, x + w + pad, y - pad, zP, x + w + pad, y + d + pad, zP, x - pad, y + d + pad, zP);
  fillPoly(g, plinthE, 0xd9d3c8);
  fillPoly(g, plinthS, 0xf7f4ee);
  fillPoly(g, plinthTop, 0xfffaf4);
  for (let step = 0; step < 3; step++) {
    const sy = y + d + pad + 1.7 - step * 0.55;
    const inset = w * 0.04 * step;
    const sx0 = x + w * 0.26 + inset;
    const sx1 = x + w * 0.74 - inset;
    const z0 = (zP / 3) * step;
    const z1s = (zP / 3) * (step + 1);
    fillPoly(g, quad(sx0, sy, z0, sx1, sy, z0, sx1, sy, z1s, sx0, sy, z1s), step === 1 ? 0xc23b32 : 0xf3efe6);
    fillPoly(g, quad(sx0, sy - 0.42, z1s, sx1, sy - 0.42, z1s, sx1, sy, z1s, sx0, sy, z1s), 0xfffaf4);
  }
  const zW = zP + Math.max(2.6, Math.min(4.4, d * 0.22));
  const wallS = quad(x, y + d, zP, x + w, y + d, zP, x + w, y + d, zW, x, y + d, zW);
  const wallE = quad(x + w, y, zP, x + w, y + d, zP, x + w, y + d, zW, x + w, y, zW);
  fillPoly(g, wallE, 0xe4d9c4);
  fillPoly(g, wallS, 0xf4efe4);
  const bays = Math.max(2, Math.min(4, Math.round(w / 8)));
  for (let bay = 0; bay < bays; bay++) {
    const t0 = (bay + 0.22) / bays;
    const t1 = (bay + 0.78) / bays;
    const sill = zP + 0.55;
    const head = zW - 0.55;
    fillPoly(g, quad(x + w * t0, y + d, sill, x + w * t1, y + d, sill, x + w * t1, y + d, head, x + w * t0, y + d, head), 0xe2a23a);
    const margin = (t1 - t0) * 0.16;
    fillPoly(
      g,
      quad(x + w * (t0 + margin), y + d, sill + 0.16, x + w * (t1 - margin), y + d, sill + 0.16, x + w * (t1 - margin), y + d, head - 0.14, x + w * (t0 + margin), y + d, head - 0.14),
      0xc23b32
    );
  }
  const cols = Math.max(4, Math.min(6, Math.round(w / 5)));
  for (let i = 0; i < cols; i++) {
    const cx = x + (w * (i + 0.5)) / cols;
    const cy = y + d + 0.28;
    fillPoly(g, quad(cx - 0.32, cy, zP, cx + 0.32, cy, zP, cx + 0.32, cy, zW - 0.05, cx - 0.32, cy, zW - 0.05), 0x1d4a38);
    fillPoly(g, quad(cx - 0.38, cy, zP + 0.12, cx + 0.38, cy, zP + 0.12, cx + 0.38, cy, zP + 0.38, cx - 0.38, cy, zP + 0.38), 0xe2a23a);
    fillPoly(g, quad(cx - 0.38, cy, zW - 0.48, cx + 0.38, cy, zW - 0.48, cx + 0.38, cy, zW - 0.2, cx - 0.38, cy, zW - 0.2), 0xe2a23a);
    const lamp = project(cx, cy + 0.05, zP + (zW - zP) * 0.48);
    g.circle(lamp[0], lamp[1], 1.25).fill({ color: 0xffe08a });
  }
  const pedZ0 = zW - 1.2;
  const pedZ1 = zW + 0.25;
  const ped = [project(x + w * 0.28, y + d + 0.08, pedZ0), project(x + w * 0.72, y + d + 0.08, pedZ0), project(x + w * 0.5, y + d + 0.08, pedZ1)];
  fillPoly(g, ped, 0xc23b32);
  fillPoly(g, [project(x + w * 0.36, y + d + 0.1, pedZ0 + 0.22), project(x + w * 0.64, y + d + 0.1, pedZ0 + 0.22), project(x + w * 0.5, y + d + 0.1, pedZ1 - 0.16)], 0xe2a23a);
  const rise = Math.max(1.7, d * 0.11);
  const roofs = [];
  let crown = null;
  for (let i = 0; i < tiers; i++) {
    const shrink = i * Math.min(w, d) * 0.13;
    const box = {
      x: x + shrink,
      y: y + shrink * 0.55,
      w: Math.max(4, w - shrink * 2),
      d: Math.max(3.2, d - shrink * 1.2),
    };
    const z = zW + i * (rise + 0.85);
    const parts = paintBandedGable(g, box, z, rise, 0.8);
    if (i === 0 || i === tiers - 1) roofs.push(parts.south, parts.north, parts.east);
    crown = parts;
  }
  const portico = paintBandedGable(
    g,
    { x: x + w * 0.22, y: y + d * 0.78, w: w * 0.56, d: Math.max(3.2, d * 0.34) },
    zW - 0.2,
    rise * 0.72,
    0.4
  );
  if (crown) {
    const tip = project(x + w / 2, crown.ridgeY, crown.topZ + 2.1);
    const foot = project(x + w / 2, crown.ridgeY, crown.topZ + 0.15);
    g.moveTo(foot[0], foot[1]).lineTo(tip[0], tip[1]).stroke({ width: 1.5, color: 0xe2a23a, cap: "round" });
    g.circle(tip[0], tip[1], 1.7).fill({ color: 0xe2a23a });
  }
  return [plinthS, plinthE, wallS, wallE, portico.south, ...roofs];
}

function stiltTone(building) {
  const name = building.stilt || ["teak", "dark", "amber"][hashId(building.id) % 3];
  if (name === "dark") {
    return { wall: 0x4a3428, wallE: 0x3a281e, deck: 0x5c3a28, deckShade: 0x3e291c, post: 0x3a281e, door: 0x2a1c14, roof: 0x6b4228, roofDark: 0x4a2c18, shutter: 0xc4894a };
  }
  if (name === "amber") {
    return { wall: 0x8a5534, wallE: 0x6e4328, deck: 0xa86838, deckShade: 0x7a4a28, post: 0x6b4632, door: 0x4a301c, roof: 0x8a5534, roofDark: 0x6b3e24, shutter: 0xe2c08a };
  }
  return { wall: 0x6b4632, wallE: 0x543828, deck: 0x8a5534, deckShade: 0x6b4228, post: 0x5c3a28, door: 0x3a2418, roof: 0x7a4e30, roofDark: 0x5c3a22, shutter: 0xd7b07a };
}

function tileSlope(g, eave0, eave1, ridge0, ridge1, color, dark) {
  const bands = 5;
  for (let i = 0; i < bands; i++) {
    const t0 = i / bands;
    const t1 = (i + 1) / bands;
    const a = mix3(eave0, ridge0, t0);
    const b = mix3(eave1, ridge1, t0);
    const c = mix3(eave1, ridge1, t1);
    const d = mix3(eave0, ridge0, t1);
    fillPoly(g, [project(a[0], a[1], a[2]), project(b[0], b[1], b[2]), project(c[0], c[1], c[2]), project(d[0], d[1], d[2])], i % 2 ? dark : color);
  }
}

function roofFinial(g, x, y, z) {
  const base = project(x, y, z);
  const up = project(x, y, z + 0.9);
  const curl = project(x, y - 0.45, z + 1.25);
  g.moveTo(base[0], base[1]).lineTo(up[0], up[1]).lineTo(curl[0], curl[1]).stroke({ width: 1.35, color: 0xe2a23a, cap: "round", join: "round" });
}

function paintTileRoof(g, box, z1, color, dark, rise) {
  const x = box.x;
  const y = box.y;
  const w = box.w;
  const d = box.d;
  const ridgeY = y + d * 0.42;
  const ridgeZ = z1 + rise;
  const eaveS0 = [x, y + d, z1];
  const eaveS1 = [x + w, y + d, z1];
  const eaveN0 = [x, y, z1];
  const eaveN1 = [x + w, y, z1];
  const ridge0 = [x, ridgeY, ridgeZ];
  const ridge1 = [x + w, ridgeY, ridgeZ];
  tileSlope(g, eaveN0, eaveN1, ridge0, ridge1, shift(color, -18), shift(dark, -12));
  tileSlope(g, eaveS0, eaveS1, ridge0, ridge1, color, dark);
  const south = [project(x, y + d, z1), project(x + w, y + d, z1), project(x + w, ridgeY, ridgeZ), project(x, ridgeY, ridgeZ)];
  const north = [project(x, y, z1), project(x + w, y, z1), project(x + w, ridgeY, ridgeZ), project(x, ridgeY, ridgeZ)];
  const east = [project(x + w, y, z1), project(x + w, y + d, z1), project(x + w, ridgeY, ridgeZ)];
  fillPoly(g, east, dark);
  strokePoly(g, south, 0x2a1c14, 1.05);
  for (let i = 1; i <= 4; i++) {
    const t = i / 5;
    const a = project(x + w * t, y + d, z1);
    const b = project(x + w * t, ridgeY, ridgeZ);
    g.moveTo(a[0], a[1]).lineTo(b[0], b[1]).stroke({ width: 0.7, color: dark, alpha: 0.85 });
  }
  const ridgeA = project(x, ridgeY, ridgeZ);
  const ridgeB = project(x + w, ridgeY, ridgeZ);
  g.moveTo(ridgeA[0], ridgeA[1]).lineTo(ridgeB[0], ridgeB[1]).stroke({ width: 1.2, color: shift(color, 24), cap: "round" });
  roofFinial(g, x, ridgeY, ridgeZ);
  roofFinial(g, x + w, ridgeY, ridgeZ);
  return [south, north, east];
}

function paintStilt(g, building) {
  const tone = stiltTone(building);
  const x = building.x;
  const y = building.y;
  const w = building.w;
  const d = building.d;
  const deckZ = 1.5;
  const wallH = 2.15 + Math.min(2, building.floors) * 0.45;
  const z1 = deckZ + wallH;
  const posts = [
    [x + 0.4, y + 0.35],
    [x + w - 0.4, y + 0.35],
    [x + 0.4, y + d + 1.15],
    [x + w - 0.4, y + d + 1.15],
    [x + w * 0.5, y + d + 1.15],
  ];
  for (const [px, py] of posts) {
    fillPoly(g, quad(px - 0.16, py, 0, px + 0.16, py, 0, px + 0.16, py, deckZ, px - 0.16, py, deckZ), tone.post);
  }
  const deckS = quad(x - 0.35, y + d + 1.55, deckZ - 0.28, x + w + 0.25, y + d + 1.55, deckZ - 0.28, x + w + 0.25, y + d + 1.55, deckZ, x - 0.35, y + d + 1.55, deckZ);
  const deckE = quad(x + w + 0.25, y - 0.25, deckZ - 0.28, x + w + 0.25, y + d + 1.55, deckZ - 0.28, x + w + 0.25, y + d + 1.55, deckZ, x + w + 0.25, y - 0.25, deckZ);
  const deckTop = quad(x - 0.35, y - 0.25, deckZ, x + w + 0.25, y - 0.25, deckZ, x + w + 0.25, y + d + 1.55, deckZ, x - 0.35, y + d + 1.55, deckZ);
  fillPoly(g, deckE, tone.deckShade);
  fillPoly(g, deckS, tone.deck);
  fillPoly(g, deckTop, shift(tone.deck, 16));
  const wallS = quad(x + 0.2, y + d, deckZ, x + w - 0.15, y + d, deckZ, x + w - 0.15, y + d, z1, x + 0.2, y + d, z1);
  const wallE = quad(x + w - 0.15, y + 0.2, deckZ, x + w - 0.15, y + d, deckZ, x + w - 0.15, y + d, z1, x + w - 0.15, y + 0.2, z1);
  fillPoly(g, wallE, tone.wallE);
  fillPoly(g, wallS, tone.wall);
  const doorW = Math.min(1.5, w * 0.24);
  const dx0 = x + w * 0.4;
  fillPoly(g, quad(dx0, y + d, deckZ + 0.04, dx0 + doorW, y + d, deckZ + 0.04, dx0 + doorW, y + d, deckZ + wallH * 0.72, dx0, y + d, deckZ + wallH * 0.72), tone.door);
  const shutter = (t0, t1) => {
    const sill = deckZ + wallH * 0.28;
    const head = deckZ + wallH * 0.64;
    fillPoly(g, quad(x + w * t0, y + d, sill, x + w * t1, y + d, sill, x + w * t1, y + d, head, x + w * t0, y + d, head), tone.shutter);
  };
  shutter(0.1, 0.28);
  shutter(0.66, 0.86);
  const roof = paintTileRoof(g, { x: x - 0.45, y: y - 0.35, w: w + 0.85, d: d + 0.35 }, z1, tone.roof, tone.roofDark, Math.max(2.15, d * 0.28));
  const leanZ0 = z1 * 0.72 + deckZ * 0.28;
  const leanZ1 = deckZ + 0.85;
  const lx0 = x - 0.2;
  const lx1 = x + w + 0.15;
  const ly0 = y + d * 0.62;
  const ly1 = y + d + 1.6;
  const lean = [project(lx0, ly1, leanZ1), project(lx1, ly1, leanZ1), project(lx1, ly0, leanZ0), project(lx0, ly0, leanZ0)];
  fillPoly(g, lean, tone.roofDark);
  strokePoly(g, lean, 0x2a1c14, 0.9);
  const leanE = [project(lx1, ly0, leanZ0), project(lx1, ly1, leanZ1), project(lx1, ly1, deckZ + 0.2)];
  fillPoly(g, leanE, shift(tone.roofDark, -20));
  return [deckS, deckE, wallS, wallE, ...roof, lean];
}

function paintBuilding(g, building) {
  if (building.kind === "temple") return paintWat(g, building);
  if (building.kind === "stilt" || building.kind === "wood_house") return paintStilt(g, building);
  const floorH = building.kind === "concrete" || building.kind === "school" ? 3.35 : building.kind === "wood_house" || building.kind === "temple" ? 3.05 : 3.45;
  const z0 = 0.45;
  const z1 = z0 + Math.max(1, building.floors) * floorH;
  const [southC, eastC] = wallPair(building);
  const plinthS = quad(building.x - 0.15, building.y + building.d + 0.15, 0, building.x + building.w + 0.15, building.y + building.d + 0.15, 0, building.x + building.w + 0.15, building.y + building.d + 0.15, z0, building.x - 0.15, building.y + building.d + 0.15, z0);
  const plinthE = quad(building.x + building.w + 0.15, building.y - 0.15, 0, building.x + building.w + 0.15, building.y + building.d + 0.15, 0, building.x + building.w + 0.15, building.y + building.d + 0.15, z0, building.x + building.w + 0.15, building.y - 0.15, z0);
  fillPoly(g, plinthE, 0x070b14);
  fillPoly(g, plinthS, 0x0c1220);
  const south = quad(building.x, building.y + building.d, z0, building.x + building.w, building.y + building.d, z0, building.x + building.w, building.y + building.d, z1, building.x, building.y + building.d, z1);
  const east = quad(building.x + building.w, building.y, z0, building.x + building.w, building.y + building.d, z0, building.x + building.w, building.y + building.d, z1, building.x + building.w, building.y, z1);
  fillPoly(g, east, eastC);
  fillPoly(g, south, southC);
  if (building.water_m > 0.05) {
    const zW = Math.min(z1 - 0.25, z0 + building.water_m);
    fillPoly(g, quad(building.x, building.y + building.d, z0, building.x + building.w, building.y + building.d, z0, building.x + building.w, building.y + building.d, zW, building.x, building.y + building.d, zW), 0x6a4e34, 0.55);
    fillPoly(g, quad(building.x + building.w, building.y, z0, building.x + building.w, building.y + building.d, z0, building.x + building.w, building.y + building.d, zW, building.x + building.w, building.y, zW), 0x543c28, 0.55);
  }
  paintWindows(g, building, z0, floorH, z1);
  const tops = paintRoof(g, building, z1);
  return [south, east].concat(tops);
}

function paintWindows(g, building, z0, floorH, z1) {
  const lightWall = building.kind === "concrete" || building.kind === "school" || building.kind === "clinic";
  const lit = lightWall ? 0x1a2438 : 0xb7e4ff;
  const bays = Math.max(1, Math.min(building.kind === "school" ? 14 : 4, Math.round(building.w / 3.4)));
  for (let floor = 0; floor < building.floors; floor++) {
    const sill = z0 + floor * floorH + 0.7;
    const head = sill + (building.kind === "shophouse" && floor === 0 ? floorH * 0.55 : 0.85);
    if (head > z1 - 0.2) continue;
    for (let bay = 0; bay < bays; bay++) {
      if (building.kind !== "school" && building.kind !== "concrete" && bay > 1) break;
      const t0 = (bay + 0.32) / bays;
      const t1 = (bay + 0.68) / bays;
      const accent = building.fixture_id && bay === 0 && floor === building.floors - 1;
      fillPoly(
        g,
        quad(building.x + building.w * t0, building.y + building.d, sill, building.x + building.w * t1, building.y + building.d, sill, building.x + building.w * t1, building.y + building.d, head, building.x + building.w * t0, building.y + building.d, head),
        accent ? YELLOW : lit
      );
    }
  }
}

function pitchedRoof(g, box, z1, color, rise, overhang) {
  const x = box.x - overhang;
  const y = box.y - overhang * 0.35;
  const w = box.w + overhang * 1.45;
  const d = box.d + overhang * 1.15;
  const ridgeY = y + d * 0.46;
  const ridgeZ = z1 + rise;
  const south = [project(x, y + d, z1), project(x + w, y + d, z1), project(x + w, ridgeY, ridgeZ), project(x, ridgeY, ridgeZ)];
  const north = [project(x, y, z1), project(x + w, y, z1), project(x + w, ridgeY, ridgeZ), project(x, ridgeY, ridgeZ)];
  const east = [project(x + w, y, z1), project(x + w, y + d, z1), project(x + w, ridgeY, ridgeZ)];
  fillPoly(g, east, shift(color, -42));
  fillPoly(g, north, shift(color, -16));
  fillPoly(g, south, color);
  const ridgeA = project(x, ridgeY, ridgeZ);
  const ridgeB = project(x + w, ridgeY, ridgeZ);
  g.moveTo(ridgeA[0], ridgeA[1]).lineTo(ridgeB[0], ridgeB[1]).stroke({ width: 1.3, color: shift(color, 28), cap: "round" });
  strokePoly(g, south, 0x07090f, 1.15);
  return [south, north, east];
}

function paintRoof(g, building, z1) {
  const color = roofColor(building);
  if (building.kind === "stupa" || building.roof === "stupa") {
    let z = z1;
    const tops = [];
    for (let step = 0; step < 4; step++) {
      const shrink = step * building.w * 0.14;
      const h = 1.35;
      fillPoly(g, quad(building.x + shrink, building.y + building.d - shrink, z, building.x + building.w - shrink, building.y + building.d - shrink, z, building.x + building.w - shrink, building.y + building.d - shrink, z + h, building.x + shrink, building.y + building.d - shrink, z + h), step % 2 ? 0xe7dcc4 : 0xf7f3ea);
      const top = quad(building.x + shrink, building.y + shrink, z + h, building.x + building.w - shrink, building.y + shrink, z + h, building.x + building.w - shrink, building.y + building.d - shrink, z + h, building.x + shrink, building.y + building.d - shrink, z + h);
      fillPoly(g, top, 0xf4efe4);
      tops.push(top);
      z += h;
    }
    return tops;
  }
  if (building.roof === "brown_tiered") {
    const tiers = building.tiers || 3;
    const tops = [];
    const rise = 2.05;
    const drum = 0.85;
    const step = rise + drum + 1.15;
    for (let i = 0; i < tiers; i++) {
      const shrink = i * Math.min(building.w, building.d) * 0.16;
      const z = z1 + i * step;
      const box = {
        x: building.x + shrink,
        y: building.y + shrink,
        w: Math.max(3, building.w - shrink * 2),
        d: Math.max(3, building.d - shrink * 2),
      };
      const south = quad(box.x, box.y + box.d, z, box.x + box.w, box.y + box.d, z, box.x + box.w, box.y + box.d, z + drum, box.x, box.y + box.d, z + drum);
      const east = quad(box.x + box.w, box.y, z, box.x + box.w, box.y + box.d, z, box.x + box.w, box.y + box.d, z + drum, box.x + box.w, box.y, z + drum);
      fillPoly(g, east, shift(0x6a4328, -10 * i));
      fillPoly(g, south, shift(0x8d5a34, -8 * i));
      const parts = pitchedRoof(g, box, z + drum, shift(0x7a4528, -8 * i), rise, 0.9);
      strokePoly(g, parts[0], YELLOW, i === tiers - 1 ? 0.7 : 0.5);
      tops.push(south, east, ...parts);
    }
    const cx = building.x + building.w / 2;
    const cy = building.y + building.d * 0.42;
    const topZ = z1 + (tiers - 1) * step + drum + rise;
    const tip = project(cx, cy, topZ + 1.8);
    const foot = project(cx, cy, topZ + 0.2);
    g.moveTo(foot[0], foot[1]).lineTo(tip[0], tip[1]).stroke({ width: 0.65, color: YELLOW, cap: "round" });
    return tops;
  }
  if (building.kind === "jetty") {
    const deck = quad(building.x, building.y, 0.35, building.x + building.w, building.y, 0.35, building.x + building.w, building.y + building.d, 0.35, building.x, building.y + building.d, 0.35);
    fillPoly(g, deck, 0x6d4b34);
    strokePoly(g, deck, YELLOW, 1.4);
    fillPoly(g, quad(building.x + building.w + 1.2, building.y + 2, 0.45, building.x + building.w + 8, building.y + 1.2, 0.7, building.x + building.w + 8, building.y + 3.6, 0.7, building.x + building.w + 1.2, building.y + 4.2, 0.45), 0x243456);
    return [deck];
  }
  const flat = building.roof === "flat_white" || building.roof === "flat_pink" || building.kind === "school" || building.kind === "concrete" || building.kind === "clinic" || building.kind === "shelter";
  if (flat) {
    const oh = building.kind === "school" ? 1.15 : 0.4;
    const rise = 0.55;
    const top = quad(building.x - oh, building.y - oh * 0.4, z1 + rise, building.x + building.w + oh * 0.5, building.y - oh * 0.4, z1 + rise, building.x + building.w + oh, building.y + building.d + oh, z1 + rise, building.x - oh, building.y + building.d + oh, z1 + rise);
    fillPoly(g, quad(building.x - oh, building.y + building.d + oh, z1, building.x + building.w + oh, building.y + building.d + oh, z1, building.x + building.w + oh, building.y + building.d + oh, z1 + rise, building.x - oh, building.y + building.d + oh, z1 + rise), shift(color, -28));
    fillPoly(g, top, color);
    strokePoly(g, top, building.kind === "house" ? 0x07090f : YELLOW, building.kind === "school" || building.kind === "concrete" ? 1.7 : 1.2);
    return [top];
  }
  const wood = building.kind === "wood_house" || building.wall === "wood";
  const parts = pitchedRoof(g, building, z1, color, wood ? 2.35 : 1.55, wood ? 0.7 : 0.4);
  if (wood || building.fixture_id) strokePoly(g, parts[0], YELLOW, building.fixture_id ? 1.8 : 1.35);
  return parts;
}

function treeKind(tree) {
  if (tree.kind === "banana" || tree.kind === "palm") return tree.kind;
  return hashId(tree.id || tree.x + ":" + tree.y) % 3 === 0 ? "banana" : "palm";
}

function paintPalm(g, tree) {
  const scale = Math.min(tree.r || 4.5, 8) / 5.2;
  const h = 5.4 * scale + 1.2;
  const lean = ((hashId(tree.id || "palm") % 7) - 3) * 0.15 * scale;
  const base = project(tree.x, tree.y, 0);
  const mid = project(tree.x + lean * 0.45, tree.y, h * 0.55);
  const top = project(tree.x + lean, tree.y, h);
  g.moveTo(base[0], base[1]).lineTo(mid[0], mid[1]).lineTo(top[0], top[1]).stroke({ width: 2.2 + scale, color: 0x6b4a32, cap: "round", join: "round" });
  for (let i = 0; i < 7; i++) {
    const ang = (i / 7) * Math.PI * 2;
    const dx = Math.cos(ang) * 2.5 * scale;
    const dy = Math.sin(ang) * 1.55 * scale;
    const tip = project(tree.x + lean + dx, tree.y + dy, h - 0.35);
    g.moveTo(top[0], top[1]).lineTo(tip[0], tip[1]).stroke({ width: 1.6, color: i % 2 ? 0x1f6a3c : 0x143526, cap: "round" });
  }
}

function paintBanana(g, tree) {
  const scale = Math.min(tree.r || 4.5, 8) / 5.5;
  const h = 3.4 * scale + 0.6;
  const base = project(tree.x, tree.y, 0);
  const top = project(tree.x, tree.y, h);
  g.moveTo(base[0], base[1]).lineTo(top[0], top[1]).stroke({ width: 3.6 + scale, color: 0x3d6b32, cap: "round" });
  const leaves = [
    [2.5, 0.35, 0.35, 0x2f8a45],
    [-2.3, 0.7, 0.05, 0x1f6a3c],
    [0.35, 2.1, 0.55, 0x3aaa58],
    [-0.5, -1.7, 0.25, 0x145c34],
  ];
  for (const [dx, dy, lift, color] of leaves) {
    const tip = project(tree.x + dx * scale, tree.y + dy * scale, h + lift);
    const mid = project(tree.x + dx * scale * 0.45, tree.y + dy * scale * 0.45, h * 0.72 + lift * 0.3);
    g.moveTo(top[0], top[1]).lineTo(mid[0], mid[1]).lineTo(tip[0], tip[1]).stroke({ width: 3.1, color, cap: "round", join: "round" });
  }
}

function paintTree(g, tree) {
  if (treeKind(tree) === "banana") paintBanana(g, tree);
  else paintPalm(g, tree);
}

function buildGround(g) {
  const w = town.meta.world.width_m;
  const d = town.meta.world.depth_m;
  const depth = 7;
  fillPoly(g, quad(0, d, -depth, w, d, -depth, w, d, 0, 0, d, 0), 0x080c16);
  fillPoly(g, quad(w, 0, -depth, w, d, -depth, w, d, 0, w, 0, 0), 0x0a101c);
  const step = 16;
  for (let x = 0; x < w; x += step) {
    for (let y = 0; y < d; y += step) {
      const alt = ((x / step + y / step) | 0) % 2 === 0;
      const tile = [project(x, y, 0), project(x + step, y, 0), project(x + step, y + step, 0), project(x, y + step, 0)];
      fillPoly(g, tile, alt ? 0x10182e : 0x0d1428);
      strokePoly(g, tile, 0x24345c, 0.35);
    }
  }
  g.poly(flat([project(0, 0, 0), project(w, 0, 0), project(w, d, 0), project(0, d, 0)]), true).stroke({
    color: 0x1a2748,
    width: 1,
  });
  const rim = [project(0, 0, 0.05), project(w, 0, 0.05), project(w, d, 0.05), project(0, d, 0.05)];
  strokePoly(g, rim, YELLOW, 2.4);
}

function roadRibbon(street) {
  const [a, b] = street.points;
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  const px = (-dy / len) * (street.width_m / 2);
  const py = (dx / len) * (street.width_m / 2);
  const z = 0.16;
  return {
    a, b, dx, dy, len, z,
    corners: [
      project(a[0] + px, a[1] + py, z),
      project(b[0] + px, b[1] + py, z),
      project(b[0] - px, b[1] - py, z),
      project(a[0] - px, a[1] - py, z),
    ],
  };
}

function buildRoadFills(g) {
  const ordered = streets.filter((street) => street.kind !== "canal").slice().sort((a, b) => (a.kind === "main") - (b.kind === "main"));
  for (const street of ordered) {
    const ribbon = roadRibbon(street);
    fillPoly(g, ribbon.corners, street.kind === "main" ? 0x0c1222 : 0x10182a);
  }
}

function buildRoadMarks(g) {
  const ordered = streets.filter((street) => street.kind !== "canal").slice().sort((a, b) => (a.kind === "main") - (b.kind === "main"));
  for (const street of ordered) {
    const ribbon = roadRibbon(street);
    const { corners, a, dx, dy, len, z } = ribbon;
    const edge = street.kind === "main" ? 1.35 : 0.9;
    g.moveTo(corners[0][0], corners[0][1]).lineTo(corners[1][0], corners[1][1]).stroke({ color: YELLOW, width: edge });
    g.moveTo(corners[3][0], corners[3][1]).lineTo(corners[2][0], corners[2][1]).stroke({ color: YELLOW, width: edge });
    const span = street.kind === "main" ? 7 : 4.5;
    const gap = street.kind === "main" ? 5 : 4;
    for (let dist = 2; dist < len - 2; dist += span + gap) {
      const t0 = dist / len;
      const t1 = Math.min(1, (dist + span) / len);
      const from = project(a[0] + dx * t0, a[1] + dy * t0, z + 0.08);
      const to = project(a[0] + dx * t1, a[1] + dy * t1, z + 0.08);
      g.moveTo(from[0], from[1]).lineTo(to[0], to[1]).stroke({
        color: 0xf4f7ff,
        width: street.kind === "main" ? 1.05 : 0.75,
        cap: "round",
      });
    }
  }
  const canal = streets.find((street) => street.kind === "canal");
  if (!canal) return;
  const [a, b] = canal.points;
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  const px = (-dy / len) * (canal.width_m / 2);
  const py = (dx / len) * (canal.width_m / 2);
  const leftA = project(a[0] + px, a[1] + py, 0.2);
  const leftB = project(b[0] + px, b[1] + py, 0.2);
  const rightA = project(a[0] - px, a[1] - py, 0.2);
  const rightB = project(b[0] - px, b[1] - py, 0.2);
  g.moveTo(leftA[0], leftA[1]).lineTo(leftB[0], leftB[1]).stroke({ color: YELLOW, width: 1.5 });
  g.moveTo(rightA[0], rightA[1]).lineTo(rightB[0], rightB[1]).stroke({ color: YELLOW, width: 1.5 });
}

function buildCourtyards(g) {
  for (const feature of flood.features) {
    for (const hole of feature.geometry.coordinates.slice(1)) {
      const pad = hole.map((point) => project(point[0], point[1], 0.1));
      fillPoly(g, pad, 0x17243f);
      strokePoly(g, pad, YELLOW, 0.65);
    }
  }
}

function floodPaint(depth) {
  if (depth >= 1.2) return { color: 0x2c4a48, alpha: 0.74, edge: 0x6d8a78 };
  if (depth >= 0.7) return { color: 0x3a5854, alpha: 0.66, edge: 0x6d8a78 };
  if (depth >= 0.4) return { color: 0x4e6d66, alpha: 0.55, edge: 0x7d9a90 };
  return { color: 0x5f7c72, alpha: 0.42, edge: 0x8aaba0 };
}

function ringBounds(ring) {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;
  for (const point of ring) {
    minX = Math.min(minX, point[0]);
    minY = Math.min(minY, point[1]);
    maxX = Math.max(maxX, point[0]);
    maxY = Math.max(maxY, point[1]);
  }
  return { minX, minY, maxX, maxY };
}

function pointInBounds(x, y, bounds) {
  return x > bounds.minX && x < bounds.maxX && y > bounds.minY && y < bounds.maxY;
}

function drawFloodRipple(g, outer, holes, phase) {
  const box = ringBounds(outer);
  const holeBoxes = holes.map(ringBounds);
  const span = box.maxY - box.minY;
  const bands = span > 80 ? 4 : 2;
  for (let band = 0; band < bands; band += 1) {
    const y0 = box.minY + ((band + 1) / (bands + 1)) * span;
    let drawing = false;
    for (let x = box.minX + 3; x <= box.maxX - 3; x += 4) {
      const y = y0 + Math.sin(x / 16 + phase + band) * 1.15;
      const dry = holeBoxes.some((hole) => pointInBounds(x, y, hole));
      const point = project(x, y, 0.12);
      if (dry) {
        drawing = false;
        continue;
      }
      if (!drawing) g.moveTo(point[0], point[1]);
      else g.lineTo(point[0], point[1]);
      drawing = true;
    }
    g.stroke({ color: 0x9bb8ae, width: 1.15, alpha: 0.34 });
  }
}

function buildFlood(g) {
  g.clear();
  const features = flood.features.slice().sort((a, b) => a.properties.depth_m - b.properties.depth_m);
  const phase = reduce ? 0 : performance.now() / 900;
  for (const feature of features) {
    const depth = feature.properties.depth_m;
    if (depth > floodLevel + 0.001) continue;
    const paint = floodPaint(depth);
    const rings = feature.geometry.coordinates;
    const outer = rings[0];
    const holes = rings.slice(1);
    const ringPoints = (ring) => flat(ring.map((point) => project(point[0], point[1], 0.08)));
    g.poly(ringPoints(outer), true).fill({ color: paint.color, alpha: paint.alpha });
    for (const hole of holes) g.poly(ringPoints(hole), true).cut();
    g.poly(ringPoints(outer), true).stroke({ color: paint.edge, width: 7, alpha: 0.22 });
    g.poly(ringPoints(outer), true).stroke({ color: paint.edge, width: 1.5, alpha: 0.5 });
    if (!reduce) drawFloodRipple(g, outer, holes, phase);
  }
}

function buildPower(g) {
  const main = streets.find((street) => street.poles);
  if (!main) return;
  const [a, b] = main.points;
  const dx = b[0] - a[0];
  const dy = b[1] - a[1];
  const len = Math.hypot(dx, dy) || 1;
  const px = -dy / len;
  const py = dx / len;
  const offset = main.width_m / 2 + 1.5;
  const tops = [];
  for (let dist = 18; dist < len - 8; dist += 34) {
    const t = dist / len;
    const x = a[0] + dx * t - px * offset;
    const y = a[1] + dy * t - py * offset;
    const base = project(x, y, 0);
    const top = project(x, y, 7.2);
    g.moveTo(base[0], base[1]).lineTo(top[0], top[1]).stroke({ width: 1.4, color: 0xc5cedf });
    const left = project(x - 1.3, y, 6.7);
    const right = project(x + 1.3, y, 6.7);
    g.moveTo(left[0], left[1]).lineTo(right[0], right[1]).stroke({ width: 1.3, color: YELLOW });
    tops.push(top);
  }
  for (let i = 1; i < tops.length; i++) {
    g.moveTo(tops[i - 1][0], tops[i - 1][1]).lineTo(tops[i][0], tops[i][1]).stroke({ width: 1, color: 0x9aa6c2, alpha: 0.8 });
  }
}

function addLabel(text, x, y, angle, size, fill) {
  const label = new Text({
    text,
    style: {
      fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif",
      fontSize: size,
      fill,
      fontWeight: "600",
      stroke: { color: INK, width: 4 },
    },
  });
  label.anchor.set(0.5);
  label.position.set(x, y);
  label.rotation = angle;
  label.eventMode = "none";
  labels.push(label);
  world.addChild(label);
}

function syncLabelScale() {
  if (!world) return;
  const size = 1 / Math.max(world.scale.x, 0.2);
  for (const label of labels) label.scale.set(size);
}

function buildLabels() {
  for (const street of streets) {
    const [a, b] = street.points;
    const start = project(a[0], a[1], 0.4);
    const end = project(b[0], b[1], 0.4);
    if (Math.hypot(end[0] - start[0], end[1] - start[1]) < 70) continue;
    let angle = Math.atan2(end[1] - start[1], end[0] - start[0]);
    if (angle > Math.PI / 2 || angle < -Math.PI / 2) angle += Math.PI;
    const named = street.labels && street.labels.length
      ? street.labels
      : [{ name_en: street.name_en, name_th: street.name_th, t: 0.5 }];
    for (const row of named) {
      const t = row.t == null ? 0.5 : row.t;
      const worldX = a[0] + (b[0] - a[0]) * t;
      const worldY = a[1] + (b[1] - a[1]) * t;
      const point = project(worldX, worldY, 0.4);
      addLabel(row.name_en || row.name_th, point[0], point[1], angle, street.kind === "main" ? 15 : 12, 0xf7f8ff);
    }
  }
  for (const building of town.buildings) {
    if (!building.landmark || !(building.name_en || building.name_th)) continue;
    const point = project(building.x + building.w / 2, building.y + building.d + 1.5, 2);
    addLabel(building.name_en || building.name_th, point[0], point[1], 0, building.kind === "school" || building.kind === "temple" ? 15 : 12, 0xf7f8ff);
  }
}

function buildLanes(g) {
  for (const edge of town.graph.edges) {
    if (!edge.lane) continue;
    const a = nodeById[edge.from];
    const b = nodeById[edge.to];
    if (!a || !b) continue;
    const from = project(a.x, a.y, 0.16);
    const to = project(b.x, b.y, 0.16);
    const boat = edge.modes.includes("boat") && !edge.modes.includes("foot");
    g.moveTo(from[0], from[1]).lineTo(to[0], to[1]).stroke({
      color: boat ? 0xff5d3a : YELLOW,
      width: 1.7,
      cap: "round",
    });
  }
}

function worldSpans(route) {
  const spans = [];
  let total = 0;
  for (const leg of route.legs) {
    const pts = leg.node_ids.map((id) => nodeById[id]).filter(Boolean);
    let len = 0;
    for (let i = 1; i < pts.length; i++) len += Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
    spans.push({ leg, pts, len, at: total });
    total += len;
  }
  return { spans, total };
}

function pointAlongWorld(pts, distance) {
  let left = distance;
  for (let i = 1; i < pts.length; i++) {
    const seg = Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
    if (left <= seg || i === pts.length - 1) {
      const t = seg === 0 ? 0 : Math.min(1, left / seg);
      return { x: pts[i - 1].x + (pts[i].x - pts[i - 1].x) * t, y: pts[i - 1].y + (pts[i].y - pts[i - 1].y) * t };
    }
    left -= seg;
  }
  const last = pts[pts.length - 1];
  return { x: last.x, y: last.y };
}

function pointAt(route, distance) {
  const { spans, total } = worldSpans(route);
  if (!spans.length) return null;
  const travel = Math.max(0, Math.min(distance, total));
  let span = spans[0];
  let remain = travel;
  for (const candidate of spans) {
    if (remain <= candidate.len || candidate === spans[spans.length - 1]) {
      span = candidate;
      break;
    }
    remain -= candidate.len;
  }
  const here = pointAlongWorld(span.pts, Math.min(remain, Math.max(span.len, 0)));
  return { here, span, total };
}

function paintRoute(route, offset) {
  const { spans } = worldSpans(route);
  for (const span of spans) {
    const projected = span.pts.map((point) => project(point.x, point.y, 0.2));
    const color = span.leg.mode === "boat" ? 0x7ec8ff : YELLOW;
    if (projected.length >= 2) {
      solidPath(routeGroundG, projected, 0x07090f, 5);
      dashPath(routeGroundG, projected, color, 2.4, span.leg.mode === "boat" ? 5 : 10, 7, offset);
    }
  }
}

function boatCue(rule) {
  if (!rule) return "rescue";
  if (rule.vehicle === "van") return "supply";
  if (rule.vehicle === "truck") return "evac";
  if (rule.return_to === "clinic") return "medical";
  return "rescue";
}

function drawBoatSprite(screen, angle, cue) {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  const p = (dx, dy) => [screen[0] + dx * c - dy * s, screen[1] + dx * s + dy * c];
  const hull = [p(14, 0), p(7, 5.1), p(-9, 4.2), p(-12, 0), p(-9, -4.2), p(7, -5.1)];
  fillPoly(routeG, hull, 0xf7f4ee);
  strokePoly(routeG, hull, 0x8d95a3, 1.7);
  const inner = [p(7.5, 0), p(4.2, 3.1), p(-6.5, 2.5), p(-8, 0), p(-6.5, -2.5), p(4.2, -3.1)];
  fillPoly(routeG, inner, 0xc4894a);
  const thwartA = p(-1.5, 2.15);
  const thwartB = p(-1.5, -2.15);
  routeG.moveTo(thwartA[0], thwartA[1]).lineTo(thwartB[0], thwartB[1]).stroke({ width: 1.6, color: 0x8a5a32, cap: "round" });
  const thwartC = p(3.2, 2.35);
  const thwartD = p(3.2, -2.35);
  routeG.moveTo(thwartC[0], thwartC[1]).lineTo(thwartD[0], thwartD[1]).stroke({ width: 1.6, color: 0x8a5a32, cap: "round" });
  const ring = p(-5.2, 0.15);
  routeG.circle(ring[0], ring[1], 2.15).stroke({ width: 1.5, color: 0x7ec8ff });
  if (cue === "supply") {
    fillPoly(routeG, [p(0.6, 1.7), p(4.4, 1.7), p(4.4, -1.5), p(0.6, -1.5)], 0x8a5a32);
    fillPoly(routeG, [p(4.6, 1.15), p(7.4, 1.15), p(7.4, -1.05), p(4.6, -1.05)], 0x6b4228);
    return;
  }
  if (cue === "medical" || cue === "evac") {
    const flag = [p(-0.4, -0.6), p(-0.4, -8.2), p(5.2, -6.2), p(-0.4, -4.6)];
    fillPoly(routeG, flag, cue === "medical" ? 0xf7f4ee : 0xf0a040);
    strokePoly(routeG, flag, cue === "medical" ? 0xc23b32 : 0xc46a12, 0.8);
    if (cue === "medical") {
      const cross = p(1.5, -6.3);
      routeG.moveTo(cross[0] - 1.7, cross[1]).lineTo(cross[0] + 1.7, cross[1]).stroke({ width: 1.35, color: 0xff3b30, cap: "round" });
      routeG.moveTo(cross[0], cross[1] - 1.7).lineTo(cross[0], cross[1] + 1.7).stroke({ width: 1.35, color: 0xff3b30, cap: "round" });
    }
  }
}

function drawWake(route, distance) {
  for (let i = 1; i <= 3; i++) {
    const spot = pointAt(route, distance - i * 3.2);
    if (!spot) continue;
    const screen = project(spot.here.x, spot.here.y, 0.4);
    routeG.ellipse(screen[0], screen[1], 7 - i, 2.4).stroke({ color: 0x9fd4ff, width: 1.2, alpha: 0.45 / i });
  }
}

function drawPulse(trip) {
  const building = buildingById(trip.buildingId);
  if (!building) return;
  const center = project(building.x + building.w / 2, building.y + building.d / 2, 1.2);
  const age = (performance.now() - trip.born) / 1000;
  for (let i = 0; i < 3; i++) {
    const t = (age * 0.7 + i * 0.35) % 1.2;
    routeG.ellipse(center[0], center[1], 8 + t * 28, 4 + t * 12).stroke({ color: YELLOW, width: 1.6, alpha: Math.max(0, 0.85 - t) });
  }
}

function drawTrips(offset) {
  if (!routeG || !routeGroundG) return;
  routeG.clear();
  routeGroundG.clear();
  for (const trip of trips) {
    for (const route of trip.phases || []) paintRoute(route, offset);
    if (trip.kind === "pulse") {
      drawPulse(trip);
      continue;
    }
    const route = (trip.phases || [])[trip.phase];
    if (!route) continue;
    const spot = pointAt(route, trip.travel);
    if (!spot) continue;
    const behind = pointAt(route, Math.max(0, trip.travel - 1.4));
    const screen = project(spot.here.x, spot.here.y, 1.2);
    const prev = behind ? project(behind.here.x, behind.here.y, 1.2) : screen;
    const angle = Math.atan2(screen[1] - prev[1], screen[0] - prev[0]);
    drawWake(route, trip.travel);
    drawBoatSprite(screen, angle, trip.cue || boatCue({ vehicle: trip.kind }));
  }
}

function advanceTrips(deltaMS) {
  if (reduce) return;
  for (const trip of trips) {
    if (trip.kind === "pulse" || trip.parked) continue;
    const route = (trip.phases || [])[trip.phase];
    if (!route) continue;
    const total = worldSpans(route).total;
    trip.travel += deltaMS * 0.022;
    if (trip.travel < total) continue;
    if (trip.phase < trip.phases.length - 1) {
      trip.phase += 1;
      trip.travel = 0;
    } else {
      trip.parked = true;
      trip.travel = total;
    }
  }
}

const OUTLINE_HEX = { P1: 0xff3b30, P2: 0xff9f1a, P3: 0x3ddc84, P4: 0xc084fc };
const CALLER_OUTLINE = 0xff3b30;
const DEST_OUTLINE = 0x2f6bff;
const PENDING_OUTLINE = 0xed7401;

function activeDestinationId() {
  if (!review || !review.rule || review.approval === "pending" || review.approval === "rejected") return null;
  const rule = review.rule;
  if (rule.return_to === "clinic" || rule.id === "p1-medical" || rule.id === "hospital-flood") return "bldg-clinic";
  if (rule.return_to === "shelter" || rule.vehicle === "truck") return "bldg-shelter";
  return null;
}

function outlineColorFor(id) {
  const call = activeCallId && town ? town.calls.find((item) => item.id === activeCallId) : null;
  if (call && call.building_id === id) {
    if (review && review.approval === "pending" && review.call && review.call.building_id === id) return PENDING_OUTLINE;
    return CALLER_OUTLINE;
  }
  if (activeDestinationId() === id) return DEST_OUTLINE;
  if (town) {
    for (const item of town.calls) {
      if (item.building_id !== id) continue;
      const decision = callResults.get(item.id);
      if (!decision) continue;
      return OUTLINE_HEX[decision.final_priority] || CALLER_OUTLINE;
    }
  }
  return CALLER_OUTLINE;
}

function outlineBuilding(g, id, color) {
  const record = records && records.get(id);
  if (!record) return;
  for (const poly of record.polys) {
    if (!poly || poly.length < 3) continue;
    glowPoly(g, poly, color, 7, 0.3);
    strokePoly(g, poly, color, 1.8);
  }
}

function drawSelection() {
  if (!selectG) return;
  selectG.clear();
  if (!selected || !records || !records.has(selected)) return;
  outlineBuilding(selectG, selected, outlineColorFor(selected));
}

function drawMarkers() {
  markerG.clear();
  for (const building of town.buildings) {
    if (building.sim_status !== "needs_help" && building.sim_status !== "evacuated") continue;
    const point = project(building.x + building.w * 0.5, building.y + building.d * 0.15, building.floors * 3.1 + 2.4);
    if (building.sim_status === "needs_help") {
      markerG.circle(point[0], point[1], 5.5).fill({ color: 0xff4b3a });
      markerG.circle(point[0], point[1], 5.5).stroke({ color: 0xfff6ea, width: 1.4 });
    } else {
      markerG.rect(point[0], point[1] - 7, 9, 6).fill({ color: 0xf4f6fb });
    }
  }
}

function sortKey(building) {
  return building.x + building.y + building.w + building.d;
}

function buildSceneryBlock() {
  const cell = 2;
  const cols = Math.ceil(town.meta.world.width_m / cell) + 2;
  const rows = Math.ceil(town.meta.world.depth_m / cell) + 2;
  const grid = new Uint8Array(cols * rows);
  const mark = (x, y) => {
    const c = Math.floor(x / cell);
    const r = Math.floor(y / cell);
    if (c < 0 || r < 0 || c >= cols || r >= rows) return;
    grid[r * cols + c] = 1;
  };
  const markDisk = (x, y, rad) => {
    const r2 = rad * rad;
    for (let yy = y - rad; yy <= y + rad; yy += cell) {
      for (let xx = x - rad; xx <= x + rad; xx += cell) {
        const dx = xx - x;
        const dy = yy - y;
        if (dx * dx + dy * dy <= r2) mark(xx, yy);
      }
    }
  };
  const markCapsule = (ax, ay, bx, by, rad) => {
    const len = Math.hypot(bx - ax, by - ay) || 1;
    const steps = Math.max(1, Math.ceil(len / cell));
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      markDisk(ax + (bx - ax) * t, ay + (by - ay) * t, rad);
    }
  };
  for (const building of town.buildings) {
    for (let yy = building.y - 2.2; yy <= building.y + building.d + 2.2; yy += cell) {
      for (let xx = building.x - 2.2; xx <= building.x + building.w + 2.2; xx += cell) mark(xx, yy);
    }
  }
  for (const street of streets) {
    const [a, b] = street.points;
    markCapsule(a[0], a[1], b[0], b[1], street.width_m / 2 + 3.2);
  }
  for (const edge of town.graph.edges) {
    const a = nodeById[edge.from];
    const b = nodeById[edge.to];
    if (!a || !b) continue;
    markCapsule(a.x, a.y, b.x, b.y, 3.4);
  }
  for (const tree of town.trees) markDisk(tree.x, tree.y, Math.min(tree.r || 4, 8) * 0.45);
  for (const feature of flood.features) {
    for (const hole of feature.geometry.coordinates.slice(1)) {
      let minX = Infinity;
      let minY = Infinity;
      let maxX = -Infinity;
      let maxY = -Infinity;
      for (const point of hole) {
        minX = Math.min(minX, point[0]);
        minY = Math.min(minY, point[1]);
        maxX = Math.max(maxX, point[0]);
        maxY = Math.max(maxY, point[1]);
      }
      for (let yy = minY - 2; yy <= maxY + 2; yy += cell) {
        for (let xx = minX - 2; xx <= maxX + 2; xx += cell) {
          if (pip(xx, yy, hole)) mark(xx, yy);
        }
      }
    }
  }
  return {
    blocked(x, y) {
      const c = Math.floor(x / cell);
      const r = Math.floor(y / cell);
      if (c < 0 || r < 0 || c >= cols || r >= rows) return true;
      return grid[r * cols + c] === 1;
    },
  };
}

function ovalClear(block, px, py, rx, ry) {
  if (block.blocked(px, py)) return false;
  for (let i = 0; i < 8; i++) {
    const t = (i / 8) * Math.PI * 2;
    if (block.blocked(px + Math.cos(t) * rx, py + Math.sin(t) * ry)) return false;
  }
  return true;
}

function buildGroundCover(g, block) {
  const canal = streets.find((street) => street.kind === "canal");
  if (canal) {
    const bank = canal.points[0][0] + canal.width_m / 2 + 4.2;
    for (let y = 34; y < 396; y += 9) {
      const x = bank + (hashId("bank-" + y) % 5);
      if (block.blocked(x, y) || block.blocked(x + 3, y + 2)) continue;
      const green = hashId("grass-" + y) % 2 ? 0x1b5a38 : 0x143f2c;
      fillPoly(g, quad(x, y, 0.04, x + 5.2, y, 0.04, x + 5.2, y + 5.4, 0.04, x, y + 5.4, 0.04), green, 0.92);
    }
  }
  let ponds = 0;
  for (let y = 28; y < 390 && ponds < 6; y += 34) {
    for (let x = 48; x < 500 && ponds < 6; x += 42) {
      const h = hashId("pond-" + x + "-" + y);
      if (h % 3 === 0) continue;
      const px = x + (h % 15) - 7;
      const py = y + ((h >>> 6) % 13) - 6;
      const rx = 6 + (h % 4);
      const ry = 4.5 + ((h >>> 4) % 3);
      if (!ovalClear(block, px, py, rx + 1.6, ry + 1.6)) continue;
      const ring = [];
      for (let i = 0; i < 12; i++) {
        const t = (i / 12) * Math.PI * 2;
        ring.push(project(px + Math.cos(t) * rx, py + Math.sin(t) * ry, 0.12));
      }
      fillPoly(g, ring, 0x2f6f86, 0.9);
      strokePoly(g, ring, 0xc7ead4, 1.05);
      ponds += 1;
    }
  }
}

function extraTrees(block) {
  const trees = [];
  const placed = [];
  for (let y = 20; y < 400; y += 16) {
    for (let x = 34; x < 520; x += 18) {
      const h = hashId("scenery-" + x + "-" + y);
      if (h % 4 !== 0) continue;
      const tx = x + (h % 11) - 5;
      const ty = y + ((h >>> 8) % 11) - 5;
      if (tx < 8 || ty < 8 || tx > 530 || ty > 410) continue;
      if (block.blocked(tx, ty)) continue;
      if (placed.some((point) => (point.x - tx) ** 2 + (point.y - ty) ** 2 < 144)) continue;
      trees.push({ id: "scenery-" + x + "-" + y, x: tx, y: ty, r: 4.6, kind: h % 3 === 0 ? "banana" : "palm" });
      placed.push({ x: tx, y: ty });
      if (trees.length >= 48) return trees;
    }
  }
  return trees;
}

function buildScene() {
  world.removeChildren();
  labels = [];
  records = new Map();
  const ground = new Graphics();
  buildGround(ground);
  ground.eventMode = "static";
  ground.on("pointertap", () => {
    if (!didDrag) select(null, false);
  });
  world.addChild(ground);

  const sceneryBlock = buildSceneryBlock();
  const cover = new Graphics();
  cover.eventMode = "none";
  buildGroundCover(cover, sceneryBlock);
  world.addChild(cover);

  const roadFills = new Graphics();
  roadFills.eventMode = "none";
  buildRoadFills(roadFills);
  world.addChild(roadFills);

  floodG = new Graphics();
  floodG.eventMode = "none";
  buildFlood(floodG);
  world.addChild(floodG);

  const courtyards = new Graphics();
  courtyards.eventMode = "none";
  buildCourtyards(courtyards);
  world.addChild(courtyards);

  const roadMarks = new Graphics();
  roadMarks.eventMode = "none";
  buildRoadMarks(roadMarks);
  world.addChild(roadMarks);

  const lanes = new Graphics();
  lanes.eventMode = "none";
  buildLanes(lanes);
  world.addChild(lanes);

  routeGroundG = new Graphics();
  routeGroundG.eventMode = "none";
  world.addChild(routeGroundG);

  const objects = [];
  for (const building of town.buildings) {
    const g = new Graphics();
    const polys = paintBuilding(g, building);
    g.eventMode = "static";
    g.cursor = "pointer";
    g.hitArea = { contains: (x, y) => polys.some((poly) => pip(x, y, poly)) };
    g.on("pointertap", (event) => {
      event.stopPropagation();
      if (!didDrag) select(building.id, false);
    });
    records.set(building.id, { building, g, polys });
    objects.push({ sort: sortKey(building), g });
  }
  for (const tree of town.trees.concat(extraTrees(sceneryBlock))) {
    const g = new Graphics();
    g.eventMode = "none";
    paintTree(g, tree);
    objects.push({ sort: tree.x + tree.y, g });
  }
  const main = streets.find((street) => street.kind === "main");
  if (main) {
    const g = new Graphics();
    g.eventMode = "none";
    buildPower(g);
    objects.push({ sort: (main.points[0][0] + main.points[1][0]) / 2 + main.fixed + 4, g });
  }
  objects.sort((a, b) => a.sort - b.sort);
  for (const object of objects) world.addChild(object.g);

  routeG = new Graphics();
  routeG.eventMode = "none";
  world.addChild(routeG);
  selectG = new Graphics();
  selectG.eventMode = "none";
  world.addChild(selectG);
  markerG = new Graphics();
  markerG.eventMode = "none";
  world.addChild(markerG);
  drawMarkers();
  buildLabels();
  callLightG = new Graphics();
  callLightG.eventMode = "none";
  world.addChild(callLightG);
  drawTrips(0);
  drawSelection();
  drawCallLights();
}

function screenToWorld(sx, sy) {
  const local = world.toLocal({ x: sx, y: sy });
  const isoX = local.x;
  const isoY = local.y;
  return [isoY + isoX / 2, isoY - isoX / 2];
}

function updateMinimap() {
  const canvas = document.getElementById("minimap");
  const ctx = canvas.getContext("2d");
  const w = town.meta.world.width_m;
  const d = town.meta.world.depth_m;
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.fillStyle = "#0b1220";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const pad = 8;
  const sx = (canvas.width - pad * 2) / w;
  const sy = (canvas.height - pad * 2) / d;
  const map = (x, y) => [pad + x * sx, pad + y * sy];
  ctx.strokeStyle = "#9aa8bb";
  ctx.globalAlpha = 0.9;
  ctx.lineWidth = 1;
  ctx.strokeRect(pad, pad, w * sx, d * sy);
  ctx.globalAlpha = 0.45;
  ctx.fillStyle = "#3a5854";
  ctx.fillRect(pad, pad + 180 * sy, (w - 8) * sx, (d - 180) * sy);
  ctx.globalAlpha = 1;
  for (const building of town.buildings) {
    const color = roofColor(building);
    ctx.fillStyle = "#" + color.toString(16).padStart(6, "0");
    const [mx, my] = map(building.x, building.y);
    ctx.fillRect(mx, my, Math.max(1.2, building.w * sx), Math.max(1.2, building.d * sy));
  }
  const inset = viewInsets();
  const corners = [
    [inset.left, inset.top],
    [app.screen.width - inset.right, inset.top],
    [app.screen.width - inset.right, app.screen.height - 20],
    [inset.left, app.screen.height - 20],
  ].map(([x, y]) => screenToWorld(x, y));
  ctx.save();
  ctx.beginPath();
  ctx.rect(pad, pad, w * sx, d * sy);
  ctx.clip();
  ctx.beginPath();
  corners.forEach(([x, y], index) => {
    const [mx, my] = map(x, y);
    if (index) ctx.lineTo(mx, my);
    else ctx.moveTo(mx, my);
  });
  ctx.closePath();
  ctx.fillStyle = "rgba(0, 118, 216, 0.16)";
  ctx.fill();
  ctx.strokeStyle = "#0076D8";
  ctx.lineWidth = 1.5;
  ctx.stroke();
  const focus = screenToWorld(app.screen.width * 0.42, app.screen.height * 0.48);
  const [fx, fy] = map(focus[0], focus[1]);
  ctx.beginPath();
  ctx.arc(fx, fy, 3.2, 0, Math.PI * 2);
  ctx.fillStyle = "#ED7401";
  ctx.fill();
  ctx.restore();
}

function viewInsets() {
  const narrow = window.innerWidth <= 860;
  return { left: narrow ? 12 : 388, right: narrow ? 16 : 344, top: 88 };
}

function viewCenter() {
  const inset = viewInsets();
  return [(inset.left + app.screen.width - inset.right) / 2, app.screen.height / 2];
}

function frameRoutes(routes) {
  const xs = [];
  const ys = [];
  for (const route of routes) {
    const building = buildingById(route.building_id);
    const base = buildingById(route.base_id);
    for (const box of [building, base]) {
      if (!box) continue;
      xs.push(box.x, box.x + box.w);
      ys.push(box.y, box.y + box.d);
    }
    for (const leg of route.legs) {
      for (const id of leg.node_ids) {
        const node = nodeById[id];
        if (!node) continue;
        xs.push(node.x);
        ys.push(node.y);
      }
    }
  }
  if (!xs.length || !app) return;
  const minX = Math.min(...xs);
  const maxX = Math.max(...xs);
  const minY = Math.min(...ys);
  const maxY = Math.max(...ys);
  const corners = [
    [minX, minY],
    [maxX, minY],
    [maxX, maxY],
    [minX, maxY],
  ].map(([x, y]) => project(x, y, 0));
  const spanX = Math.max(40, Math.max(...corners.map((point) => point[0])) - Math.min(...corners.map((point) => point[0])));
  const spanY = Math.max(40, Math.max(...corners.map((point) => point[1])) - Math.min(...corners.map((point) => point[1])));
  const inset = viewInsets();
  const zoom = Math.min(6.4, Math.max(0.7, Math.min((app.screen.width - inset.left - inset.right - 24) / spanX, (app.screen.height - 110) / spanY)));
  lookAt((minX + maxX) / 2, (minY + maxY) / 2, zoom);
}

function lookAt(x, y, zoom) {
  const point = project(x, y, 0);
  world.scale.set(zoom);
  const [cx, cy] = viewCenter();
  world.position.set(cx - point[0] * zoom, cy - point[1] * zoom);
  syncLabelScale();
  updateMinimap();
  updateCallLink();
}

function fitTown() {
  const w = town.meta.world.width_m;
  const d = town.meta.world.depth_m;
  const corners = [
    [0, 0],
    [w, 0],
    [w, d],
    [0, d],
  ].map(([x, y]) => project(x, y, 0));
  const minX = Math.min(...corners.map((point) => point[0]));
  const maxX = Math.max(...corners.map((point) => point[0]));
  const minY = Math.min(...corners.map((point) => point[1]));
  const maxY = Math.max(...corners.map((point) => point[1]));
  const inset = viewInsets();
  const zoom = Math.min(
    (app.screen.width - inset.left - inset.right) / (maxX - minX),
    (app.screen.height - 90) / (maxY - minY)
  );
  world.scale.set(Math.max(0.2, zoom));
  const [cx, cy] = viewCenter();
  world.position.set(cx - ((minX + maxX) / 2) * world.scale.x, cy - ((minY + maxY) / 2) * world.scale.y);
  syncLabelScale();
  updateMinimap();
  updateCallLink();
}

function zoomAt(factor) {
  const mx = app.screen.width / 2 - 80;
  const my = app.screen.height / 2;
  const local = world.toLocal({ x: mx, y: my });
  const next = Math.min(8, Math.max(0.28, world.scale.x * factor));
  world.scale.set(next);
  world.position.set(mx - local.x * next, my - local.y * next);
  syncLabelScale();
  updateMinimap();
  updateCallLink();
}

function buildingById(id) {
  return town.buildings.find((building) => building.id === id) || null;
}

function repaint(id) {
  const record = records.get(id);
  if (!record) return;
  record.g.clear();
  record.polys = paintBuilding(record.g, record.building);
  record.g.hitArea = { contains: (x, y) => record.polys.some((poly) => pip(x, y, poly)) };
  drawSelection();
  drawMarkers();
}

function select(id, center) {
  selected = id;
  if (id && location.hash !== "#" + id) history.replaceState(null, "", "#" + id);
  if (!id && location.hash) history.replaceState(null, "", location.pathname + location.search);
  const building = id ? buildingById(id) : null;
  if (center && building) lookAt(building.x + building.w / 2, building.y + building.d / 2, Math.min(8, Math.max(world.scale.x, 7.2)));
  drawSelection();
  drawCallLights();
}

function setStatus(householdId, status) {
  if (!STATUSES.includes(status)) return null;
  const building = town.buildings.find((row) => row.household && row.household.household_id === householdId);
  if (!building) return null;
  building.sim_status = status;
  repaint(building.id);
  select(building.id, false);
  updateMinimap();
  return { building_id: building.id, household_id: householdId, sim_status: status };
}

function el(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text != null) node.textContent = text;
  return node;
}

async function getJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(url + " returned " + response.status);
  return response.json();
}

async function loadLive() {
  try {
    live.health = await getJson("/health");
  } catch (error) {
    live.health = null;
  }
  const log = document.getElementById("backend-log");
  if (!log) return;
  if (live.health && live.health.impl) {
    log.append(
      el(
        "p",
        "muted",
        "API connected. S1 " + live.health.impl.S1_IMPL + ", S2 " + live.health.impl.S2_IMPL + ". Stub gateway, not a live model."
      )
    );
  } else {
    log.append(el("p", "muted", "API not connected. The block still draws. A call needs POST /cases on this host."));
  }
  try {
    live.labels = await getJson("/policies/labels");
  } catch (error) {
    live.labels = null;
  }
}

function labelNames() {
  const names = {};
  for (const row of (live.labels && live.labels.labels) || []) {
    if (row && row.id) names[row.id] = row.label || row.id;
  }
  return names;
}

function showCorrection(fixtureId) {
  const host = document.getElementById("correct-host");
  if (!host) return;
  host.replaceChildren();
  const caseState = caseStates.get(fixtureId);
  const decision = callResults.get(fixtureId);
  if (!caseState || !decision) return;
  const note = live.correctionNote && live.correctionNote.forId === fixtureId ? live.correctionNote : null;
  mountCorrectForm(host, {
    caseState,
    decision,
    fixtureId,
    policyVersion: (live.labels && live.labels.version) || "",
    labelNames: labelNames(),
    note,
    onResult: (result) => {
      live.correctionNote = { forId: fixtureId, ok: result.ok, text: result.text };
      if (result.decision) {
        callResults.set(fixtureId, result.decision);
        if (live.triage && live.triage.forId === fixtureId) {
          live.triage = { ...live.triage, decision: result.decision };
        }
      }
      if (result.ok) showCorrection(fixtureId);
    },
  });
}

const KEYWORD_RULES = [
  { id: "C01-a", label: "keyword: water at the door or ground floor", test: /water at the door|ground floor/ },
  { id: "F17", label: "keyword: rent or not eligible", test: /rent|not eligible|eligib/ },
  { id: "F18", label: "keyword: payment list", test: /payment list|sister/ },
  { id: "F10", label: "keyword: oxygen or rising water", test: /oxygen|rising/ },
  { id: "F11", label: "keyword: immobile", test: /immobile|cannot walk|can't walk/ },
  { id: "F02", label: "keyword: food or rice", test: /\brice\b|\bfood\b|hungry/ },
  { id: "F01", label: "keyword: drinking water", test: /drinking water/ },
  { id: "F06", label: "keyword: evacuate", test: /evacuat/ },
  { id: "F07", label: "keyword: school", test: /\bschool\b/ },
  { id: "F05", label: "keyword: flood update", test: /flood update|what time|published/ },
  { id: "F16", label: "keyword: unaccompanied child", test: /unaccompanied/ },
  { id: "F03", label: "keyword: which shelter", test: /which shelter|shelter has space/ },
];

function setPhoneStatus(text) {
  const node = document.getElementById("phone-status");
  if (node) node.textContent = text;
}

function pushPhone(kind, text, thai) {
  const log = document.getElementById("phone-log");
  const bubble = el("div", "bubble " + kind);
  bubble.append(document.createTextNode(text));
  if (thai) bubble.append(el("span", "th", thai));
  log.append(bubble);
  log.scrollTop = log.scrollHeight;
}

function greet() {
  const framing = responses && responses.framing
    ? responses.framing
    : "Sukhumvit block in Watthana, drawn in local metres. data.demo_event is still TODO_HUMAN.";
  pushPhone("note", framing + " Flood rises from flood.json. Type, speak, or open Prompts. The stub gateway returns the priority, and that result lights the house. Replies are not a live model.");
  document.getElementById("chooser-note").textContent =
    "DEMO-ONLY chooser. It lives in this page. gateway.route_chooser is still TODO_HUMAN.";
}

function demoChoose(text) {
  const q = text.toLowerCase();
  for (const rule of KEYWORD_RULES) {
    if (rule.test.test(q)) return { fixtureId: rule.id, how: rule.label };
  }
  const tokens = q.split(/[^a-z0-9]+/).filter((word) => word.length > 2);
  let best = town.calls[0];
  let score = 0;
  for (const call of town.calls) {
    const hay = (call.opening + " " + call.title).toLowerCase();
    let next = 0;
    for (const token of tokens) if (hay.includes(token)) next += 1;
    if (call.opening.toLowerCase() === q) next += 10;
    if (next > score) {
      score = next;
      best = call;
    }
  }
  return {
    fixtureId: best.id,
    how: score
      ? "nearest scripted opening (" + score + " shared words)"
      : "no keyword hit; fell back to " + best.id,
  };
}

function chooserSentence(call, how) {
  return (
    "DEMO-ONLY chooser in this page, not backend policy. gateway.route_chooser is TODO_HUMAN, so a free-text case is not routed by the gateway. Matched fixture " +
    call.id +
    " by " +
    how +
    ". The stub gateway answers that fixture id. It does not read this sentence with a live model."
  );
}

async function postJson(url, body) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let detail = "";
    try {
      detail = JSON.stringify(await response.json());
    } catch (error) {
      detail = "";
    }
    throw new Error(url + " returned " + response.status + (detail ? " " + detail : ""));
  }
  return response.json();
}

function replyMatches(template, ctx) {
  const when = template.when || {};
  if (when.priority && when.priority !== ctx.priority) return false;
  if (when.route && when.route !== ctx.route) return false;
  if (when.vehicle && when.vehicle !== ctx.vehicle) return false;
  if (when.needs_any && !when.needs_any.some((need) => ctx.needs.has(need))) return false;
  return true;
}

function operatorReply(decision, call, text) {
  const rule = matchRule(call, decision, text);
  const source = (decision.source_outcomes && decision.source_outcomes[0]) || {};
  const needs = new Set((source.needs || []).map(String));
  const ctx = {
    priority: decision.final_priority,
    route: decision.final_route,
    vehicle: rule.vehicle,
    needs,
  };
  const templates = (replies && replies.templates) || [];
  const template = templates.find((item) => replyMatches(item, ctx)) || templates[templates.length - 1];
  const eta = rule.eta_min || (rule.vehicle === "boat" ? 12 : rule.vehicle === "truck" ? 15 : 20);
  const bag = { eta, question: source.next_question || "" };
  let en = template ? applyTemplate(template.en, bag) : "Thank you. I have your message. Please keep your phone with you.";
  const th = template && template.th ? applyTemplate(template.th, bag) : "";
  if (source.next_question) en = "I just need to check one thing with you. " + source.next_question + " " + en;
  if (decision.requires_human) en += " A colleague will confirm this with you.";
  return { en, th };
}

function saplingStep(decision) {
  const source = (decision.source_outcomes && decision.source_outcomes[0]) || {};
  const needs = (source.needs || []).map(String);
  const blob = JSON.stringify(decision);
  const verdict = /sapling_verdict=([a-z_]+)/.exec(blob);
  const aid = decision.final_route === "aid_caseworker" || needs.includes("aid_payment");
  if (verdict) return { state: "on", detail: "This payload includes " + verdict[0] + "." };
  if (aid) {
    return {
      state: "stub",
      detail:
        "Aid eligibility or denial is in Sapling's scope (config/decisions.yaml sapling_scope). This stub result has no sapling_verdict. The stub gateway does not call system2/sapling.py. The Sapling client is stub. mocks/sapling_stub is not this household's verdict.",
    };
  }
  return { state: "off", detail: "Not an aid-eligibility or denial check. Sapling stays out." };
}

function flowSteps(decision, trace) {
  const outcomes = decision.source_outcomes || [];
  const source = outcomes[0] || {};
  const cascaded = outcomes.length > 1;
  const s1source = cascaded ? outcomes[1] || {} : source;
  const system = String(source.system || "");
  const selected = (decision.policy_notes || []).find((line) => /selected/.test(String(line))) || "";
  const gatewayNote = (trace || []).find((event) => event.stage === "gateway");
  const routerNote = (trace || []).find((event) => event.stage === "router");
  const sapling = saplingStep(decision);
  const why = [source.reason, selected].filter(Boolean).join(" — ");
  const s1why = [s1source.reason].filter(Boolean).join(" — ");
  const s1Step = cascaded
    ? { state: "on", detail: s1why + " — handed off to System 2 in the same turn." }
    : { state: system === "system_1" ? "on" : "off", detail: system === "system_1" ? why : "Not this call. The precheck sent it straight to System 2." };
  const s2Step = cascaded
    ? { state: "on", detail: why }
    : { state: system === "system_2" ? "on" : "off", detail: system === "system_2" ? why : "Not this call. System 1 decided without a handoff." };
  return [
    {
      title: "Mubit gateway",
      state: "on",
      detail: gatewayNote && gatewayNote.notes ? gatewayNote.notes : "POST /cases/{id}/turns reached the stub gateway.",
    },
    {
      title: "System 1 fast path",
      state: s1Step.state,
      detail: s1Step.detail,
    },
    {
      title: "System 1 → System 2 handoff",
      state: cascaded ? "on" : "off",
      detail: cascaded
        ? "Cascade mode: the System 1 escalate outcome became the System 2 handoff."
        : "No cascade on this call.",
    },
    {
      title: "System 2 reasoning",
      state: s2Step.state,
      detail: s2Step.detail,
    },
    { title: "Banyan Sapling", state: sapling.state, detail: sapling.detail },
    {
      title: "Decision router",
      state: "on",
      detail: routerNote && routerNote.notes
        ? routerNote.notes
        : decision.final_priority + " · " + decision.final_route,
    },
    {
      title: "Next action",
      state: "on",
      detail: String(decision.next_action).replaceAll("_", " "),
    },
  ];
}

function applyTemplate(text, bag) {
  return String(text || "").replace(/\{([a-z_]+)\}/g, (_, key) => (bag[key] == null ? "" : String(bag[key])));
}

function thresholdValue() {
  const node = document.getElementById("threshold");
  const fallback = (eventsFile && eventsFile.confidence_threshold) || 0.8;
  const value = node ? Number(node.value) : fallback;
  if (!Number.isFinite(value)) return fallback;
  return Math.min(1, Math.max(0, value));
}

function topScore(scores) {
  let key = "P4";
  let value = -1;
  for (const [name, score] of Object.entries(scores || {})) {
    if (score > value) {
      value = score;
      key = name;
    }
  }
  return { key, value: Math.max(0, value) };
}

function renderScores(scores, needs, accepted) {
  const box = document.getElementById("scores");
  if (!box) return;
  box.replaceChildren();
  const top = topScore(scores);
  box.append(el("p", null, accepted ? "System 1 ACCEPTED — stays on the fast path." : "System 1 REJECTED — handed to System 2."));
  for (const [key, score] of Object.entries(scores || {})) {
    const row = el("div", "score" + (key === top.key ? (accepted ? " accepted" : " rejected") : ""));
    row.append(el("span", null, key));
    const bar = el("div", "bar");
    const fill = document.createElement("i");
    fill.style.width = Math.round(Number(score) * 100) + "%";
    bar.append(fill);
    row.append(bar, el("span", null, Number(score).toFixed(2)));
    if (key === top.key) row.append(el("b", null, accepted ? "ACCEPTED" : "REJECTED"));
    box.append(row);
  }
  box.append(el("p", "muted", "Needs"));
  for (const [key, score] of Object.entries(needs || {})) {
    const row = el("div", "score");
    row.append(el("span", null, key));
    const bar = el("div", "bar");
    const fill = document.createElement("i");
    fill.style.width = Math.round(Number(score) * 100) + "%";
    bar.append(fill);
    row.append(bar, el("span", null, Number(score).toFixed(2)));
    box.append(row);
  }
}

function floodLine(call) {
  const building = buildingById(call.building_id);
  const depth = building && Number.isFinite(building.water_m) ? building.water_m : 0;
  return "Lot water_m is " + depth + " m in town.json, taken from flood.json. There is no tool endpoint. This line is simulated.";
}

function shelterLine(call) {
  const route = town.response_routes.find((item) => item.call_id === call.id && item.role === "evac");
  if (!route) return "No drawn shelter path.";
  return "Nearest drawn shelter path is " + route.length_m + " m to the evacuation shelter. Simulated lookup on response_routes.";
}

function ruleMatches(rule, ctx) {
  const when = rule.when || {};
  if (when.priority && when.priority !== ctx.priority) return false;
  if (when.route && when.route !== ctx.route) return false;
  if (when.needs_any && !when.needs_any.some((need) => ctx.needs.has(need))) return false;
  if (when.text && !ctx.text.includes(String(when.text).toLowerCase())) return false;
  if (when.flooded && !ctx.flooded) return false;
  return true;
}

function matchRule(call, decision, text) {
  const source = (decision.source_outcomes && decision.source_outcomes[0]) || {};
  const needs = new Set((source.needs || []).map(String));
  const building = buildingById(call.building_id);
  const flooded = (building && Number(building.water_m) >= 0.25) || /flood|rising|water/.test(String(text || "").toLowerCase());
  const ctx = {
    priority: decision.final_priority,
    route: decision.final_route,
    needs,
    text: String(text || "").toLowerCase(),
    flooded,
  };
  const rules = (rulebook && rulebook.rules) || [];
  return (
    rules.find((rule) => ruleMatches(rule, ctx)) ||
    rules[rules.length - 1] || { id: "none", action: "No draft rule matched.", vehicle: "none" }
  );
}

function lastNode(route) {
  const legs = route.legs || [];
  const ids = legs.length ? legs[legs.length - 1].node_ids : [];
  return ids[ids.length - 1];
}

function reverseRoute(route) {
  return {
    ...route,
    id: route.id + "-return",
    legs: [...route.legs].reverse().map((leg) => ({ mode: leg.mode, node_ids: [...leg.node_ids].reverse() })),
  };
}

function hospitalRoute(call) {
  if (hospitalCache.has(call.id)) return hospitalCache.get(call.id);
  const rescue = town.response_routes.find((item) => item.call_id === call.id && item.role === "rescue");
  let route = null;
  if (rescue && clinicNode) {
    const ids = walk(town.graph.edges, lastNode(rescue), clinicNode.id);
    const legs = ids ? legsFromPath(town.graph.edges, ids, "boat") : [];
    if (legs.length) {
      route = {
        id: "resp-" + call.id + "-hospital",
        call_id: call.id,
        building_id: call.building_id,
        base_id: "bldg-clinic",
        role: "hospital",
        legs,
      };
    }
  }
  hospitalCache.set(call.id, route);
  return route;
}

function startTrip(call, rule) {
  trips = [];
  if (!rule || rule.vehicle === "none") {
    drawTrips(0);
    return;
  }
  if (rule.vehicle === "pulse") {
    trips = [{ kind: "pulse", buildingId: call.building_id, born: performance.now(), phases: [], phase: 0, travel: 0 }];
    const building = buildingById(call.building_id);
    lookAt(building.x + building.w / 2, building.y + building.d / 2, 5.2);
    drawTrips(moverClock);
    return;
  }
  const outbound = town.response_routes.find((item) => item.call_id === call.id && item.role === rule.outbound);
  if (!outbound) return;
  const phases = [];
  if (rule.vehicle === "truck") {
    phases.push(reverseRoute(outbound));
    if (rule.return_to) phases.push(outbound);
  } else if (rule.vehicle === "boat") {
    phases.push(outbound);
    if (rule.return_to === "clinic") {
      const hospital = hospitalRoute(call);
      if (hospital) phases.push(hospital);
    } else if (rule.return_to === "shelter") {
      const evac = town.response_routes.find((item) => item.call_id === call.id && item.role === "evac");
      if (evac) phases.push(evac);
    }
  } else {
    phases.push(outbound);
  }
  const total = worldSpans(phases[0]).total;
  trips = [{ kind: rule.vehicle, cue: boatCue(rule), phases, phase: 0, travel: reduce ? total : 0, parked: !!reduce, buildingId: call.building_id }];
  frameRoutes(phases);
  drawTrips(moverClock);
}

function readLog() {
  try {
    const parsed = JSON.parse(localStorage.getItem(LOG_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    return [];
  }
}

function renderDecisionLog(rows) {
  const list = document.getElementById("decision-log");
  if (!list) return;
  list.replaceChildren();
  for (const row of rows || readLog()) {
    const when = new Date(row.at).toLocaleString("en-GB", { timeZone: "Europe/London", hour12: false });
    const title = row.title ? row.title + " · " : "";
    list.append(el("li", null, when + " London · " + title + row.fixture_id + " · " + row.priority + " · " + row.rule_id + " · " + row.operator));
  }
}

function writeLog(rows) {
  localStorage.setItem(LOG_KEY, JSON.stringify(rows));
  renderDecisionLog(rows);
}

function pushDecisionLog(entry) {
  const rows = readLog();
  entry.id = entry.fixture_id + "-" + Date.now();
  rows.unshift(entry);
  writeLog(rows.slice(0, 40));
  return entry;
}

function updateDecisionLog(id, patch) {
  writeLog(readLog().map((row) => (row.id === id ? { ...row, ...patch } : row)));
}

function highlightRule(id) {
  document.querySelectorAll("#rulebook tr").forEach((row) => row.classList.toggle("hit", row.dataset.rule === id));
}

function renderRulebook() {
  const label = document.getElementById("rulebook-label");
  if (label) label.textContent = (rulebook && rulebook.label) || "";
  const body = document.querySelector("#rulebook tbody");
  if (!body || !rulebook) return;
  body.replaceChildren();
  for (const rule of rulebook.rules) {
    const row = document.createElement("tr");
    row.dataset.rule = rule.id;
    const id = document.createElement("td");
    id.textContent = rule.id;
    const action = document.createElement("td");
    action.textContent = rule.action;
    row.append(id, action);
    body.append(row);
  }
}

function plainPriority(priority) {
  return PLAIN_PRIORITY[priority] || "the same outcome";
}

function readPatterns() {
  try {
    const parsed = JSON.parse(localStorage.getItem(PATTERN_KEY) || "[]");
    return Array.isArray(parsed) ? parsed : [];
  } catch (error) {
    return [];
  }
}

function patternStatus(row) {
  if (row.lifeSafety && !row.confirmed) return "Needs approval";
  if (row.owner === "system_1") return "Promoted";
  return "Learning";
}

function formatSeen(iso) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString("en-GB", {
    timeZone: "Europe/London",
    hour12: false,
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderPatterns(rows) {
  const table = document.getElementById("pattern-list");
  const empty = document.getElementById("pattern-empty");
  if (!table) return;
  const data = rows || readPatterns();
  const body = table.querySelector("tbody");
  if (body) body.replaceChildren();
  if (empty) empty.hidden = data.length > 0;
  table.hidden = data.length === 0;
  if (!body || !data.length) return;
  for (const row of data) {
    const tr = document.createElement("tr");
    const path = row.owner === "system_1" ? "System 1" : "System 2";
    const status = patternStatus(row);
    const statusClass = status === "Needs approval" ? "approval" : status === "Promoted" ? "promoted" : "learning";
    tr.append(el("td", null, row.label));
    tr.append(el("td", "num", String(row.count)));
    const pathCell = document.createElement("td");
    pathCell.append(el("span", "pat-badge " + (row.owner === "system_1" ? "s1" : "s2"), path));
    tr.append(pathCell);
    const statusCell = document.createElement("td");
    statusCell.append(el("span", "pat-status " + statusClass, status));
    tr.append(statusCell);
    tr.append(el("td", null, formatSeen(row.lastSeen)));
    body.append(tr);
  }
}

function writePatterns(rows) {
  localStorage.setItem(PATTERN_KEY, JSON.stringify(rows));
  renderPatterns(rows);
}

function rememberPattern(theme, decision, path, stored, consistent) {
  const rows = readPatterns().filter((row) => row.id !== theme.id);
  rows.unshift({
    id: theme.id,
    label: theme.label,
    count: path.timesBefore + 1,
    lastPriority: decision.final_priority,
    lastRoute: decision.final_route,
    owner: path.owner,
    confirmed: !!(stored && stored.confirmed && consistent),
    lifeSafety: !!theme.life_safety,
    learns: theme.learns !== false,
    lastSeen: new Date().toISOString(),
  });
  writePatterns(rows.slice(0, 24));
}

function setFeedProgress(done, total) {
  const bar = document.getElementById("feed-progress");
  if (bar) bar.style.width = total ? Math.round((done / total) * 100) + "%" : "0%";
  const count = document.getElementById("feed-count");
  if (count) count.textContent = total ? done + " of " + total + " steps" : "";
}

function setPriorityBadge(priority) {
  const badge = document.getElementById("priority-badge");
  if (!badge) return;
  if (!priority) {
    badge.hidden = true;
    return;
  }
  badge.hidden = false;
  badge.className = "priority-badge pri-" + String(priority).toLowerCase();
  badge.textContent = "Gateway " + priority;
}

function writePayload(call, decision, trace, text) {
  const source = (decision.source_outcomes && decision.source_outcomes[0]) || {};
  const log = document.getElementById("backend-log");
  log.replaceChildren();
  const details = document.createElement("details");
  const summary = document.createElement("summary");
  summary.textContent = "Stub payload";
  const pre = el("pre");
  pre.textContent = JSON.stringify(
    {
      case_id: decision.case_id,
      caller: text,
      priority: decision.final_priority,
      route: decision.final_route,
      needs: source.needs || [],
      next_question: source.next_question || null,
      next_action: decision.next_action,
      requires_human: decision.requires_human,
      reason: source.reason || null,
      trace: (trace || []).map((event) => ({
        case_id: event.case_id,
        stage: event.stage,
        notes: event.notes,
      })),
    },
    null,
    2
  );
  details.append(summary, pre);
  log.append(details);
}

function stepDetail(step, call, decision, source, bag) {
  const lines = [];
  if (step.fill === "flood") lines.push(floodLine(call));
  if (step.fill === "shelter") lines.push(shelterLine(call));
  if (step.kind === "memory" && (call.memory || []).length) {
    lines.push("Stub memory file: " + call.memory.map((row) => row.kind + " — " + row.summary).join(" "));
  }
  if (step.kind === "system_1" || step.kind === "system_2" || step.kind === "router" || step.kind === "sapling" || step.kind === "handoff") {
    lines.push("Gateway stub: " + bag.priority + " · " + bag.route + " · " + bag.next_action + ". " + (source.reason || ""));
  }
  if ((step.kind === "system_2" || step.kind === "handoff") && !String(step.text || "").includes("TODO_HUMAN")) {
    lines.push("Simulated. system2.orchestrator_model is still TODO_HUMAN.");
  }
  if (step.kind === "rule") {
    const pack = responses && responses.priorities ? responses.priorities[decision.final_priority] : null;
    if (pack) {
      lines.push("Repo policy (" + responses.policy_source + "): " + pack.policy);
      lines.push((responses.suggestion_label || "Suggestion") + " " + pack.suggestion);
    }
  }
  return lines;
}

function renderFlowCard(step, headline, details) {
  const meta = STEP_META[step.kind] || { icon: "·", kicker: "Step" };
  const item = el("li", "flow-card wait kind-" + (step.kind || "tool"));
  item.append(el("span", "step-icon", meta.icon));
  const body = el("div", "step-body");
  const kicker = el("p", "step-kicker");
  kicker.append(document.createTextNode(meta.kicker));
  kicker.append(el("span", step.source === "gateway" ? "gw-badge" : "sim-badge", step.source === "gateway" ? "gateway" : "simulated"));
  body.append(kicker, el("p", "step-headline", headline));
  if (details.length) {
    const fold = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = "Technical detail";
    fold.append(summary);
    for (const line of details) fold.append(el("p", null, line));
    body.append(fold);
  }
  item.append(body);
  return item;
}

function pathFor(call, decision, scenario) {
  const baseScores = (scenario && scenario.scores) || {};
  const baseTop = topScore(baseScores);
  const theme = scenario && scenario.theme;
  const promoteAfter = (eventsFile && eventsFile.learning && eventsFile.learning.promote_after) || 3;
  const stored = theme ? readPatterns().find((row) => row.id === theme.id) || null : null;
  const consistent = !stored || stored.lastPriority === decision.final_priority;
  if (!theme) {
    const accepted = baseTop.value >= thresholdValue();
    return {
      theme: null,
      stored: null,
      consistent: true,
      scores: baseScores,
      path: {
        accepted,
        confidence: baseTop.value,
        owner: accepted ? "system_1" : "system_2",
        hold: null,
        explain: "",
        timesBefore: 0,
      },
    };
  }
  const path = decidePath({
    base: baseTop.value,
    timesBefore: stored ? stored.count : 0,
    promoteAfter,
    threshold: thresholdValue(),
    learns: theme.learns !== false,
    lifeSafety: !!theme.life_safety,
    confirmed: !!(stored && stored.confirmed && consistent),
    consistent,
  });
  return { theme, stored, consistent, scores: withTop(baseScores, baseTop.key, path.confidence), path };
}

function vehicleLabel(rule) {
  if (!rule || rule.vehicle === "none") return "No vehicle";
  if (rule.vehicle === "pulse") return "SMS pulse";
  if (rule.vehicle === "boat") return "Rescue boat";
  if (rule.vehicle === "van") return "Supply boat";
  if (rule.vehicle === "truck") return "Evacuation boat";
  return String(rule.vehicle);
}

function destinationLabel(rule) {
  if (!rule || rule.vehicle === "none") return "No destination";
  if (rule.vehicle === "pulse") return "This phone";
  if (rule.return_to === "clinic" || rule.id === "p1-medical" || rule.id === "hospital-flood") return "Clinic";
  if (rule.return_to === "shelter" || rule.vehicle === "truck") return "Evacuation shelter";
  return "The caller's house";
}

function etaLabel(rule) {
  if (rule && rule.eta_min) return String(rule.eta_min);
  if (!rule || rule.vehicle === "none" || rule.vehicle === "pulse") return "none";
  if (rule.vehicle === "boat") return "12";
  if (rule.vehicle === "truck") return "15";
  return "20";
}

function proposalText(rule) {
  const eta = etaLabel(rule);
  const etaBit = eta === "none" ? "No ETA." : "About " + eta + " minutes.";
  return vehicleLabel(rule) + " to " + destinationLabel(rule) + ". " + etaBit + " Rule " + (rule.id || "none") + ": " + (rule.action || "");
}

function clearApprovalChrome() {
  const gate = document.getElementById("approval-gate");
  if (gate) gate.classList.remove("pending");
  const banner = document.getElementById("approval-banner");
  if (banner) banner.hidden = true;
  const frame = document.getElementById("dispatch-pending");
  if (frame) frame.hidden = true;
}

function showApproval(rule) {
  const gate = document.getElementById("approval-gate");
  if (gate) gate.classList.add("pending");
  const banner = document.getElementById("approval-banner");
  const status = document.getElementById("approval-status");
  const proposal = document.getElementById("approval-proposal");
  if (status) status.textContent = "Awaiting operator approval";
  if (proposal) proposal.textContent = proposalText(rule);
  if (banner) banner.hidden = false;
  const frame = document.getElementById("dispatch-pending");
  const frameText = document.getElementById("dispatch-pending-text");
  if (frameText) frameText.textContent = "Awaiting operator approval. " + proposalText(rule);
  if (frame) frame.hidden = false;
  if (gate) gate.scrollIntoView({ block: "nearest" });
}

function scenarioKind(scenario, kind) {
  return ((scenario && scenario.steps) || []).find((step) => step.kind === kind) || null;
}

function revealDispatch(review) {
  const step = review.dispatchStep;
  const list = document.getElementById("flow");
  if (!step || !list) return;
  const headline = applyTemplate(step.text, review.bag || {}).replace(/\s*Gateway reason:.*$/i, "").trim();
  const item = renderFlowCard(step, headline, []);
  item.classList.remove("wait");
  item.classList.add("on");
  list.append(item);
  item.scrollIntoView({ block: "nearest" });
}

function logEntry(call, decision, rule, operator, action) {
  return {
    case_id: decision.case_id || call.id,
    fixture_id: call.id,
    title: activeSummary,
    priority: decision.final_priority,
    route: decision.final_route,
    rule_id: rule.id,
    action: action || rule.action,
    operator,
    at: new Date().toISOString(),
  };
}

let activeSummary = "";

function showCallTitle(title) {
  activeSummary = title || "";
  const heading = document.getElementById("call-heading");
  if (heading) heading.textContent = title || "No call yet";
  const frame = document.getElementById("dispatch-pending-title");
  if (frame) frame.textContent = title || "";
}

async function playFeed(call, decision, trace, text, fast) {
  const token = ++flowToken;
  const scenario = eventsFile && eventsFile.scenarios ? eventsFile.scenarios[call.id] : null;
  const needs = (scenario && scenario.needs) || {};
  const planned = pathFor(call, decision, scenario);
  const scores = planned.scores;
  const top = topScore(scores);
  const path = planned.path;
  const accepted = path.accepted;
  const gated = needsOperatorApproval(decision, path);
  const source = (decision.source_outcomes && decision.source_outcomes[0]) || {};
  const aid = decision.final_route === "aid_caseworker" || (source.needs || []).map(String).includes("aid_payment");
  const rule = matchRule(call, decision, text);
  renderScores(scores, needs, accepted);
  setPriorityBadge(decision.final_priority);
  clearApprovalChrome();
  const list = document.getElementById("flow");
  list.replaceChildren();
  for (const id of ["op-accept", "op-reject"]) {
    const button = document.getElementById(id);
    if (button) button.disabled = true;
  }
  const bag = {
    memory_count: (call.memory || []).length === 1 ? "1 past case" : (call.memory || []).length + " past cases",
    top_need: (scenario && scenario.top_need) || "need",
    guess: top.key,
    confidence: top.value.toFixed(2),
    verdict: accepted ? "accepted" : "rejected",
    reason: source.reason || "no stub reason",
    next_action: String(decision.next_action || "").replaceAll("_", " "),
    priority: decision.final_priority,
    route: String(decision.final_route || "").replaceAll("_", " "),
    vehicle: vehicleLabel(rule),
    destination: destinationLabel(rule),
    eta: etaLabel(rule),
    rule_id: rule.id,
    action: rule.action,
  };
  const steps = (scenario ? scenario.steps : []).filter((step) => {
    if (step.kind === "operator_approval" || step.kind === "dispatch") return false;
    if (step.when === "rejected" && accepted) return false;
    if (step.when === "accepted" && !accepted) return false;
    if (step.when === "aid" && !aid) return false;
    return true;
  });
  if (path.explain) {
    const at = steps.findIndex((step) => step.kind === "system_1");
    const kind = path.hold === "aid" ? "sapling" : path.accepted ? "system_1" : "system_2";
    steps.splice(Math.max(0, at + 1), 0, {
      id: "pattern",
      kind,
      delay_ms: 640,
      source: "simulated",
      text: path.explain,
    });
  }
  const cascaded = (decision.source_outcomes || []).length > 1;
  if (cascaded && !steps.some((step) => step.kind === "handoff")) {
    const patternAt = steps.findIndex((step) => step.id === "pattern");
    const at = patternAt >= 0 ? patternAt : steps.findIndex((step) => step.kind === "system_1");
    steps.splice(Math.max(0, at + 1), 0, {
      id: "cascade",
      kind: "handoff",
      delay_ms: 640,
      source: "gateway",
      text: "Cascade: System 1 escalated and System 2 decided this turn.",
    });
  }
  let dispatchStep = null;
  if (gated) {
    dispatchStep = scenarioKind(scenario, "dispatch") || {
      id: "dispatch",
      kind: "dispatch",
      delay_ms: 480,
      source: "simulated",
      text: "Dispatched after operator approval. Rulebook draft {rule_id}: {action}",
    };
    steps.push(
      scenarioKind(scenario, "operator_approval") || {
        id: "approval",
        kind: "operator_approval",
        delay_ms: 420,
        source: "simulated",
        text: "Awaiting operator approval. Proposed {vehicle} to {destination}, about {eta} minutes. Rule {rule_id}.",
      }
    );
  } else {
    steps.push({
      id: "rule",
      kind: "rule",
      delay_ms: 480,
      source: "simulated",
      text: "Rulebook draft " + rule.id + ": " + rule.action,
    });
  }
  if (planned.theme) rememberPattern(planned.theme, decision, path, planned.stored, planned.consistent);
  setFeedProgress(0, steps.length);
  for (const step of steps) {
    let headline = applyTemplate(step.text, bag).replace(/\s*Gateway reason:.*$/i, "").trim();
    if (step.kind === "operator_approval") {
      headline = "PENDING APPROVAL. " + (activeSummary ? activeSummary + ". " : "") + headline;
    }
    if (step.kind === "memory" && path.timesBefore > 0 && planned.stored && planned.consistent) {
      const seen = path.timesBefore;
      headline =
        "Mubit: seen this pattern " +
        seen +
        " time" +
        (seen === 1 ? "" : "s") +
        " before, last outcome " +
        plainPriority(planned.stored.lastPriority) +
        ".";
    }
    const item = renderFlowCard(step, headline, stepDetail(step, call, decision, source, bag));
    if (step.kind === "operator_approval") item.classList.add("pending");
    list.append(item);
    step._item = item;
  }
  writePayload(call, decision, trace, text);
  let shown = 0;
  for (const step of steps) {
    if (token !== flowToken) return;
    step._item.classList.remove("wait");
    step._item.classList.add("on");
    shown += 1;
    setFeedProgress(shown, steps.length);
    step._item.scrollIntoView({ block: "nearest" });
    const delay = reduce ? 0 : fast ? 80 : step.delay_ms || 480;
    if (delay) await new Promise((resolve) => setTimeout(resolve, delay));
  }
  if (token !== flowToken) return;
  highlightRule(rule.id);
  review = {
    call,
    decision,
    rule,
    entryId: null,
    themeId: planned.theme ? planned.theme.id : null,
    text,
    bag,
    dispatchStep,
    approval: gated ? "pending" : "dispatched",
  };
  for (const id of ["op-accept", "op-reject"]) {
    const button = document.getElementById(id);
    if (button) button.disabled = false;
  }
  if (gated) {
    trips = [];
    drawTrips(0);
    showApproval(rule);
    setPhoneStatus("Awaiting operator approval");
    drawCallLights();
    drawSelection();
    return;
  }
  const entry = pushDecisionLog(logEntry(call, decision, rule, "pending"));
  review.entryId = entry.id;
  startTrip(call, rule);
}

function appendLiveStep(step) {
  const list = document.getElementById("flow");
  if (!list) return;
  const item = renderFlowCard(
    { kind: step.kind || "router", source: step.source || "gateway" },
    step.text || "",
    []
  );
  item.classList.remove("wait");
  item.classList.add("on");
  list.append(item);
}

function attachLiveFeed(source) {
  if (!source || typeof source.addEventListener !== "function") return;
  source.addEventListener("step", (event) => appendLiveStep((event && event.detail) || event));
}

function acceptReview() {
  if (!review) return;
  if (review.approval === "pending") {
    review.approval = "dispatched";
    const entry = pushDecisionLog(logEntry(review.call, review.decision, review.rule, "dispatched"));
    review.entryId = entry.id;
    revealDispatch(review);
    startTrip(review.call, review.rule);
    const reply = operatorReply(review.decision, review.call, review.text || "");
    pushPhone("operator", reply.en, reply.th);
    pushPhone("note", "Scripted reply, not a live operator.");
    setPhoneStatus("Dispatched");
    clearApprovalChrome();
    drawCallLights();
    drawSelection();
  } else if (review.entryId) {
    updateDecisionLog(review.entryId, { operator: "accepted" });
  }
  if (review.themeId) {
    const rows = readPatterns();
    const row = rows.find((item) => item.id === review.themeId);
    if (row && row.lifeSafety) {
      row.confirmed = true;
      writePatterns(rows);
    }
  }
  document.getElementById("op-accept").disabled = true;
  document.getElementById("op-reject").disabled = true;
}

function rejectReview() {
  if (!review) return;
  if (review.approval === "pending") {
    review.approval = "rejected";
    pushDecisionLog(logEntry(review.call, review.decision, review.rule, "rejected", "Rejected before dispatch. " + review.rule.action));
    trips = [];
    drawTrips(0);
    pushPhone("operator", "An operator is reassigning this request. Nothing has been sent.");
    setPhoneStatus("Reassigning");
    clearApprovalChrome();
    drawCallLights();
    drawSelection();
  } else {
    updateDecisionLog(review.entryId, { operator: "rejected" });
    trips = [];
    drawTrips(0);
  }
  showCorrection(review.call.id);
  document.getElementById("op-accept").disabled = true;
  document.getElementById("op-reject").disabled = true;
}

function renderPrompts() {
  const box = document.getElementById("prompt-groups");
  if (!box || !promptFile) return;
  box.replaceChildren();
  for (const group of promptFile.groups) {
    const block = el("section", "prompt-group");
    block.append(el("h3", null, group.label));
    for (const prompt of group.prompts) {
      const button = el("button", "prompt-card");
      button.type = "button";
      button.append(document.createTextNode(prompt.en));
      if (prompt.th) button.append(el("small", null, prompt.th));
      button.addEventListener("click", () => {
        document.getElementById("prompt-drawer").hidden = true;
        document.getElementById("prompts-toggle").setAttribute("aria-expanded", "false");
        callPlaying = false;
        syncPlayButton();
        placeCall(prompt.en, { fixtureId: prompt.fixture_id, how: "saved prompt " + prompt.id }, { via: "saved prompt" });
      });
      block.append(button);
    }
    box.append(block);
  }
}

function showInCall(name) {
  const panel = document.getElementById("in-call");
  panel.hidden = false;
  document.getElementById("caller-name").textContent = name || "Caller";
  callStartedAt = Date.now();
  const timer = document.getElementById("call-timer");
  timer.textContent = "00:00";
  clearInterval(callTimerHandle);
  callTimerHandle = setInterval(() => {
    const seconds = Math.floor((Date.now() - callStartedAt) / 1000);
    const text = String(Math.floor(seconds / 60)).padStart(2, "0") + ":" + String(seconds % 60).padStart(2, "0");
    timer.textContent = text;
  }, 250);
}

function hideInCall() {
  const panel = document.getElementById("in-call");
  if (panel) panel.hidden = true;
  clearInterval(callTimerHandle);
}

function renderKeypad() {
  const box = document.getElementById("keypad");
  if (!box) return;
  box.replaceChildren();
  for (const digit of ["1", "2", "3", "4", "5", "6", "7", "8", "9", "*", "0", "#"]) {
    const button = el("button", null, digit);
    button.type = "button";
    button.addEventListener("click", () => {
      const input = document.getElementById("phone-input");
      input.value = (input.value + digit).slice(0, 400);
    });
    box.append(button);
  }
}

function tickClock() {
  const node = document.getElementById("phone-clock");
  if (!node) return;
  node.textContent = new Date().toLocaleTimeString("en-GB", { timeZone: "Europe/London", hour: "2-digit", minute: "2-digit" });
}

function placeCall(text, choice, options = {}) {
  const generation = callGeneration;
  const job = callChain.catch(() => {}).then(async () => {
    if (generation !== callGeneration) return;
    return runPlaceCall(text, choice, options);
  });
  callChain = job;
  return job;
}

async function runPlaceCall(text, choice, options = {}) {
  const generation = callGeneration;
  const speak = options.speak !== false;
  const spoken = String(text || "").trim();
  if (!spoken) return;
  const match = choice || demoChoose(spoken);
  const call = town.calls.find((item) => item.id === match.fixtureId);
  if (!call) throw new Error("No fixture for " + match.fixtureId);
  const sentence = chooserSentence(call, match.how);
  document.getElementById("chooser-note").textContent = sentence;
  activeCallId = call.id;
  const node = document.getElementById("mubit-node");
  if (node) {
    node.classList.add("busy");
    node.classList.remove("done");
  }
  setPhoneStatus(call.id);
  if (speak) {
    if (options.via) pushPhone("note", "Transcript via " + options.via + ".");
    pushPhone("note", sentence);
    pushPhone("caller", spoken);
    renderCallList();
    const row = document.querySelector("#call-list li.active");
    if (row) row.scrollIntoView({ block: "nearest" });
    updateCallLink();
    select(call.building_id, false);
    if (document.getElementById("in-call") && !document.getElementById("in-call").hidden) {
      document.getElementById("caller-name").textContent = call.title;
    }
  }
  try {
    const created = await postJson("/cases", { fixture_id: call.id });
    const caseId = created.case.case_id;
    phoneCases.set(call.id, caseId);
    const transcript = created.case.transcript || [];
    const last = transcript.length ? transcript[transcript.length - 1].t_ms : 0;
    const turned = await postJson("/cases/" + encodeURIComponent(caseId) + "/turns", {
      t_ms: last + 1000,
      speaker: "caller",
      text: spoken,
    });
    if (generation !== callGeneration) return;
    const decision = turned.decision;
    callResults.set(call.id, decision);
    caseStates.set(call.id, turned.case);
    live.triage = { forId: call.id, decision, caseState: turned.case };
    let trace = [];
    try {
      trace = await getJson("/cases/" + encodeURIComponent(caseId) + "/trace");
    } catch (error) {
      trace = [];
    }
    if (node) {
      node.classList.remove("busy");
      node.classList.add("done");
    }
    if (speak) {
      showCallTitle(callSummary({ title: call.title, text: spoken }));
      const scenario = eventsFile && eventsFile.scenarios ? eventsFile.scenarios[call.id] : null;
      const planned = pathFor(call, decision, scenario);
      const gated = needsOperatorApproval(decision, planned.path);
      if (gated) {
        setPhoneStatus("Awaiting operator approval");
        pushPhone("operator", "An operator is reviewing your request now.");
      } else {
        const reply = operatorReply(decision, call, spoken);
        pushPhone("operator", reply.en, reply.th);
        pushPhone("note", "Scripted reply, not a live operator.");
      }
      await playFeed(call, decision, trace, spoken, callPlaying);
    }
  } catch (error) {
    if (node) node.classList.remove("busy");
    if (speak) pushPhone("note", "The gateway did not answer. " + error.message);
    else throw error;
  }
  drawCallLights();
  renderCallList();
  updateCallLink();
}

let recorder = null;
let recordChunks = [];
let recognition = null;
let heard = "";
let recording = false;

async function transcribeClip(blob) {
  try {
    const body = new FormData();
    body.append("file", blob, "clip.webm");
    body.append("language", "en");
    const response = await fetch("/stt/transcribe", { method: "POST", body });
    if (!response.ok) return null;
    const data = await response.json();
    if (data && data.text) return { text: data.text, via: "POST /stt/transcribe" };
  } catch (error) {
    return null;
  }
  return null;
}

async function toggleRecord() {
  if (recording) {
    await stopRecord();
    return;
  }
  heard = "";
  recording = true;
  const button = document.getElementById("phone-record");
  button.classList.add("on");
  setPhoneStatus("Recording");
  showInCall("Caller");
  const Speech = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (Speech) {
    recognition = new Speech();
    recognition.lang = "en-GB";
    recognition.interimResults = false;
    recognition.onresult = (event) => {
      heard = event.results[0][0].transcript || "";
    };
    try {
      recognition.start();
    } catch (error) {
      recognition = null;
    }
  }
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    recorder = new MediaRecorder(stream);
    recordChunks = [];
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size) recordChunks.push(event.data);
    };
    recorder.start();
  } catch (error) {
    recorder = null;
  }
}

async function stopRecord() {
  recording = false;
  hideInCall();
  const button = document.getElementById("phone-record");
  button.classList.remove("on");
  const liveSpeech = recognition;
  recognition = null;
  if (liveSpeech) {
    try {
      liveSpeech.stop();
    } catch (error) {
      /* already stopped */
    }
  }
  await new Promise((resolve) => setTimeout(resolve, 350));
  const muted = document.getElementById("call-mute") && document.getElementById("call-mute").getAttribute("aria-pressed") === "true";
  if (muted) heard = "";
  const speechText = heard.trim();
  let blob = null;
  if (recorder && recorder.state !== "inactive") {
    const active = recorder;
    blob = await new Promise((resolve) => {
      active.onstop = () => resolve(new Blob(recordChunks, { type: active.mimeType || "audio/webm" }));
      try {
        active.stop();
      } catch (error) {
        resolve(null);
      }
    });
    if (active.stream) active.stream.getTracks().forEach((track) => track.stop());
  }
  recorder = null;
  if (speechText) {
    setPhoneStatus("Web Speech API");
    await placeCall(speechText, null, { via: "browser Web Speech API" });
    return;
  }
  if (blob && blob.size) {
    const stt = await transcribeClip(blob);
    if (stt && stt.text) {
      setPhoneStatus(stt.via);
      await placeCall(stt.text, null, { via: stt.via });
      return;
    }
  }
  setPhoneStatus("No transcript");
  pushPhone(
    "note",
    "Stub transcript: speech-to-text is not live. speech_to_text.provider is TODO_HUMAN. infra/modal/stt_app is not mounted on this API, and POST /stt/transcribe did not return text. The browser speech API returned nothing. No words were invented from the recording."
  );
}

function drawCallLights() {
  if (!callLightG || !town || !records) return;
  callLightG.clear();
  const colors = new Map();
  for (const call of town.calls) {
    const decision = callResults.get(call.id);
    if (!decision) continue;
    colors.set(call.building_id, OUTLINE_HEX[decision.final_priority] || CALLER_OUTLINE);
  }
  const caller = activeCallId ? town.calls.find((item) => item.id === activeCallId) : null;
  if (caller) {
    const pending = review && review.approval === "pending" && review.call && review.call.id === caller.id;
    colors.set(caller.building_id, pending ? PENDING_OUTLINE : CALLER_OUTLINE);
  }
  const dest = activeDestinationId();
  if (dest && (!caller || dest !== caller.building_id)) colors.set(dest, DEST_OUTLINE);
  for (const [id, color] of colors) {
    if (id === selected) continue;
    outlineBuilding(callLightG, id, color);
  }
}

function updateCallLink() {
  // The map chip and dotted connector are gone. Mubit stays on the feed cards.
}

function renderCallLegend() {
  const box = document.getElementById("priority-legend");
  box.replaceChildren();
  for (const priority of ["P1", "P2", "P3", "P4"]) {
    const answered = [...callResults.values()].filter((decision) => decision.final_priority === priority).length;
    const labelled = town.calls.filter((call) => call.expected_priority === priority).length;
    const span = el("span");
    const swatch = el("i", "swatch pri-" + priority.toLowerCase());
    span.append(swatch, document.createTextNode(" " + priority + " " + answered + "/" + labelled));
    box.append(span);
  }
}

function renderCallList() {
  const list = document.getElementById("call-list");
  list.replaceChildren();
  for (const call of town.calls) {
    const item = el("li");
    item.dataset.call = call.id;
    if (call.id === activeCallId) item.classList.add("active");
    const button = document.createElement("button");
    button.type = "button";
    const head = el("span", "call-id", call.id + " · " + call.title);
    const decision = callResults.get(call.id);
    if (decision) {
      const badge = el("span", "call-badge pri-" + decision.final_priority.toLowerCase(), decision.final_priority);
      head.append(badge);
    }
    button.append(head, el("span", "call-msg", call.opening));
    button.addEventListener("click", () => {
      callPlaying = false;
      syncPlayButton();
      const index = town.calls.findIndex((item) => item.id === call.id);
      if (index === callCursor) callCursor += 1;
      placeCall(call.opening, { fixtureId: call.id, how: "scripted call " + call.id });
    });
    item.append(button);
    list.append(item);
  }
  renderCallLegend();
}

function syncPlayButton() {
  const button = document.getElementById("calls-play");
  button.textContent = callPlaying ? "Pause" : "Play 20 calls";
}

async function playCalls() {
  if (callPlaying) {
    callPlaying = false;
    syncPlayButton();
    return;
  }
  callPlaying = true;
  const token = ++callToken;
  syncPlayButton();
  fitTown();
  while (callPlaying && token === callToken && callCursor < town.calls.length) {
    const call = town.calls[callCursor];
    callCursor += 1;
    await placeCall(call.opening, { fixtureId: call.id, how: "scripted list, in fixture order" });
    if (!callPlaying || token !== callToken) break;
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  if (token === callToken) callPlaying = false;
  syncPlayButton();
}

function resetCalls() {
  callPlaying = false;
  callToken += 1;
  flowToken += 1;
  callGeneration += 1;
  callCursor = 0;
  callResults = new Map();
  activeCallId = null;
  phoneCases = new Map();
  caseStates = new Map();
  live.triage = null;
  live.correctionNote = null;
  review = null;
  trips = [];
  clearApprovalChrome();
  select(null, false);
  const correctHost = document.getElementById("correct-host");
  if (correctHost) correctHost.replaceChildren();
  const scores = document.getElementById("scores");
  if (scores) scores.replaceChildren();
  for (const id of ["op-accept", "op-reject"]) {
    const button = document.getElementById(id);
    if (button) button.disabled = true;
  }
  document.querySelectorAll("#rulebook tr").forEach((row) => row.classList.remove("hit"));
  hideInCall();
  drawTrips(0);
  drawCallLights();
  renderCallList();
  updateCallLink();
  syncPlayButton();
  document.getElementById("flow").replaceChildren();
  document.getElementById("backend-log").replaceChildren();
  setPriorityBadge(null);
  setFeedProgress(0, 0);
  renderPatterns();
  showCallTitle("");
  document.getElementById("phone-log").replaceChildren();
  document.querySelectorAll("[data-priority]").forEach((button) => button.classList.remove("on"));
  const node = document.getElementById("mubit-node");
  if (node) node.classList.remove("busy", "done");
  greet();
  loadLive();
}

function bindChrome() {
  document.getElementById("view-fit").addEventListener("click", fitTown);
  document.getElementById("view-dispatch").addEventListener("click", () => {
    const camera = town.meta.camera;
    lookAt(camera.look_at[0], camera.look_at[1], camera.zoom_px_per_m);
  });
  document.getElementById("calls-play").addEventListener("click", () => playCalls());
  document.getElementById("calls-step").addEventListener("click", () => {
    callPlaying = false;
    syncPlayButton();
    if (callCursor >= town.calls.length) return;
    const call = town.calls[callCursor];
    callCursor += 1;
    placeCall(call.opening, { fixtureId: call.id, how: "scripted list, stepped" });
  });
  document.getElementById("calls-reset").addEventListener("click", resetCalls);
  for (const id of ["town-reset", "dispatch-reset"]) {
    const button = document.getElementById(id);
    if (button) button.addEventListener("click", resetCalls);
  }
  document.getElementById("phone-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const input = document.getElementById("phone-input");
    const text = input.value;
    input.value = "";
    callPlaying = false;
    syncPlayButton();
    placeCall(text, null, { via: "typed message" });
  });
  document.getElementById("phone-record").addEventListener("click", () => toggleRecord());
  document.getElementById("call-end").addEventListener("click", () => {
    if (recording) stopRecord();
  });
  document.getElementById("prompts-toggle").addEventListener("click", () => {
    const drawer = document.getElementById("prompt-drawer");
    drawer.hidden = !drawer.hidden;
    document.getElementById("prompts-toggle").setAttribute("aria-expanded", String(!drawer.hidden));
  });
  for (const id of ["call-mute", "call-speaker", "call-keypad"]) {
    document.getElementById(id).addEventListener("click", () => {
      const button = document.getElementById(id);
      const on = button.getAttribute("aria-pressed") !== "true";
      button.setAttribute("aria-pressed", String(on));
      if (id === "call-keypad") document.getElementById("keypad").hidden = !on;
    });
  }
  document.getElementById("op-accept").addEventListener("click", acceptReview);
  document.getElementById("op-reject").addEventListener("click", rejectReview);
  document.getElementById("log-clear").addEventListener("click", () => writeLog([]));
  document.getElementById("pattern-reset").addEventListener("click", () => writePatterns([]));
  const patternRule = document.getElementById("pattern-rule");
  if (patternRule && eventsFile && eventsFile.learning && eventsFile.learning.life_safety_rule) {
    patternRule.textContent = eventsFile.learning.life_safety_rule;
  }
  renderPatterns();
  const threshold = document.getElementById("threshold");
  if (eventsFile && eventsFile.confidence_threshold != null) threshold.value = String(eventsFile.confidence_threshold);
  renderPrompts();
  renderRulebook();
  renderDecisionLog();
  renderKeypad();
  tickClock();
  setInterval(tickClock, 15000);
  renderCallList();
  greet();
  app.stage.eventMode = "static";
  app.stage.hitArea = app.screen;
  app.stage.on("pointerdown", (event) => {
    didDrag = false;
    drag = { x: event.global.x, y: event.global.y, ox: world.x, oy: world.y };
  });
  app.stage.on("pointermove", (event) => {
    if (!drag) return;
    const dx = event.global.x - drag.x;
    const dy = event.global.y - drag.y;
    if (dx * dx + dy * dy > 16) didDrag = true;
    world.position.set(drag.ox + dx, drag.oy + dy);
    updateMinimap();
    updateCallLink();
  });
  app.stage.on("pointerup", () => {
    drag = null;
  });
  app.stage.on("pointerupoutside", () => {
    drag = null;
  });
  app.canvas.addEventListener(
    "wheel",
    (event) => {
      event.preventDefault();
      const rect = app.canvas.getBoundingClientRect();
      const mx = event.clientX - rect.left;
      const my = event.clientY - rect.top;
      const local = world.toLocal({ x: mx, y: my });
      const factor = event.deltaY < 0 ? 1.08 : 0.92;
      const next = Math.min(8, Math.max(0.28, world.scale.x * factor));
      world.scale.set(next);
      world.position.set(mx - local.x * next, my - local.y * next);
      syncLabelScale();
      updateMinimap();
      updateCallLink();
    },
    { passive: false }
  );
  window.addEventListener("keydown", (event) => {
    if (event.target && (event.target.id === "phone-input" || event.target.tagName === "INPUT")) return;
    if (event.key === "Escape") select(null, false);
    if (event.key === "+" || event.key === "=") zoomAt(1.15);
    if (event.key === "-" || event.key === "_") zoomAt(1 / 1.15);
  });
  window.addEventListener("resize", () => {
    app.stage.hitArea = app.screen;
    updateMinimap();
  });
}

function applyPublicPlaces(townBody, placeBody) {
  const labels = (placeBody && placeBody.labels) || {};
  const thai = /[\u0e00-\u0e7f]/;
  for (const building of townBody.buildings || []) {
    const label = labels[building.id];
    if (!label || !label.name_en) continue;
    if (building.fixture_id || building.resource_id || building.id === "bldg-temple") continue;
    if (thai.test(label.name_th || "") || thai.test(label.name_en || "")) continue;
    building.name_th = label.name_en;
    building.name_en = label.name_en;
  }
}

async function main() {
  const [townBody, streetBody, floodBody, responseBody, eventBody, promptBody, ruleBody, replyBody, placeBody] = await Promise.all([
    getJson("data/town.json"),
    getJson("data/streets.json"),
    getJson("data/flood.json"),
    getJson("data/responses.json"),
    getJson("data/sim_events.json"),
    getJson("data/prompts.json"),
    getJson("data/rulebook.json"),
    getJson("data/replies.json"),
    getJson("data/places.json"),
  ]);
  town = townBody;
  applyPublicPlaces(town, placeBody);
  streets = streetBody.streets;
  flood = floodBody;
  responses = responseBody;
  eventsFile = eventBody;
  promptFile = promptBody;
  rulebook = ruleBody;
  replies = replyBody;
  floodMax = Math.max(...flood.features.map((feature) => feature.properties.depth_m));
  if (reduce) floodLevel = floodMax;
  streetById = Object.fromEntries(streets.map((street) => [street.id, street]));
  nodeById = Object.fromEntries(town.graph.nodes.map((node) => [node.id, node]));
  const clinic = town.buildings.find((building) => building.id === "bldg-clinic");
  if (clinic) clinicNode = nearestNode(town.graph.nodes, town.buildings, clinic.x + clinic.w / 2, clinic.y + clinic.d / 2);
  try {
    await document.fonts.load('700 16px "Noto Sans Thai"');
  } catch (error) {
    /* Thai phone replies still use Noto Sans Thai. Map labels are romanised. */
  }
  app = new Application();
  const pixiOptions = {
    background: INK,
    resizeTo: window,
    antialias: true,
    autoDensity: true,
    resolution: Math.min(window.devicePixelRatio || 1, 2),
  };
  try {
    await app.init({ ...pixiOptions, preference: "webgl" });
  } catch (error) {
    app = new Application();
    await app.init(pixiOptions);
  }
  scene.appendChild(app.canvas);
  world = new Container();
  world.eventMode = "passive";
  app.stage.addChild(world);
  buildScene();
  document.getElementById("loading").hidden = true;
  document.getElementById("graph-stat").textContent =
    town.graph.nodes.length + " junctions · " + town.graph.edges.length + " links · " + town.buildings.length + " blocks";
  bindChrome();
  const camera = town.meta.camera;
  lookAt(camera.look_at[0], camera.look_at[1], camera.zoom_px_per_m);
  const hash = decodeURIComponent(location.hash.replace("#", ""));
  if (hash && buildingById(hash)) select(hash, true);
  app.ticker.add((ticker) => {
    if (!reduce) {
      if (floodLevel < floodMax) {
        floodLevel = Math.min(floodMax, floodLevel + ticker.deltaMS * 0.00015);
      }
      if (floodG) buildFlood(floodG);
    }
    moverClock += ticker.deltaMS;
    if (!reduce) advanceTrips(ticker.deltaMS);
    drawTrips(moverClock);
    if (reduce) return;
    markerG.alpha = 0.55 + 0.45 * Math.sin(ticker.lastTime / 260);
    const pulse = 0.74 + 0.26 * Math.sin(ticker.lastTime / 280);
    if (callLightG) callLightG.alpha = pulse;
    if (selectG) selectG.alpha = pulse;
  });
  loadLive();
}

window.BaanSafeSim = {
  setStatus,
  select: (id) => select(id, true),
  getBuilding: (id) => (town ? buildingById(id) : null),
  attachLiveFeed,
  tripCount: () => trips.length,
  approvalPhase: () => (review ? review.approval : null),
};

main().catch((error) => {
  const loading = document.getElementById("loading");
  loading.hidden = false;
  loading.textContent = "Could not start the town view. Serve this folder over HTTP. " + error.message;
});
