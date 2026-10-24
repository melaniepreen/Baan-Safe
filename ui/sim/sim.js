/* Fixed-camera town, drawn with PixiJS.

   World metres: x east, y south (toward the camera), z up.
   Iso pixels: ((x - y), (x + y) / 2 - z). Pixi only pans and zooms that
   picture. The heading never changes.

   Houses, streets, flood polygons, and routes come from ./data.
*/
import { mountCorrectForm } from "../correct.js";
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
let floodAlpha = 0.82;
let activeRoutes = new Set();
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
let activeCallId = null;
let callLightG = null;

const PRIORITY_COLOR = { P1: "#ff4b3a", P2: "#ff9f1a", P3: "#d6ff3c", P4: "#8aa0ff" };
const PRIORITY_HEX = { P1: 0xff4b3a, P2: 0xff9f1a, P3: 0xd6ff3c, P4: 0x8aa0ff };

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

function routePoints(route) {
  return route.node_ids.map((id) => {
    const node = nodeById[id];
    return project(node.x, node.y, 0.85);
  });
}

function drawRoutes(offset) {
  routeG.clear();
  for (const route of town.routes) {
    if (!activeRoutes.has(route.id)) continue;
    const pts = routePoints(route);
    const color = route.mode === "boat" ? 0xff5d3a : YELLOW;
    solidPath(routeG, pts, 0x07090f, 7);
    dashPath(routeG, pts, color, 3, route.mode === "boat" ? 3 : 12, route.mode === "boat" ? 8 : 8, offset);
    const length = pathLength(pts);
    if (length < 1) continue;
    const marker = pointAlong(pts, reduce ? length * 0.45 : offset % length);
    routeG.circle(marker[0], marker[1], route.mode === "boat" ? 5.5 : 4.2).fill({ color });
    routeG.circle(marker[0], marker[1], route.mode === "boat" ? 5.5 : 4.2).stroke({ color: INK, width: 1.2 });
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
  floodG.alpha = floodAlpha;
  world.addChild(floodG);

  const courtyards = new Graphics();
  courtyards.eventMode = "none";
  buildCourtyards(courtyards);
  world.addChild(courtyards);

  const roadMarks = new Graphics();
  roadMarks.eventMode = "none";
  buildRoadMarks(roadMarks);
  world.addChild(roadMarks);

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
  drawRoutes(0);
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
  return { left: narrow ? 12 : 330, right: narrow ? 16 : 360, top: 72 };
}

function viewCenter() {
  const inset = viewInsets();
  return [(inset.left + app.screen.width - inset.right) / 2, app.screen.height / 2];
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
  renderPanel();
  if (building && building.household && building.household.location_label && building.household.location_label.includes("District")) {
    loadContext(building.household.location_label.split(",")[0]);
  }
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

function renderPanel() {
  const panel = document.getElementById("panel");
  panel.replaceChildren();
  const api = el("p");
  api.append(el("span", live.health ? "chip live" : "chip off", live.health ? "API connected" : "Local data only"));
  if (live.health && live.health.impl) {
    api.append(el("span", "chip", "S1 " + live.health.impl.S1_IMPL));
    api.append(el("span", "chip", "S2 " + live.health.impl.S2_IMPL));
  }
  panel.append(api);

  const jumps = el("div", "jump-row");
  for (const route of town.routes) {
    const button = el("button", null, route.fixture_id + " " + route.mode);
    button.type = "button";
    button.addEventListener("click", () => {
      activeRoutes.add(route.id);
      syncRouteChecks();
      drawRoutes(0);
      const target = town.buildings.find((candidate) => candidate.fixture_id === route.fixture_id);
      select(target ? target.id : route.to_building, true);
    });
    jumps.append(button);
  }
  panel.append(jumps);

  const building = selected ? buildingById(selected) : null;
  if (!building) {
    panel.append(el("h2", null, "Select a block"));
    panel.append(el("p", "muted", "Each house is an object with an id. Street names are placeholders. Household location_label stays a district, not an address."));
    panel.append(resourceList());
    panel.append(contextBlock());
    return;
  }

  panel.append(el("h2", null, building.name_en || building.name_th || building.id));
  panel.append(el("p", "muted", building.id + " · " + building.kind + " · " + building.floors + (building.floors > 1 ? " storeys" : " storey")));
  const street = streetById[building.street_id];
  if (street) panel.append(el("p", null, "Beside " + street.name_en + ". Not a stored address."));
  const chips = el("p");
  chips.append(el("span", "chip", building.sim_status.replaceAll("_", " ")));
  chips.append(el("span", "chip", "water " + building.water_m + " m"));
  if (building.fixture_id) chips.append(el("span", "chip", building.fixture_id));
  panel.append(chips);

  if (building.household) {
    panel.append(el("h3", null, "Mark household"));
    const row = el("div", "status-row");
    for (const status of STATUSES) {
      const button = el("button", null, status.replaceAll("_", " "));
      button.type = "button";
      button.setAttribute("aria-pressed", String(building.sim_status === status));
      button.addEventListener("click", () => setStatus(building.household.household_id, status));
      row.append(button);
    }
    panel.append(row);
    panel.append(el("h3", null, "Household contract"));
    const list = document.createElement("dl");
    for (const [key, value] of Object.entries(building.household)) {
      list.append(el("dt", null, key));
      list.append(el("dd", null, value == null ? "—" : Array.isArray(value) ? value.join(", ") : String(value)));
    }
    panel.append(list);
    const details = document.createElement("details");
    details.append(el("summary", null, "Household JSON"));
    const pre = el("pre");
    pre.textContent = JSON.stringify(building.household, null, 2);
    details.append(pre);
    panel.append(details);
  }

  if (building.fixture) {
    panel.append(el("h3", null, "Fixture " + building.fixture.fixture_id));
    panel.append(el("p", null, building.fixture.title));
    const expected = el("p");
    expected.append(el("span", "chip", building.fixture.expected_system.replaceAll("_", " ")));
    expected.append(el("span", "chip " + building.fixture.expected_priority.toLowerCase(), building.fixture.expected_priority));
    expected.append(el("span", "chip", building.fixture.expected_route));
    panel.append(expected);
    if (building.also_fixture_ids) panel.append(el("p", "muted", "Same household as " + building.also_fixture_ids.join(", ") + "."));
    const run = el("button", null, "Run gateway triage");
    run.type = "button";
    run.addEventListener("click", () => runTriage(building.fixture_id));
    panel.append(run);
    const callOnBuilding = town.calls.find((call) => call.building_id === building.id && live.triage && live.triage.forId === call.id);
    const triageId = callOnBuilding ? callOnBuilding.id : building.fixture_id;
    if (live.triage && live.triage.forId === triageId && live.triage.caseState) {
      const decision = live.triage.decision;
      panel.append(el("p", null, "Router: " + decision.next_action + " · " + decision.final_priority + " · " + decision.final_route));
      const source = decision.source_outcomes && decision.source_outcomes[0];
      if (source) panel.append(el("p", "muted", source.reason));
      mountCorrection(panel, triageId);
    } else if (live.triageError && live.triageError.forId === building.fixture_id) {
      panel.append(el("p", "error", live.triageError.message));
    }
  }

  if (building.resource_id) {
    const resource = (town.resources || []).find((row) => row.resource_id === building.resource_id);
    if (resource) {
      panel.append(el("h3", null, "Resource"));
      panel.append(el("p", null, resource.name + " · " + resource.kind + " · " + (resource.district || "")));
    }
  }
  panel.append(contextBlock());
}

function resourceList() {
  const wrap = el("div");
  wrap.append(el("h3", null, "Resources"));
  const list = el("ul", "plain");
  const rows = live.resources
    ? [].concat(live.resources.boats, live.resources.ambulances, live.resources.shelters, live.resources.welfare_points)
    : town.resources.map((row) => ({ id: row.resource_id, name: row.name, district: row.district }));
  for (const row of rows) {
    const item = el("li");
    const button = el("button", null, row.name + " · " + row.district);
    button.type = "button";
    button.addEventListener("click", () => {
      const building = town.buildings.find((candidate) => candidate.resource_id === (row.id || row.resource_id));
      if (building) select(building.id, true);
    });
    item.append(button);
    list.append(item);
  }
  wrap.append(list, el("p", "muted", live.resources ? "From GET /resources." : "Copy of mocks/resources.json baked into the town file."));
  return wrap;
}

function contextBlock() {
  const wrap = el("div");
  wrap.append(el("h3", null, "Flood context"));
  if (!live.context) {
    wrap.append(el("p", "muted", "GET /context is the live district lookup. The sheet on the block is flood.json. /map/flood stays in WGS84 and is not drawn on these plots."));
    return wrap;
  }
  wrap.append(el("p", null, live.context.matched_district || "No district match"));
  const chips = el("p");
  for (const key of ["in_flood_extent_1d", "in_flood_extent_7d", "in_flood_extent_30d", "repeat_flood_area", "in_flood_risk_layer", "in_observed_event_extent"]) {
    if (live.context[key]) chips.append(el("span", "chip", key.replaceAll("_", " ")));
  }
  if (!chips.childNodes.length) chips.append(el("span", "chip", "no extent flag"));
  wrap.append(chips);
  if (live.context.rainfall_last_24h_mm != null) {
    wrap.append(el("p", "muted", "Rain last 24h " + live.context.rainfall_last_24h_mm + " mm. Forecast " + live.context.rainfall_forecast_24h_mm + " mm."));
  }
  return wrap;
}

async function getJson(url, options) {
  const response = await fetch(url, options);
  if (!response.ok) throw new Error(url + " returned " + response.status);
  return response.json();
}

async function loadContext(district) {
  try {
    live.context = await getJson("/context?district=" + encodeURIComponent(district));
    renderPanel();
  } catch (error) {
    live.context = null;
  }
}

function labelNames() {
  const names = {};
  for (const row of (live.labels && live.labels.labels) || []) {
    if (row && row.id) names[row.id] = row.label || row.id;
  }
  return names;
}

function mountCorrection(panel, fixtureId) {
  if (!live.triage || live.triage.forId !== fixtureId || !live.triage.caseState) return;
  const host = el("div");
  panel.append(host);
  const note = live.correctionNote && live.correctionNote.forId === fixtureId ? live.correctionNote : null;
  mountCorrectForm(host, {
    caseState: live.triage.caseState,
    decision: live.triage.decision,
    fixtureId,
    policyVersion: (live.labels && live.labels.version) || "",
    labelNames: labelNames(),
    note,
    onResult: (result) => {
      live.correctionNote = { forId: fixtureId, ok: result.ok, text: result.text };
      if (result.decision && live.triage && live.triage.forId === fixtureId) {
        live.triage = { ...live.triage, decision: result.decision };
      }
      if (result.ok) renderPanel();
    },
  });
}

async function runTriage(fixtureId) {
  live.triageError = null;
  live.correctionNote = null;
  try {
    const fixture = await getJson("/fixtures/" + fixtureId);
    const decision = await getJson("/triage", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fixture.case_state),
    });
    live.triage = { forId: fixtureId, decision, caseState: fixture.case_state };
  } catch (error) {
    live.triage = null;
    live.triageError = { forId: fixtureId, message: error.message };
  }
  renderPanel();
}

