import { test } from "node:test";
import assert from "node:assert/strict";
import { HEADERS } from "./headers.js";
import { AuthError } from "./sheets.js";
import { StaleError, enqueue, markCard, perform, resume, resumePending, trackShow, untrackShow } from "./actions.js";

const IDS = { Tracked: 10, Cards: 20, Schedule: 30, Meta: 40 };

function world({ tracked = [], cardKeys = ["card_id"], failNext = null } = {}) {
  const sheets = {
    writes: [],
    reads: [],
    fail: failNext,
    async get(ranges) {
      sheets.reads.push(ranges);
      return ranges.map((range) =>
        range.startsWith("Tracked")
          ? [HEADERS.Tracked, ...tracked.map((row) => HEADERS.Tracked.map((c) => row[c] ?? ""))]
          : cardKeys.map((key) => [key]),
      );
    },
    async sheetIds() {
      return IDS;
    },
    async batchUpdate(requests) {
      if (sheets.fail) {
        const error = sheets.fail;
        sheets.fail = null;
        throw error;
      }
      sheets.writes.push(requests);
      for (const request of requests) {
        if (request.appendCells) {
          const values = request.appendCells.rows[0].values.map((cell) => Object.values(cell.userEnteredValue)[0]);
          tracked.push(Object.fromEntries(HEADERS.Tracked.map((column, i) => [column, values[i]])));
        }
      }
    },
  };
  const ctx = { sheets, nowIso: () => "T", today: () => "2026-09-28", pending: [], asked: 0, onAuthNeeded: () => { ctx.asked += 1; } };
  return ctx;
}

test("markCard writes when the key still matches", async () => {
  const ctx = world({ cardKeys: ["card_id", "ep:1:S01E01"] });
  await markCard(ctx, { _row: 2, card_id: "ep:1:S01E01" }, "noted");
  assert.equal(ctx.sheets.writes.length, 1);
  assert.equal(ctx.sheets.writes[0][0].updateCells.range.startRowIndex, 1);
});

test("markCard aborts with StaleError when the row moved", async () => {
  const ctx = world({ cardKeys: ["card_id", "hand-inserted", "ep:1:S01E01"] });
  await assert.rejects(markCard(ctx, { _row: 2, card_id: "ep:1:S01E01" }, "noted"), StaleError);
  assert.equal(ctx.sheets.writes.length, 0);
});

test("trackShow reads Tracked and Cards in one batchGet and writes once", async () => {
  const ctx = world({ cardKeys: ["card_id", "sugg:9"] });
  await trackShow(ctx, { tmdb_id: 9, name: "Nine", first_air_year: 2025, poster_url: "" }, "suggestion", { _row: 2, card_id: "sugg:9" });
  assert.deepEqual(ctx.sheets.reads, [["Tracked!A:J", "Cards!A:A"]]);
  assert.equal(ctx.sheets.writes.length, 1);
  assert.deepEqual(ctx.sheets.writes[0].map((r) => Object.keys(r)[0]), ["updateCells", "appendCells"]);
});

test("untrackShow deactivates rows another device appended after page load", async () => {
  const tracked = [
    { tmdb_id: 1, name: "One", active: true },
    { tmdb_id: 2, name: "Two", active: true },
    { tmdb_id: 1, name: "One", active: true },
  ];
  const ctx = world({ tracked });
  await untrackShow(ctx, 1);
  assert.deepEqual(ctx.sheets.writes[0].map((r) => r.updateCells.range.startRowIndex), [1, 3]);
});

test("perform keeps the action on AuthError and resumePending retries it once", async () => {
  const ctx = world({ cardKeys: ["card_id", "x"], failNext: new AuthError("expired") });
  const action = () => markCard(ctx, { _row: 2, card_id: "x" }, "noted");
  assert.equal(await perform(ctx, action), "pending");
  assert.equal(ctx.asked, 1);
  assert.deepEqual(ctx.pending, [action]);
  assert.equal(ctx.sheets.writes.length, 0);
  assert.equal(await resumePending(ctx), "done");
  assert.deepEqual(ctx.pending, []);
  assert.equal(ctx.sheets.writes.length, 1);
  assert.equal(await resumePending(ctx), null);
});

test("perform rethrows non-auth errors", async () => {
  const ctx = world({ cardKeys: ["card_id", "x"], failNext: new Error("boom") });
  await assert.rejects(perform(ctx, () => markCard(ctx, { _row: 2, card_id: "x" }, "noted")), /boom/);
  assert.deepEqual(ctx.pending, []);
});

test("enqueue runs Track then Untrack in order so Untrack sees the new row", async () => {
  const ctx = world({ cardKeys: ["card_id"] });
  const show = { tmdb_id: 5, name: "Five", first_air_year: 2020, poster_url: "" };
  const first = enqueue(ctx, () => trackShow(ctx, show, "search"));
  const second = enqueue(ctx, () => untrackShow(ctx, 5));
  assert.deepEqual(await Promise.all([first, second]), ["done", "done"]);
  const untrackWrite = ctx.sheets.writes[1][0].updateCells;
  assert.equal(untrackWrite.range.startRowIndex, 1);
  assert.deepEqual(untrackWrite.rows[0].values[0], { userEnteredValue: { boolValue: false } });
});

test("actions made while signed out queue in order and all resume", async () => {
  const ctx = world({ cardKeys: ["card_id", "a", "b"], failNext: new AuthError("expired") });
  const one = enqueue(ctx, () => markCard(ctx, { _row: 2, card_id: "a" }, "noted"));
  const two = enqueue(ctx, () => markCard(ctx, { _row: 3, card_id: "b" }, "noted"));
  assert.deepEqual(await Promise.all([one, two]), ["pending", "pending"]);
  assert.equal(ctx.asked, 1);
  assert.equal(ctx.pending.length, 2);
  assert.equal(await resume(ctx), "done");
  assert.deepEqual(ctx.sheets.writes.map((w) => w[0].updateCells.range.startRowIndex), [1, 2]);
  assert.deepEqual(ctx.pending, []);
});

test("a failure in one queued action does not block the next", async () => {
  const ctx = world({ cardKeys: ["card_id", "x"], failNext: new Error("boom") });
  const one = enqueue(ctx, () => markCard(ctx, { _row: 2, card_id: "x" }, "noted"));
  const two = enqueue(ctx, () => markCard(ctx, { _row: 2, card_id: "x" }, "ignored"));
  await assert.rejects(one, /boom/);
  assert.equal(await two, "done");
});
