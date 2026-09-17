import { test } from "node:test";
import assert from "node:assert/strict";
import { INTERVAL_DAYS, nextBox, dueAfter, applyGrade } from "./practice.js";

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
