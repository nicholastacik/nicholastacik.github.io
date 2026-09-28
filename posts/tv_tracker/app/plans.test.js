import { test } from "node:test";
import assert from "node:assert/strict";
import { activeShows, planCardStatus, planTrack, planUntrack, toCell } from "./state.js";

const IDS = { Tracked: 10, Cards: 20, Schedule: 30, Meta: 40 };
const str = (v) => ({ userEnteredValue: { stringValue: v } });

test("toCell keeps types", () => {
  assert.deepEqual(toCell(true), { userEnteredValue: { boolValue: true } });
  assert.deepEqual(toCell(1434), { userEnteredValue: { numberValue: 1434 } });
  assert.deepEqual(toCell("2026-09-28"), str("2026-09-28"));
  assert.deepEqual(toCell(undefined), str(""));
});

test("planCardStatus writes status and updated_at in one range", () => {
  assert.deepEqual(planCardStatus({ _row: 5 }, "noted", "T", IDS), [
    {
      updateCells: {
        range: { sheetId: 20, startRowIndex: 4, endRowIndex: 5, startColumnIndex: 12, endColumnIndex: 14 },
        rows: [{ values: [str("noted"), str("T")] }],
        fields: "userEnteredValue",
      },
    },
  ]);
});

const SHOW = { tmdb_id: 247767, name: "The Studio", first_air_year: 2025, poster_url: "https://p" };
const base = { show: SHOW, source: "suggestion", today: "2026-09-28", nowIso: "T", sheetIds: IDS };

test("planTrack appends a new show and marks the suggestion card", () => {
  const requests = planTrack({ ...base, tracked: [], card: { _row: 7 } });
  assert.equal(requests.length, 2);
  assert.deepEqual(requests[0].updateCells.range, { sheetId: 20, startRowIndex: 6, endRowIndex: 7, startColumnIndex: 12, endColumnIndex: 14 });
  assert.deepEqual(requests[0].updateCells.rows[0].values[0], str("tracked"));
  const append = requests[1].appendCells;
  assert.equal(append.sheetId, 10);
  assert.equal(append.fields, "userEnteredValue");
  assert.deepEqual(append.rows[0].values, [
    { userEnteredValue: { numberValue: 247767 } },
    str(""),
    str("The Studio"),
    { userEnteredValue: { numberValue: 2025 } },
    str("https://p"),
    str("2026-09-28"),
    str("suggestion"),
    { userEnteredValue: { boolValue: true } },
    str("T"),
  ]);
});

test("planTrack reactivates inactive rows and resets added_at, without appending", () => {
  const tracked = [{ _row: 3, tmdb_id: 247767, active: false }, { _row: 9, tmdb_id: 247767, active: "FALSE" }];
  const requests = planTrack({ ...base, tracked, card: null });
  assert.ok(requests.every((r) => r.updateCells));
  const cols = requests.map((r) => [r.updateCells.range.startRowIndex, r.updateCells.range.startColumnIndex]);
  assert.deepEqual(cols, [[2, 5], [2, 7], [8, 5], [8, 7]]);
  assert.deepEqual(requests[1].updateCells.rows[0].values, [{ userEnteredValue: { boolValue: true } }, str("T")]);
});

test("planTrack on an already active show only touches active", () => {
  const requests = planTrack({ ...base, tracked: [{ _row: 3, tmdb_id: 247767, active: true }], card: null });
  assert.deepEqual(requests.map((r) => r.updateCells.range.startColumnIndex), [7]);
});

test("two devices tracking from the same stale read both append, and readers collapse them", () => {
  const first = planTrack({ ...base, tracked: [], card: null });
  const second = planTrack({ ...base, tracked: [], card: null });
  assert.ok(first[0].appendCells && second[0].appendCells);
  const rows = [
    { _row: 2, tmdb_id: 247767, name: "The Studio", active: true },
    { _row: 3, tmdb_id: 247767, name: "The Studio", active: true },
  ];
  assert.deepEqual(activeShows(rows).map((s) => s.tmdb_id), [247767]);
});

test("planUntrack deactivates every matching row", () => {
  const tracked = [{ _row: 2, tmdb_id: 1, active: true }, { _row: 4, tmdb_id: 2, active: true }, { _row: 6, tmdb_id: 1, active: true }];
  const requests = planUntrack({ tracked, tmdbId: 1, nowIso: "T", sheetIds: IDS });
  assert.deepEqual(requests.map((r) => r.updateCells.range.startRowIndex), [1, 5]);
  assert.deepEqual(requests[0].updateCells.rows[0].values, [{ userEnteredValue: { boolValue: false } }, str("T")]);
});
