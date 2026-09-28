import { test } from "node:test";
import assert from "node:assert/strict";
import { HEADERS } from "./headers.js";
import { activeIds, activeShows, domain, rowsFromValues, safeUrl, truthy, visibleCards } from "./state.js";

test("truthy accepts booleans and any-case TRUE only", () => {
  assert.ok(truthy(true) && truthy("TRUE") && truthy("True") && truthy(" true "));
  assert.ok(!truthy(false) && !truthy("") && !truthy("VRAI") && !truthy(undefined) && !truthy(0));
});

test("rowsFromValues maps headers, pads cells and skips blank rows", () => {
  const values = [
    HEADERS.Tracked,
    [1434, 84, "Family Guy", 1999, "p", "2026-09-28", "import", true, "t"],
    [],
    ["", "", ""],
    [2, "", "Two"],
  ];
  const rows = rowsFromValues("Tracked", values);
  assert.deepEqual(rows.map((r) => [r._row, r.tmdb_id, r.name, r.active]), [
    [2, 1434, "Family Guy", true],
    [5, 2, "Two", ""],
  ]);
  assert.equal(rows[1].poster_url, "");
  assert.deepEqual(rowsFromValues("Tracked", undefined), []);
});

const tracked = (tmdb_id, active, extra = {}) => ({ tmdb_id, name: `Show ${tmdb_id}`, poster_url: "", first_air_year: 2020, active, ...extra });

test("activeIds and activeShows collapse duplicates and skip inactive or blank rows", () => {
  const rows = [tracked(2, true, { name: "Beta" }), tracked(1, "TRUE", { name: "Alpha" }), tracked(2, true, { name: "Beta" }), tracked(3, false), tracked("", true)];
  assert.deepEqual([...activeIds(rows)].sort(), [1, 2]);
  assert.deepEqual(activeShows(rows).map((s) => [s.tmdb_id, s.name]), [[1, "Alpha"], [2, "Beta"]]);
});

const card = (card_id, extra = {}) => ({
  card_id, type: "episode", tmdb_id: 1, status: "new", current: true, date: "2026-09-28",
  created_at: "2026-09-28T06:00:00-04:00", ...extra,
});

test("visibleCards filters by status, current and active show, newest first", () => {
  const rows = [tracked(1, true), tracked(2, false)];
  const cards = [
    card("a"),
    card("b", { type: "season", current: false }),
    card("c", { type: "news", tmdb_id: 2 }),
    card("d", { type: "suggestion", tmdb_id: 99, created_at: "2026-09-27T06:00:00-04:00" }),
    card("e", { status: "noted" }),
    card("f", { type: "news", created_at: "2026-09-28T07:00:00-04:00" }),
    card("g", { current: "TRUE", date: "2026-09-27" }),
  ];
  assert.deepEqual(visibleCards(cards, rows).map((c) => c.card_id), ["f", "a", "g", "d"]);
});

test("safeUrl allows only http(s); domain strips www", () => {
  assert.equal(safeUrl("https://deadline.com/x"), "https://deadline.com/x");
  assert.equal(safeUrl("http://a.b"), "http://a.b");
  for (const bad of ["javascript:alert(1)", "data:text/html,x", "", undefined, "//evil.com"]) assert.equal(safeUrl(bad), null);
  assert.equal(domain("https://www.deadline.com/2026/x"), "deadline.com");
  assert.equal(domain("not a url"), "");
});
