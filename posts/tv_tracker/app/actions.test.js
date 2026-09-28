import { test } from "node:test";
import assert from "node:assert/strict";
import { HEADERS } from "./headers.js";
import { AuthError } from "./sheets.js";
import { StaleError, markCard, perform, resumePending, trackShow, untrackShow } from "./actions.js";

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
    },
  };
  const ctx = { sheets, nowIso: () => "T", today: () => "2026-09-28", pending: null, asked: 0, onAuthNeeded: () => { ctx.asked += 1; } };
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
  assert.deepEqual(ctx.sheets.reads, [["Tracked!A:I", "Cards!A:A"]]);
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
  assert.equal(ctx.pending, action);
  assert.equal(ctx.sheets.writes.length, 0);
  assert.equal(await resumePending(ctx), "done");
  assert.equal(ctx.pending, null);
  assert.equal(ctx.sheets.writes.length, 1);
  assert.equal(await resumePending(ctx), null);
});

test("perform rethrows non-auth errors", async () => {
  const ctx = world({ cardKeys: ["card_id", "x"], failNext: new Error("boom") });
  await assert.rejects(perform(ctx, () => markCard(ctx, { _row: 2, card_id: "x" }, "noted")), /boom/);
  assert.equal(ctx.pending, null);
});
