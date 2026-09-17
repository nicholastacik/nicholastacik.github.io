// Pure, DOM-free spaced-repetition scheduler + session queue for the research page's
// Practice mode. No imports, no Date.now()/Math.random() inside — time and rng are
// passed in. The single trailing `export { ... }` is stripped when inlined into the page.

const INTERVAL_DAYS = [0, 1, 3, 7, 21];
const DAY_MS = 86400000;

function nextBox(box, grade) {
  if (grade === "missed") return 0;
  if (grade === "knew") return Math.min(4, box + 1);
  return box; // 'unsure' holds
}

function dueAfter(now, box) {
  return now + INTERVAL_DAYS[box] * DAY_MS;
}

function applyGrade(card, grade, now, promote) {
  const box = card ? card.box : 0;
  if (!promote) {
    if (grade === "missed") return { box: 0, due: now, seen: now };
    return { box, due: card ? card.due : dueAfter(now, box), seen: now };
  }
  const nb = nextBox(box, grade);
  return { box: nb, due: dueAfter(now, nb), seen: now };
}

export { INTERVAL_DAYS, nextBox, dueAfter, applyGrade };
