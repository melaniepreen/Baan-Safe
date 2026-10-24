/* Walk the town graph that build_town.py already drew.

   A vehicle may only move along these edges. The walk never invents a
   chord across a roof. Prefer one mode when the edge allows it.
*/

function inside(building, x, y) {
  return building.x + 0.15 < x && x < building.x + building.w - 0.15 && building.y + 0.15 < y && y < building.y + building.d - 0.15;
}

export function nearestNode(nodes, buildings, x, y) {
  let best = null;
  let bestD = Infinity;
  for (const node of nodes) {
    if (buildings.some((building) => inside(building, node.x, node.y))) continue;
    const d = (node.x - x) ** 2 + (node.y - y) ** 2;
    if (d < bestD) {
      bestD = d;
      best = node;
    }
  }
  return best;
}

export function walk(edges, start, goal) {
  if (!start || !goal) return null;
  if (start === goal) return [start];
  const adj = new Map();
  for (const edge of edges) {
    if (!adj.has(edge.from)) adj.set(edge.from, []);
    if (!adj.has(edge.to)) adj.set(edge.to, []);
    adj.get(edge.from).push(edge);
    adj.get(edge.to).push(edge);
  }
  const dist = new Map([[start, 0]]);
  const prev = new Map();
  const queue = [start];
  while (queue.length) {
    let best = 0;
    for (let i = 1; i < queue.length; i++) {
      if (dist.get(queue[i]) < dist.get(queue[best])) best = i;
    }
    const node = queue.splice(best, 1)[0];
    if (node === goal) break;
    for (const edge of adj.get(node) || []) {
      const next = edge.from === node ? edge.to : edge.from;
      const cost = dist.get(node) + edge.length_m;
      if (cost < (dist.get(next) ?? Infinity)) {
        dist.set(next, cost);
        prev.set(next, node);
        if (!queue.includes(next)) queue.push(next);
      }
    }
  }
  if (!prev.has(goal) && start !== goal) return null;
  const path = [goal];
  let cursor = goal;
  while (cursor !== start) {
    cursor = prev.get(cursor);
    if (!cursor) return null;
    path.push(cursor);
  }
  path.reverse();
  return path;
}

export function legsFromPath(edges, nodeIds, prefer = "boat") {
  const index = new Map();
  for (const edge of edges) {
    index.set(edge.from + "|" + edge.to, edge);
    index.set(edge.to + "|" + edge.from, edge);
  }
  const legs = [];
  let current = null;
  for (let i = 1; i < nodeIds.length; i++) {
    const edge = index.get(nodeIds[i - 1] + "|" + nodeIds[i]);
    if (!edge) return [];
    let mode = "foot";
    if (edge.modes.includes(prefer)) mode = prefer;
    else if (edge.modes.includes("boat")) mode = "boat";
    else if (edge.modes.includes("road")) mode = "road";
    else mode = edge.modes[0] || "foot";
    if (!current || current.mode !== mode) {
      current = { mode, node_ids: [nodeIds[i - 1]] };
      legs.push(current);
    }
    current.node_ids.push(nodeIds[i]);
  }
  return legs;
}