async function loadLive() {
  try {
    live.health = await getJson("/health");
  } catch (error) {
    live.health = null;
  }
  try {
    live.resources = await getJson("/resources");
  } catch (error) {
    live.resources = null;
  }
  try {
    live.labels = await getJson("/policies/labels");
  } catch (error) {
    live.labels = null;
  }
  await loadContext("Mueang Phrae District");
  renderPanel();
}

function syncRouteChecks() {
  document.querySelectorAll("[data-route]").forEach((input) => {
    input.checked = activeRoutes.has(input.dataset.route);
  });
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
    if (decision) lit.set(call.building_id, decision.final_priority);
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
    if (answer) lit.set(item.building_id, answer.final_priority);
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
      runCall(call);
    });
    item.append(button);
    list.append(item);
  }
  renderCallLegend();
}

function showReadout(call, decision, error) {
  const box = document.getElementById("mubit-readout");
  box.replaceChildren();
  box.append(el("p", "msg", call.opening));
  const hops = el("ol", "hops");
  hops.append(el("li", null, "Call " + call.id));
  hops.append(el("li", null, "GET /fixtures/" + call.id));
  hops.append(el("li", null, "POST /triage"));
  hops.append(el("li", "mubit", "Mubit gateway"));
  if (decision) {
    const source = decision.source_outcomes && decision.source_outcomes[0];
    hops.append(el("li", null, source ? String(source.system).replaceAll("_", " ") : "system"));
    hops.append(el("li", null, decision.final_priority + " · " + decision.final_route));
    hops.append(el("li", null, String(decision.next_action).replaceAll("_", " ")));
    const note = (decision.policy_notes || []).find((line) => String(line).toLowerCase().includes("mubit"));
    if (note) box.append(el("p", "muted", note));
  } else if (error) {
    hops.append(el("li", "error", error));
  } else {
    hops.append(el("li", "muted", "Sending"));
  }
  box.append(hops);
}

