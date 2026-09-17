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

function _shuffle(arr, rng) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    const tmp = arr[i];
    arr[i] = arr[j];
    arr[j] = tmp;
  }
  return arr;
}

function assembleSession(pool, store, now, size, extra, rng) {
  const due = [], unseen = [], future = [];
  for (const id of pool) {
    const rec = store[id];
    if (!rec) unseen.push(id);
    else if (rec.due <= now) due.push(id);
    else future.push(id);
  }
  due.sort((x, y) => store[x].due - store[y].due);
  _shuffle(unseen, rng);
  future.sort((x, y) => store[x].due - store[y].due);
  const ordered = extra ? due.concat(unseen, future) : due.concat(unseen);
  return ordered.slice(0, size);
}

function initSession(ids) {
  return { queue: ids.map(id => ({ id, retried: false })), size: ids.length };
}

function gradeCurrent(session, grade) {
  const queue = session.queue.slice();
  const cur = queue.shift();
  if (cur && grade === "missed" && !cur.retried) {
    const pos = Math.min(3, queue.length);
    queue.splice(pos, 0, { id: cur.id, retried: true });
  }
  return { queue, size: session.size };
}

function sessionProgress(session) {
  const remaining = new Set(session.queue.map(e => e.id));
  const retriesPending = session.queue.filter(e => e.retried).length;
  return { done: session.size - remaining.size, size: session.size, retriesPending };
}

export { INTERVAL_DAYS, nextBox, dueAfter, applyGrade, assembleSession, initSession, gradeCurrent, sessionProgress };
