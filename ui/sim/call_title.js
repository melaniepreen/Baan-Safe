/* Short title for the call on screen.

   Prefer a title or summary already stored on the matched prompt or fixture.
   Otherwise use only needs, people, and danger words that appear in the
   message. If none of those are present, keep the first eight words.
*/

const PEOPLE = [
  ["grandmother", "Grandmother"],
  ["grandfather", "Grandfather"],
  ["mother", "Mother"],
  ["father", "Father"],
  ["baby", "Baby"],
  ["child", "Child"],
  ["neighbour", "Neighbour"],
  ["neighbor", "Neighbor"],
  ["elderly", "Elderly person"],
];

const NEEDS = [
  ["drinking water", "drinking water"],
  ["oxygen", "oxygen"],
  ["rice", "rice"],
  ["food", "food"],
  ["shelter", "shelter"],
  ["rent", "rent"],
  ["payment", "payment"],
  ["water", "water"],
];

function clean(value) {
  const text = String(value || "").replace(/\s+/g, " ").trim();
  return text && text.toLowerCase() !== "this call" ? text : "";
}

function wordsOf(text) {
  return String(text || "").replace(/\s+/g, " ").trim().split(" ").filter(Boolean);
}

function capWords(text, max) {
  const words = wordsOf(text);
  if (words.length <= max) return words.join(" ");
  return words.slice(0, max).join(" ") + "…";
}

function fallbackWords(message) {
  const words = wordsOf(message);
  if (!words.length) return "No call yet";
  if (words.length <= 8) {
    return words[0].charAt(0).toUpperCase() + words[0].slice(1) + (words.length > 1 ? " " + words.slice(1).join(" ") : "");
  }
  return words[0].charAt(0).toUpperCase() + words[0].slice(1) + " " + words.slice(1, 8).join(" ") + "…";
}

function fromMessage(message) {
  const lower = message.toLowerCase();
  const has = (phrase) => lower.includes(phrase);
  let person = "";
  for (const [needle, label] of PEOPLE) {
    if (has(needle)) {
      person = label;
      break;
    }
  }
  const needs = [];
  const foundNeeds = [];
  for (const [needle, label] of NEEDS) {
    const at = lower.indexOf(needle);
    if (at >= 0) foundNeeds.push({ at, label });
  }
  foundNeeds.sort((a, b) => a.at - b.at);
  for (const row of foundNeeds) {
    if (row.label === "water" && needs.includes("drinking water")) continue;
    if (!needs.includes(row.label)) needs.push(row.label);
  }
  let danger = "";
  if (has("water is rising") || has("water rising") || (has("rising") && has("water"))) danger = "water rising";
  else if (has("at the door") && has("water")) danger = "water at the door";
  else if (has("cannot get out of bed")) danger = "cannot get out of bed";
  else if (has("cannot walk") || has("can't walk") || has("immobile")) danger = "cannot walk";
  else if (has("trapped")) danger = "trapped";
  else if (has("flood")) danger = "flood";

  const listed = danger.startsWith("water") ? needs.filter((need) => need !== "water") : needs;
  let sentence = "";
  if (person && listed.length) sentence = person + " needs " + listed.slice(0, 2).join(" and ");
  else if (listed.length) sentence = "Asking for " + listed.slice(0, 3).join(" and ");
  else if (person) sentence = person + " calling";
  if (danger) {
    const dangerBit = sentence ? danger : danger.charAt(0).toUpperCase() + danger.slice(1);
    sentence = sentence ? sentence + ", " + dangerBit : dangerBit;
  }
  return capWords(sentence, 8);
}

export function callSummary({ title, summary, text } = {}) {
  const named = clean(summary) || clean(title);
  if (named) return named;
  const message = String(text || "").replace(/\s+/g, " ").trim();
  const built = message ? fromMessage(message) : "";
  if (built) return built;
  return fallbackWords(message);
}
