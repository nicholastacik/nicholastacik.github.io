import { test } from "node:test";
import assert from "node:assert/strict";
import { findPendingSuggestion, resolveSuggestion } from "./state.js";

const r = (tmdb_id, name, first_air_year, extra = {}) => ({ tmdb_id, name, first_air_year, poster_url: `p${tmdb_id}`, country: "US", ...extra });

test("resolveSuggestion picks the title match for the year, not the first result", () => {
  const results = [r(1, "Shōgun", 1980), r(2, "Shōgun", 2024)];
  assert.deepEqual(resolveSuggestion(results, "Shogun", 2024, null), { status: "match", show: results[1] });
});

test("resolveSuggestion allows one year off but prefers an exact year", () => {
  assert.equal(resolveSuggestion([r(2, "Shōgun", 2024)], "Shōgun", 2023, null).show.tmdb_id, 2);
  assert.equal(resolveSuggestion([r(9, "Shōgun", 2025), r(2, "Shōgun", 2024)], "Shōgun", 2024, null).show.tmdb_id, 2);
});

test("resolveSuggestion uses the card's id when it is among the matches", () => {
  const results = [r(5, "Top Chef", 2013, { country: "US" }), r(6, "Top Chef", 2013, { country: "PL" })];
  assert.equal(resolveSuggestion(results, "Top Chef", 2013, 6).show.tmdb_id, 6);
});

test("resolveSuggestion reports ambiguity instead of guessing", () => {
  const results = [r(5, "Top Chef", 2013), r(6, "Top Chef", 2013), r(7, "Top Chef", 2006)];
  const outcome = resolveSuggestion(results, "Top Chef", 2013, null);
  assert.equal(outcome.status, "ambiguous");
  assert.deepEqual(outcome.candidates.map((s) => s.tmdb_id), [5, 6]);
  assert.equal(resolveSuggestion([r(5, "Top Chef", 2013), r(7, "Top Chef", 2006)], "Top Chef", null, null).status, "ambiguous");
});

test("resolveSuggestion matches original names, quotes and diacritics, and reports none", () => {
  assert.equal(resolveSuggestion([r(3, "Money Heist", 2017, { original_name: "La casa de papel" })], "La Casa de Papel", 2017, null).show.tmdb_id, 3);
  assert.equal(resolveSuggestion([r(4, "Grey's Anatomy", 2005)], "Grey’s  Anatomy", 2005, null).show.tmdb_id, 4);
  assert.deepEqual(resolveSuggestion([r(1, "Shōgun", 1980)], "Shōgun", 2024, null), { status: "none" });
  assert.deepEqual(resolveSuggestion([], "Anything", 2024, null), { status: "none" });
});

const card = (extra) => ({ card_id: "sugg:x", type: "suggestion", status: "new", tmdb_id: "", show_name: "The Studio", date: "2025", ...extra });

test("findPendingSuggestion matches by id or by title and year", () => {
  const show = { tmdb_id: 247767, name: "The Studio", first_air_year: 2025 };
  assert.equal(findPendingSuggestion([card({ tmdb_id: 247767, show_name: "Something" })], show).show_name, "Something");
  assert.equal(findPendingSuggestion([card({})], show).card_id, "sugg:x");
  assert.equal(findPendingSuggestion([card({ date: "2019" })], show), null);
  assert.equal(findPendingSuggestion([card({ status: "ignored" })], show), null);
  assert.equal(findPendingSuggestion([card({ type: "news" })], show), null);
});
