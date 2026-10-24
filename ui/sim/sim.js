/* Fixed-camera town, drawn with PixiJS.

   World metres: x east, y south (toward the camera), z up.
   Iso pixels: ((x - y), (x + y) / 2 - z). Pixi only pans and zooms that
   picture. The heading never changes.

   Houses, streets, flood polygons, and routes come from ./data.
*/
import { mountCorrectForm } from "../correct.js";
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

function paintBuilding(g, building) {
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

function paintTree(g, tree) {
  const radius = Math.min(tree.r, 8.5) * 0.72;
  const base = project(tree.x, tree.y, 0);
  const top = project(tree.x, tree.y, 4.2);
  g.moveTo(base[0], base[1]).lineTo(top[0], top[1]).stroke({ width: 2.2, color: 0x3a2a22, cap: "round" });
  g.ellipse(top[0] + 1, top[1] + radius * 0.25, radius * 1.05, radius * 0.48).fill({ color: 0x143526 });
  g.ellipse(top[0] - radius * 0.08, top[1] - radius * 0.08, radius * 0.82, radius * 0.38).fill({ color: 0x1f6a3c });
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

function buildFlood(g) {
  g.clear();
  const features = flood.features.slice().sort((a, b) => a.properties.depth_m - b.properties.depth_m);
  for (const feature of features) {
    const depth = feature.properties.depth_m;
    if (depth > floodLevel + 0.001) continue;
    const color = depth >= 1.2 ? 0x4a3424 : depth >= 0.7 ? 0x6a4a30 : 0x7d5a3a;
    const alpha = depth >= 1.2 ? 0.78 : depth >= 0.7 ? 0.62 : 0.5;
    const rings = feature.geometry.coordinates;
    const ringPoints = (ring) => flat(ring.map((point) => project(point[0], point[1], 0.08)));
    g.poly(ringPoints(rings[0]), true).fill({ color, alpha });
    for (const hole of rings.slice(1)) g.poly(ringPoints(hole), true).cut();
    g.poly(ringPoints(rings[0]), true).stroke({ color: 0xc9a15a, width: 1.2, alpha: 0.85 });
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
      fontFamily: "Noto Sans Thai, sans-serif",
      fontSize: size,
      fill,
      fontWeight: "700",
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
    const midX = (start[0] + end[0]) / 2;
    const midY = (start[1] + end[1]) / 2;
    addLabel(street.name_th, midX, midY, angle, street.kind === "main" ? 16 : 13, 0xf7f8ff);
  }
  for (const building of town.buildings) {
    if (!building.landmark || !building.name_th) continue;
    const point = project(building.x + building.w / 2, building.y + building.d + 1.5, 2);
    addLabel(building.name_th, point[0], point[1], 0, building.kind === "school" || building.kind === "temple" ? 16 : 12, 0xf7f8ff);
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

function spriteKind(kind, mode) {
  if (mode === "boat") return "boat";
  if (kind === "van") return "van";
  return "truck";
}

function drawHull(kind, screen, angle) {
  const c = Math.cos(angle);
  const s = Math.sin(angle);
  const p = (dx, dy) => [screen[0] + dx * c - dy * s, screen[1] + dx * s + dy * c];
  if (kind === "boat") {
    fillPoly(routeG, [p(11, 0), p(-8, 4.2), p(-6, 0), p(-8, -4.2)], 0xf4efe4);
    strokePoly(routeG, [p(11, 0), p(-8, 4.2), p(-6, 0), p(-8, -4.2)], INK, 1);
    return;
  }
  const body = kind === "van" ? 0xd6ff3c : 0xf0a040;
  fillPoly(routeG, [p(8, 3.2), p(-7, 3.2), p(-7, -3.2), p(8, -3.2)], body);
  fillPoly(routeG, [p(8, 2.4), p(3, 2.4), p(3, -2.4), p(8, -2.4)], 0x1a2030);
  strokePoly(routeG, [p(8, 3.2), p(-7, 3.2), p(-7, -3.2), p(8, -3.2)], INK, 1);
}

function drawWake(route, distance) {
  for (let i = 1; i <= 3; i++) {
    const sample = pointAt(route, distance - i * 3.2);
    if (!sample || sample.span.leg.mode !== "boat") continue;
    const screen = project(sample.here.x, sample.here.y, 0.4);
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
    const sample = pointAt(route, trip.travel);
    if (!sample) continue;
    const behind = pointAt(route, Math.max(0, trip.travel - 1.4));
    const screen = project(sample.here.x, sample.here.y, 1.2);
    const prev = behind ? project(behind.here.x, behind.here.y, 1.2) : screen;
    const angle = Math.atan2(screen[1] - prev[1], screen[0] - prev[0]);
    const drawn = spriteKind(trip.kind, sample.span.leg.mode);
    if (drawn === "boat") drawWake(route, trip.travel);
    drawHull(drawn, screen, angle);
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

function drawSelection() {
  selectG.clear();
  if (!selected || !records.has(selected)) return;
  const record = records.get(selected);
  const building = record.building;
  const center = project(building.x + building.w / 2, building.y + building.d * 0.62, 0.2);
  const rx = Math.max(11, Math.max(building.w, building.d) * 0.78);
  selectG.ellipse(center[0], center[1], rx, rx * 0.46).fill({ color: YELLOW, alpha: 0.14 });
  selectG.ellipse(center[0], center[1], rx, rx * 0.46).stroke({ color: YELLOW, width: 1.5 });
  for (const poly of record.polys) strokePoly(selectG, poly, YELLOW, 1.15);
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
  for (const tree of town.trees) {
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
  ctx.fillStyle = "#0b1020";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  const pad = 8;
  const sx = (canvas.width - pad * 2) / w;
  const sy = (canvas.height - pad * 2) / d;
  const map = (x, y) => [pad + x * sx, pad + y * sy];
  ctx.strokeStyle = "#d6ff3c";
  ctx.globalAlpha = 0.9;
  ctx.lineWidth = 1;
  ctx.strokeRect(pad, pad, w * sx, d * sy);
  ctx.globalAlpha = 0.35;
  ctx.fillStyle = "#6a4a30";
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
  ctx.fillStyle = "rgba(214, 255, 60, 0.16)";
  ctx.fill();
  ctx.strokeStyle = "#d6ff3c";
  ctx.lineWidth = 1.5;
  ctx.stroke();
  const focus = screenToWorld(app.screen.width * 0.42, app.screen.height * 0.48);
  const [fx, fy] = map(focus[0], focus[1]);
  ctx.beginPath();
  ctx.arc(fx, fy, 3.2, 0, Math.PI * 2);
  ctx.fillStyle = "#d6ff3c";
  ctx.fill();
  ctx.restore();
}

function viewInsets() {
  const narrow = window.innerWidth <= 860;
  return { left: narrow ? 12 : 388, right: narrow ? 16 : 344, top: 72 };
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
    : "Placeholder block for a Bangkok flood demo. data.demo_event is still TODO_HUMAN.";
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
  const source = (decision.source_outcomes && decision.source_outcomes[0]) || {};
  const system = String(source.system || "");
  const selected = (decision.policy_notes || []).find((line) => /selected/.test(String(line))) || "";
  const gatewayNote = (trace || []).find((event) => event.stage === "gateway");
  const routerNote = (trace || []).find((event) => event.stage === "router");
  const sapling = saplingStep(decision);
  const why = [source.reason, selected].filter(Boolean).join(" — ");
  return [
    {
      title: "Mubit gateway",
      state: "on",
      detail: gatewayNote && gatewayNote.notes ? gatewayNote.notes : "POST /cases/{id}/turns reached the stub gateway.",
    },
    {
      title: "System 1 fast path",
      state: system === "system_1" ? "on" : "off",
      detail: system === "system_1" ? why : "Not this call. The stub gateway routes to one system.",
    },
    {
      title: "System 2 reasoning",
      state: system === "system_2" ? "on" : "off",
      detail: system === "system_2" ? why : "Not this call. The stub gateway routes to one system.",
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
  const fallback = (eventsFile && eventsFile.confidence_threshold) || 0.75;
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
  return "Nearest drawn shelter path is " + route.length_m + " m to the fictional north hall. Simulated lookup on response_routes.";
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
  trips = [{ kind: rule.vehicle, phases, phase: 0, travel: reduce ? total : 0, parked: !!reduce, buildingId: call.building_id }];
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
    list.append(el("li", null, when + " London · " + row.fixture_id + " · " + row.priority + " · " + row.rule_id + " · " + row.operator));
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

function renderPatterns(rows) {
  const list = document.getElementById("pattern-list");
  if (!list) return;
  const data = rows || readPatterns();
  list.replaceChildren();
  if (!data.length) {
    list.append(el("li", null, "No patterns yet."));
    return;
  }
  for (const row of data) {
    const item = document.createElement("li");
    const owner = row.owner === "system_1" ? "System 1" : "System 2";
    let note = owner;
    if (row.lifeSafety && !row.confirmed) note += " · needs confirm";
    else if (row.confirmed && row.owner !== "system_1") note += " · confirmed";
    item.append(el("span", null, row.label + " · " + row.count));
    item.append(el("span", null, note));
    list.append(item);
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

async function playFeed(call, decision, trace, text, fast) {
  const token = ++flowToken;
  const scenario = eventsFile && eventsFile.scenarios ? eventsFile.scenarios[call.id] : null;
  const needs = (scenario && scenario.needs) || {};
  const planned = pathFor(call, decision, scenario);
  const scores = planned.scores;
  const top = topScore(scores);
  const path = planned.path;
  const accepted = path.accepted;
  const source = (decision.source_outcomes && decision.source_outcomes[0]) || {};
  const aid = decision.final_route === "aid_caseworker" || (source.needs || []).map(String).includes("aid_payment");
  renderScores(scores, needs, accepted);
  setPriorityBadge(decision.final_priority);
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
  };
  const steps = (scenario ? scenario.steps : []).filter((step) => {
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
  const rule = matchRule(call, decision, text);
  steps.push({
    id: "rule",
    kind: "rule",
    delay_ms: 480,
    source: "simulated",
    text: "Rulebook draft " + rule.id + ": " + rule.action,
  });
  if (planned.theme) rememberPattern(planned.theme, decision, path, planned.stored, planned.consistent);
  setFeedProgress(0, steps.length);
  for (const step of steps) {
    let headline = applyTemplate(step.text, bag).replace(/\s*Gateway reason:.*$/i, "").trim();
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
  const entry = pushDecisionLog({
    case_id: decision.case_id || call.id,
    fixture_id: call.id,
    priority: decision.final_priority,
    route: decision.final_route,
    rule_id: rule.id,
    action: rule.action,
    operator: "pending",
    at: new Date().toISOString(),
  });
  review = { call, decision, rule, entryId: entry.id, themeId: planned.theme ? planned.theme.id : null };
  for (const id of ["op-accept", "op-reject"]) {
    const button = document.getElementById(id);
    if (button) button.disabled = false;
  }
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
  updateDecisionLog(review.entryId, { operator: "accepted" });
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
  updateDecisionLog(review.entryId, { operator: "rejected" });
  trips = [];
  drawTrips(0);
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
  node.classList.add("busy");
  node.classList.remove("done");
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
    node.classList.remove("busy");
    node.classList.add("done");
    if (speak) {
      const reply = operatorReply(decision, call, spoken);
      pushPhone("operator", reply.en, reply.th);
      pushPhone("note", "Scripted reply, not a live operator.");
      await playFeed(call, decision, trace, spoken, callPlaying);
    }
  } catch (error) {
    node.classList.remove("busy");
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

function houseScreen(building) {
  const local = project(building.x + building.w / 2, building.y + building.d * 0.45, 2.4);
  const rect = app.canvas.getBoundingClientRect();
  return {
    x: rect.left + world.x + local[0] * world.scale.x,
    y: rect.top + world.y + local[1] * world.scale.y,
  };
}

function drawCallLights() {
  if (!callLightG) return;
  callLightG.clear();
  const lit = new Map();
  for (const call of town.calls) {
    const decision = callResults.get(call.id);
    if (!decision) continue;
    lit.set(call.building_id, decision.final_priority);
  }
  for (const [id, priority] of lit) {
    const building = buildingById(id);
    const color = PRIORITY_HEX[priority] || YELLOW;
    const center = project(building.x + building.w / 2, building.y + building.d * 0.72, 0.25);
    const rx = Math.max(8, Math.max(building.w, building.d) * 0.72);
    callLightG.ellipse(center[0], center[1], rx, rx * 0.42).stroke({ color, width: 1.7 });
    const beacon = project(building.x + building.w / 2, building.y + building.d * 0.15, building.floors * 3.3 + 2.8);
    callLightG.circle(beacon[0], beacon[1], 2.4).fill({ color });
  }
}

function curve(fromX, fromY, toX, toY) {
  const midX = (fromX + toX) / 2;
  return `M ${fromX} ${fromY} C ${midX} ${fromY}, ${midX} ${toY}, ${toX} ${toY}`;
}

function updateCallLink() {
  const toMubit = document.getElementById("link-to-mubit");
  const toHouse = document.getElementById("link-to-house");
  const dots = document.getElementById("link-dots");
  if (!toMubit || !town || !app) return;
  dots.replaceChildren();
  const node = document.getElementById("mubit-node").getBoundingClientRect();
  const mx = node.left + node.width / 2;
  const my = node.top + node.height / 2;
  const card = document.querySelector("#call-list li.active");
  if (card && activeCallId) {
    const rect = card.getBoundingClientRect();
    toMubit.setAttribute("d", curve(rect.right, rect.top + rect.height / 2, mx, my));
  } else {
    toMubit.setAttribute("d", "");
  }
  const call = town.calls.find((item) => item.id === activeCallId);
  const decision = activeCallId ? callResults.get(activeCallId) : null;
  if (call) {
    const point = houseScreen(buildingById(call.building_id));
    toHouse.setAttribute("d", curve(mx, my, point.x, point.y));
    toHouse.setAttribute("stroke", decision ? PRIORITY_COLOR[decision.final_priority] : "#d6ff3c");
  } else {
    toHouse.setAttribute("d", "");
  }
  const lit = new Map();
  for (const item of town.calls) {
    const answer = callResults.get(item.id);
    if (!answer) continue;
    lit.set(item.building_id, answer.final_priority);
  }
  for (const [id, priority] of lit) {
    const point = houseScreen(buildingById(id));
    const dot = document.createElementNS("http://www.w3.org/2000/svg", "circle");
    dot.setAttribute("cx", String(point.x));
    dot.setAttribute("cy", String(point.y));
    dot.setAttribute("r", id === (call && call.building_id) ? "8" : "5");
    dot.setAttribute("fill", PRIORITY_COLOR[priority]);
    dot.setAttribute("stroke", "#07090f");
    dot.setAttribute("stroke-width", "1.5");
    dots.append(dot);
  }
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
  document.getElementById("phone-log").replaceChildren();
  document.querySelectorAll("[data-priority]").forEach((button) => button.classList.remove("on"));
  const node = document.getElementById("mubit-node");
  node.classList.remove("busy", "done");
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

async function main() {
  const [townBody, streetBody, floodBody, responseBody, eventBody, promptBody, ruleBody, replyBody] = await Promise.all([
    getJson("data/town.json"),
    getJson("data/streets.json"),
    getJson("data/flood.json"),
    getJson("data/responses.json"),
    getJson("data/sim_events.json"),
    getJson("data/prompts.json"),
    getJson("data/rulebook.json"),
    getJson("data/replies.json"),
  ]);
  town = townBody;
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
    /* Labels fall back to the generic sans if the Thai face is missing. */
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
    if (!reduce && floodLevel < floodMax) {
      floodLevel = Math.min(floodMax, floodLevel + ticker.deltaMS * 0.00015);
      if (floodG) buildFlood(floodG);
    }
    moverClock += ticker.deltaMS;
    if (!reduce) advanceTrips(ticker.deltaMS);
    drawTrips(moverClock);
    if (reduce) return;
    markerG.alpha = 0.55 + 0.45 * Math.sin(ticker.lastTime / 260);
    if (callLightG) callLightG.alpha = 0.72 + 0.28 * Math.sin(ticker.lastTime / 280);
  });
  loadLive();
}

window.BaanSafeSim = {
  setStatus,
  select: (id) => select(id, true),
  getBuilding: (id) => (town ? buildingById(id) : null),
  attachLiveFeed,
};

main().catch((error) => {
  const loading = document.getElementById("loading");
  loading.hidden = false;
  loading.textContent = "Could not start the town view. Serve this folder over HTTP. " + error.message;
});
