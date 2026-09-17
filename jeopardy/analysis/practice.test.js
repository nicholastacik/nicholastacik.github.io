import { test } from "node:test";
import assert from "node:assert/strict";
import { INTERVAL_DAYS, nextBox, dueAfter, applyGrade, assembleSession } from "./practice.js";

const DAY = 86400000;

test("nextBox promotes, clamps at 4, resets on miss, holds on unsure", () => {
  assert.equal(nextBox(0, "knew"), 1);
  assert.equal(nextBox(4, "knew"), 4);
  assert.equal(nextBox(2, "unsure"), 2);
  assert.equal(nextBox(3, "missed"), 0);
});

test("dueAfter uses INTERVAL_DAYS per box", () => {
  assert.deepEqual(INTERVAL_DAYS, [0, 1, 3, 7, 21]);
  assert.equal(dueAfter(1000, 0), 1000);
  assert.equal(dueAfter(1000, 1), 1000 + 1 * DAY);
  assert.equal(dueAfter(1000, 4), 1000 + 21 * DAY);
});

test("applyGrade normal: new card knew -> box1 due tomorrow", () => {
  assert.deepEqual(applyGrade(null, "knew", 1000, true), { box: 1, due: 1000 + DAY, seen: 1000 });
});

test("applyGrade normal: unsure holds box, miss resets to box0 due now", () => {
  assert.deepEqual(applyGrade({ box: 2, due: 5, seen: 5 }, "unsure", 1000, true), { box: 2, due: 1000 + 3 * DAY, seen: 1000 });
  assert.deepEqual(applyGrade({ box: 3, due: 5, seen: 5 }, "missed", 1000, true), { box: 0, due: 1000, seen: 1000 });
});

test("applyGrade extra: correct leaves box+due unchanged, updates seen", () => {
  assert.deepEqual(applyGrade({ box: 3, due: 777, seen: 1 }, "knew", 1000, false), { box: 3, due: 777, seen: 1000 });
  assert.deepEqual(applyGrade({ box: 2, due: 888, seen: 1 }, "unsure", 1000, false), { box: 2, due: 888, seen: 1000 });
});

test("applyGrade extra: miss still resets", () => {
  assert.deepEqual(applyGrade({ box: 4, due: 999, seen: 1 }, "missed", 1000, false), { box: 0, due: 1000, seen: 1000 });
});

test("assembleSession: due before unseen, future excluded when not extra", () => {
  const store = { a: { box: 0, due: 500, seen: 1 }, b: { box: 1, due: 2000, seen: 1 } };
  const ids = assembleSession(["a", "b", "c", "d"], store, 1000, 10, false, () => 0);
  assert.equal(ids[0], "a");            // due first
  assert.ok(!ids.includes("b"));        // future excluded when extra=false
  assert.deepEqual(ids.slice(1).sort(), ["c", "d"]); // unseen included
});

test("assembleSession: future tier included only when extra", () => {
  const store = { b: { box: 1, due: 2000, seen: 1 } };
  assert.deepEqual(assembleSession(["b"], store, 1000, 10, true, () => 0), ["b"]);
});

test("assembleSession: truncates to size", () => {
  assert.equal(assembleSession(["a", "b", "c", "d", "e"], {}, 1000, 3, false, () => 0).length, 3);
});

test("assembleSession: shuffles unseen deterministically via rng", () => {
  // rng()===0 -> Fisher-Yates swaps each i with index 0: ["a","b","c"] -> ["b","c","a"]
  assert.deepEqual(assembleSession(["a", "b", "c"], {}, 1000, 3, false, () => 0), ["b", "c", "a"]);
});

import { initSession, gradeCurrent, sessionProgress } from "./practice.js";

test("gradeCurrent drops a card on a non-missed grade", () => {
  let s = initSession(["a", "b"]);
  s = gradeCurrent(s, "knew");
  assert.deepEqual(s.queue.map(e => e.id), ["b"]);
  assert.deepEqual(sessionProgress(s), { done: 1, size: 2, retriesPending: 0 });
});

test("gradeCurrent requeues a first miss once at min(3, remaining)", () => {
  let s = initSession(["a", "b", "c", "d", "e"]);
  s = gradeCurrent(s, "missed"); // pop a; 4 remain; insert at index 3
  assert.deepEqual(s.queue.map(e => e.id), ["b", "c", "d", "a", "e"]);
  assert.equal(s.queue.find(e => e.id === "a").retried, true);
  assert.deepEqual(sessionProgress(s), { done: 0, size: 5, retriesPending: 1 });
});

test("a second miss of the same card does not requeue (finite retries)", () => {
  let s = initSession(["a"]);
  s = gradeCurrent(s, "missed");                 // -> [a(retried)]
  assert.deepEqual(s.queue.map(e => e.id), ["a"]);
  assert.deepEqual(sessionProgress(s), { done: 0, size: 1, retriesPending: 1 });
  s = gradeCurrent(s, "missed");                 // already retried -> dropped
  assert.deepEqual(s.queue, []);
  assert.deepEqual(sessionProgress(s), { done: 1, size: 1, retriesPending: 0 });
});

test("missing the final card yields exactly one retry", () => {
  let s = initSession(["a", "b"]);
  s = gradeCurrent(s, "knew");                   // -> [b]
  s = gradeCurrent(s, "missed");                 // pop b; 0 remain; insert at index 0
  assert.deepEqual(s.queue.map(e => e.id), ["b"]);
  s = gradeCurrent(s, "missed");                 // retried -> dropped, session ends
  assert.deepEqual(s.queue, []);
});

import { sanitizeStore } from "./practice.js";

test("sanitizeStore returns empty on wrong/missing version or bad shape", () => {
  assert.deepEqual(sanitizeStore(null), { v: 1, cards: {} });
  assert.deepEqual(sanitizeStore({ v: 2, cards: { a: { box: 0, due: 1, seen: 1 } } }), { v: 1, cards: {} });
  assert.deepEqual(sanitizeStore({ cards: {} }), { v: 1, cards: {} });
  assert.deepEqual(sanitizeStore({ v: 1, cards: null }), { v: 1, cards: {} });
});

test("sanitizeStore drops invalid records, keeps valid ones", () => {
  const parsed = { v: 1, cards: {
    good: { box: 2, due: 100, seen: 50 },
    badBox: { box: 9, due: 100, seen: 50 },
    floatBox: { box: 1.5, due: 100, seen: 50 },
    nanDue: { box: 0, due: NaN, seen: 50 },
    infSeen: { box: 0, due: 100, seen: Infinity },
    notObj: 5,
  } };
  assert.deepEqual(sanitizeStore(parsed), { v: 1, cards: { good: { box: 2, due: 100, seen: 50 } } });
});