function syncPlayButton() {
  const button = document.getElementById("calls-play");
  button.textContent = callPlaying ? "Pause" : "Play 20 calls";
}

async function runCall(call) {
  activeCallId = call.id;
  renderCallList();
  const row = document.querySelector("#call-list li.active");
  if (row) row.scrollIntoView({ block: "nearest" });
  const node = document.getElementById("mubit-node");
  node.classList.add("busy");
  node.classList.remove("done");
  showReadout(call, null, null);
  updateCallLink();
  select(call.building_id, false);
  try {
    const fixture = await getJson("/fixtures/" + encodeURIComponent(call.id));
    const decision = await getJson("/triage", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(fixture.case_state),
    });
    callResults.set(call.id, decision);
    live.triage = { forId: call.id, decision, caseState: fixture.case_state };
    live.correctionNote = null;
    showReadout(call, decision, null);
    node.classList.remove("busy");
    node.classList.add("done");
  } catch (error) {
    callResults.delete(call.id);
    showReadout(call, null, error.message);
    node.classList.remove("busy");
  }
  drawCallLights();
  renderCallList();
  updateCallLink();
  renderPanel();
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
    await runCall(call);
    if (!callPlaying || token !== callToken) break;
    await new Promise((resolve) => setTimeout(resolve, 650));
  }
  if (token === callToken) callPlaying = false;
  syncPlayButton();
}

