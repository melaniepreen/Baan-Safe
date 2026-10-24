import { readFileSync } from "node:fs";
import { LANDMARKS, locationLine, matchLandmark, soiName } from "./landmarks.js";

function assert(cond, message) {
  if (!cond) throw new Error(message);
}

const town = JSON.parse(readFileSync(new URL("./data/town.json", import.meta.url), "utf8"));
const prompts = JSON.parse(readFileSync(new URL("./data/prompts.json", import.meta.url), "utf8"));
const byCall = Object.fromEntries(town.calls.map((call) => [call.id, call.building_id]));
const byBuilding = Object.fromEntries(town.buildings.map((building) => [building.id, building]));

assert(matchLandmark("I am near Baan Chompoo Apartment").id === "chompoo", "chompoo");
assert(matchLandmark("I am beside Khlong Saen Saep and I can see Wat That Thong").id === "khlong", "khlong before temple");
assert(matchLandmark("I am next to a temple and surrounded by many trees").id === "temple-trees", "temple");

const pins = [];
for (const group of prompts.groups) {
  for (const prompt of group.prompts) {
    const landmark = matchLandmark(prompt.en);
    const buildingId = landmark ? landmark.buildingId : byCall[prompt.fixture_id];
    assert(byBuilding[buildingId], "missing " + buildingId);
    pins.push({ id: prompt.id, fixture: prompt.fixture_id, buildingId });
  }
}
const shared = new Map();
for (const row of pins) {
  if (shared.has(row.fixture)) assert(shared.get(row.fixture) === row.buildingId, row.fixture + " split");
  else shared.set(row.fixture, row.buildingId);
}
const buildings = [...shared.values()];
assert(new Set(buildings).size === buildings.length, "two fixtures share " + buildings.join(","));
for (const row of LANDMARKS) {
  assert(row.confidence >= 0.55 && row.confidence <= 0.7, row.id + " confidence");
  assert(!buildings.filter((id) => id === row.buildingId).length || shared.get(row.fixtureId) === row.buildingId, "pin reused");
}
const temple = byBuilding["bldg-0328"];
const line = locationLine(temple, LANDMARKS.find((row) => row.id === "temple-trees"));
assert(line.includes("bldg-0328"), line);
assert(line.includes(soiName(temple.x + temple.w / 2, temple.y + temple.d / 2)), line);
assert(!/gps|latitude|longitude/i.test(line), line);
const rice = pins.find((row) => row.id === "s1-rice");
const oxygen = pins.find((row) => row.id === "s2-oxygen");
const rent = pins.find((row) => row.id === "sap-rent");
const sister = pins.find((row) => row.id === "sap-sister");
assert(new Set([rice, oxygen, rent, sister, ...LANDMARKS].map((row) => row.buildingId)).size === 7, "demo pins");
console.log("landmarks ok");
