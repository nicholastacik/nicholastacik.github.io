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
