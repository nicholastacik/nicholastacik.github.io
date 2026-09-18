import { test } from "node:test";
import assert from "node:assert/strict";
import { pickSession } from "./practice.js";

test("pickSession returns up to size distinct ids from the pool", () => {
  const pool = ["a", "b", "c", "d", "e"];
  const out = pickSession(pool, 3, () => 0);
  assert.equal(out.length, 3);
  assert.equal(new Set(out).size, 3); // distinct
  out.forEach((id) => assert.ok(pool.includes(id)));
});

test("pickSession returns the whole pool when size exceeds it", () => {
  const out = pickSession(["a", "b"], 10, () => 0);
  assert.deepEqual(out.slice().sort(), ["a", "b"]);
});

test("pickSession shuffles deterministically via rng", () => {
  // rng()===0 -> Fisher-Yates swaps each i with index 0: ["a","b","c"] -> ["b","c","a"]
  assert.deepEqual(pickSession(["a", "b", "c"], 3, () => 0), ["b", "c", "a"]);
});

test("pickSession does not mutate the input pool", () => {
  const pool = ["a", "b", "c"];
  pickSession(pool, 2, () => 0);
  assert.deepEqual(pool, ["a", "b", "c"]);
});
