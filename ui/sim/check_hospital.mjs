import { readFileSync } from "node:fs";
import { legsFromPath, nearestNode, walk } from "./route_walk.js";

const town = JSON.parse(readFileSync(new URL("./data/town.json", import.meta.url), "utf8"));
const clinic = town.buildings.find((building) => building.id === "bldg-clinic");
const clinicNode = nearestNode(town.graph.nodes, town.buildings, clinic.x + clinic.w / 2, clinic.y + clinic.d / 2);
if (!clinicNode) throw new Error("no clinic node");
const nodes = Object.fromEntries(town.graph.nodes.map((node) => [node.id, node]));

function inside(building, x, y) {
  return building.x + 0.15 < x && x < building.x + building.w - 0.15 && building.y + 0.15 < y && y < building.y + building.d - 0.15;
}

let checked = 0;
for (const call of town.calls) {
  const rescue = town.response_routes.find((route) => route.call_id === call.id && route.role === "rescue");
  const end = rescue.legs[rescue.legs.length - 1].node_ids.at(-1);
  const ids = walk(town.graph.edges, end, clinicNode.id);
  if (!ids || ids.length < 2) throw new Error("no hospital path for " + call.id);
  const legs = legsFromPath(town.graph.edges, ids, "boat");
  if (!legs.length) throw new Error("no legs for " + call.id);
  for (const leg of legs) {
    for (let i = 1; i < leg.node_ids.length; i++) {
      const left = leg.node_ids[i - 1];
      const right = leg.node_ids[i];
      const edge = town.graph.edges.find(
        (item) => item.modes.includes(leg.mode) && new Set([item.from, item.to]).size === 2 && [item.from, item.to].includes(left) && [item.from, item.to].includes(right)
      );
      if (!edge) throw new Error("gap " + call.id + " " + left + " " + right);
      const a = nodes[left];
      const b = nodes[right];
      const steps = Math.max(3, Math.round(edge.length_m / 2));
      for (let step = 0; step <= steps; step++) {
        const t = step / steps;
        const x = a.x + (b.x - a.x) * t;
        const y = a.y + (b.y - a.y) * t;
        for (const building of town.buildings) {
          if (inside(building, x, y)) throw new Error("inside " + building.id + " on " + call.id);
        }
      }
    }
  }
  checked += 1;
}
if (checked !== 20) throw new Error("checked " + checked);
console.log("hospital paths ok", clinicNode.id);
