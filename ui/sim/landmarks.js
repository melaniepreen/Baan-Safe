/* Landmark guesses for callers who do not know a house number.

   Each row pins a different drawn building. The fixture id is only the
   stub gateway's script. The pin is not that fixture's house, and it is
   not a device GPS fix.
*/

export const PHONE_NAME = "Baan-Safe";
export const PHONE_NUMBER = "+66 81 555 0149";

const SUKHUMVIT_Y = 196;
const SOIS = [
  { x: 48, north: "Soi Sukhumvit 39", south: "Soi Sukhumvit 24" },
  { x: 132, north: "Soi Sukhumvit 49", south: "Soi Sukhumvit 36" },
  { x: 228, north: "Soi Sukhumvit 55", south: "Soi Sukhumvit 38" },
  { x: 324, north: null, south: "Soi Sukhumvit 40" },
  { x: 420, north: "Soi Sukhumvit 63", south: "Soi Sukhumvit 42" },
];

export function soiName(x, y) {
  const south = y >= SUKHUMVIT_Y;
  const options = SOIS.filter((soi) => (south ? soi.south : soi.north));
  let best = options[0];
  let bestD = Infinity;
  for (const soi of options) {
    const distance = Math.abs(x - soi.x);
    if (distance < bestD) {
      best = soi;
      bestD = distance;
    }
  }
  return south ? best.south : best.north;
}

export const LANDMARKS = [
  {
    id: "chompoo",
    test: /baan chompoo|chompoo apartment/i,
    buildingId: "bldg-tower-pink",
    fixtureId: "F13",
    confidence: 0.64,
    landmarks: "Baan Chompoo Apartment",
  },
  {
    id: "khlong",
    test: /khlong saen saep|\bkhlong\b/i,
    buildingId: "bldg-0441",
    fixtureId: "C01-a",
    confidence: 0.58,
    landmarks: "Khlong Saen Saep + tree cluster",
  },
  {
    id: "temple-trees",
    test: /temple|wat that thong/i,
    buildingId: "bldg-0328",
    fixtureId: "F15",
    confidence: 0.66,
    landmarks: "Wat That Thong + tree cluster",
  },
];

export function matchLandmark(text) {
  const spoken = String(text || "");
  return LANDMARKS.find((row) => row.test.test(spoken)) || null;
}

const STREET_X = {
  "soi-chamlong-khlong": 48,
  "soi-chamlong-wat-fa": 132,
  "soi-chamlong-talat": 228,
  "soi-chamlong-ho-nuea": 324,
  "soi-chamlong-fai": 420,
};

export function locationLine(building, landmark) {
  const x = building.x + building.w / 2;
  const y = building.y + building.d / 2;
  const axis = STREET_X[building.street_id];
  const soi = soiName(axis == null ? x : axis, y);
  if (landmark) {
    return (
      "Location approximated from landmarks · " +
      landmark.landmarks +
      " · " +
      soi +
      " (est.) · " +
      building.id +
      " · confidence " +
      landmark.confidence.toFixed(2)
    );
  }
  const name = building.name_en || building.id;
  return "Location · " + name + " · " + soi + " · " + building.id;
}