function resetCalls() {
  callPlaying = false;
  callToken += 1;
  callCursor = 0;
  callResults = new Map();
  activeCallId = null;
  live.triage = null;
  const node = document.getElementById("mubit-node");
  node.classList.remove("busy", "done");
  document.getElementById("mubit-readout").replaceChildren();
  drawCallLights();
  renderCallList();
  updateCallLink();
  syncPlayButton();
  renderPanel();
}

function bindChrome() {
  document.getElementById("flood-opacity").addEventListener("input", (event) => {
    floodAlpha = Number(event.target.value) / 100;
    if (floodG) floodG.alpha = floodAlpha;
  });
  document.getElementById("view-fit").addEventListener("click", fitTown);
  document.getElementById("calls-play").addEventListener("click", () => playCalls());
  document.getElementById("calls-step").addEventListener("click", () => {
    callPlaying = false;
    syncPlayButton();
    if (callCursor >= town.calls.length) return;
    const call = town.calls[callCursor];
    callCursor += 1;
    runCall(call);
  });
  document.getElementById("calls-reset").addEventListener("click", resetCalls);
  renderCallList();
  document.getElementById("view-dispatch").addEventListener("click", () => {
    const camera = town.meta.camera;
    lookAt(camera.look_at[0], camera.look_at[1], camera.zoom_px_per_m);
  });
  const box = document.getElementById("route-toggles");
  for (const route of town.routes) {
    const label = el("label", "check");
    const input = document.createElement("input");
    input.type = "checkbox";
    input.dataset.route = route.id;
    input.checked = true;
    activeRoutes.add(route.id);
    input.addEventListener("change", () => {
      if (input.checked) activeRoutes.add(route.id);
      else activeRoutes.delete(route.id);
      drawRoutes(0);
    });
    label.append(input, document.createTextNode(" " + route.fixture_id + " " + route.mode));
    box.append(label);
  }
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
  const [townBody, streetBody, floodBody] = await Promise.all([
    getJson("data/town.json"),
    getJson("data/streets.json"),
    getJson("data/flood.json"),
  ]);
  town = townBody;
  streets = streetBody.streets;
  flood = floodBody;
  streetById = Object.fromEntries(streets.map((street) => [street.id, street]));
  nodeById = Object.fromEntries(town.graph.nodes.map((node) => [node.id, node]));
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
  document.getElementById("panel").hidden = false;
  document.getElementById("graph-stat").textContent =
    town.graph.nodes.length + " junctions · " + town.graph.edges.length + " links · " + town.buildings.length + " blocks";
  bindChrome();
  const camera = town.meta.camera;
  lookAt(camera.look_at[0], camera.look_at[1], camera.zoom_px_per_m);
  renderPanel();
  const hash = decodeURIComponent(location.hash.replace("#", ""));
  if (hash && buildingById(hash)) select(hash, true);
  let offset = 0;
  app.ticker.add((ticker) => {
    if (reduce) return;
    offset += ticker.deltaMS * 0.04;
    drawRoutes(offset);
    markerG.alpha = 0.55 + 0.45 * Math.sin(ticker.lastTime / 260);
    if (callLightG) callLightG.alpha = 0.72 + 0.28 * Math.sin(ticker.lastTime / 280);
  });
  loadLive();
}

window.BaanSafeSim = {
  setStatus,
  select: (id) => select(id, true),
  getBuilding: (id) => (town ? buildingById(id) : null),
};

main().catch((error) => {
  const loading = document.getElementById("loading");
  loading.hidden = false;
  loading.textContent = "Could not start the town view. Serve this folder over HTTP. " + error.message;
});
