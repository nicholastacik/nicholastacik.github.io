import { test } from "node:test";
import assert from "node:assert/strict";
import { HEADERS } from "./headers.js";
import { AuthError, ForbiddenError, SheetsClient, SheetsError, tabRange } from "./sheets.js";
import { mapResults, resultLabel, searchShows, searchUrl } from "./tmdb.js";

function fakeFetch(responses) {
  const calls = [];
  const fn = async (url, init = {}) => {
    calls.push({ url: String(url), init });
    const { status = 200, body = {} } = responses.shift();
    return { status, ok: status >= 200 && status < 300, json: async () => body, text: async () => JSON.stringify(body) };
  };
  return { fn, calls };
}

const client = (responses) => {
  const fake = fakeFetch(responses);
  return { sheets: new SheetsClient({ sheetId: "SID", getToken: () => "tok", fetchFn: fake.fn }), calls: fake.calls };
};

test("tabRange covers each tab's columns", () => {
  assert.equal(tabRange("Cards"), "Cards!A:N");
  assert.equal(tabRange("Tracked"), "Tracked!A:J");
  assert.equal(tabRange("Meta"), "Meta!A:B");
});

test("get sends unformatted batchGet with bearer token", async () => {
  const { sheets, calls } = client([{ body: { valueRanges: [{ values: [["a"]] }, {}] } }]);
  assert.deepEqual(await sheets.get(["Cards!A:A", "Tracked!A:J"]), [[["a"]], []]);
  const url = new URL(calls[0].url);
  assert.equal(url.origin + url.pathname, "https://sheets.googleapis.com/v4/spreadsheets/SID/values:batchGet");
  assert.equal(url.searchParams.get("valueRenderOption"), "UNFORMATTED_VALUE");
  assert.deepEqual(url.searchParams.getAll("ranges"), ["Cards!A:A", "Tracked!A:J"]);
  assert.equal(calls[0].init.headers.Authorization, "Bearer tok");
});

test("readAll parses every tab", async () => {
  const valueRanges = Object.keys(HEADERS).map((tab) => ({ values: [HEADERS[tab], tab === "Meta" ? ["last_run_ok", true] : []] }));
  const { sheets } = client([{ body: { valueRanges } }]);
  const data = await sheets.readAll();
  assert.deepEqual(Object.keys(data), ["Tracked", "Cards", "Schedule", "Meta"]);
  assert.deepEqual(data.Meta, [{ _row: 2, key: "last_run_ok", value: true }]);
  assert.deepEqual(data.Cards, []);
});

test("errors map to 401 AuthError, 403 ForbiddenError, other SheetsError", async () => {
  await assert.rejects(client([{ status: 401 }]).sheets.get(["Meta!A:B"]), AuthError);
  await assert.rejects(client([{ status: 403 }]).sheets.get(["Meta!A:B"]), ForbiddenError);
  await assert.rejects(client([{ status: 500 }]).sheets.get(["Meta!A:B"]), SheetsError);
});

test("sheetIds is fetched once and cached", async () => {
  const body = { sheets: [{ properties: { sheetId: 0, title: "Tracked" } }, { properties: { sheetId: 7, title: "Cards" } }] };
  const { sheets, calls } = client([{ body }]);
  assert.deepEqual(await sheets.sheetIds(), { Tracked: 0, Cards: 7 });
  assert.deepEqual(await sheets.sheetIds(), { Tracked: 0, Cards: 7 });
  assert.equal(calls.length, 1);
  assert.match(calls[0].url, /\/SID\?fields=sheets\.properties/);
});

test("batchUpdate posts requests", async () => {
  const { sheets, calls } = client([{ body: {} }]);
  await sheets.batchUpdate([{ x: 1 }]);
  assert.equal(calls[0].url, "https://sheets.googleapis.com/v4/spreadsheets/SID:batchUpdate");
  assert.equal(calls[0].init.method, "POST");
  assert.deepEqual(JSON.parse(calls[0].init.body), { requests: [{ x: 1 }] });
});

test("TMDB search url, mapping and limit", async () => {
  const url = new URL(searchUrl("Slow Horses", "KEY"));
  assert.equal(url.pathname, "/3/search/tv");
  assert.equal(url.searchParams.get("query"), "Slow Horses");
  assert.equal(url.searchParams.get("api_key"), "KEY");
  assert.deepEqual(mapResults([{ id: 1, name: "A", first_air_date: "2022-04-01", poster_path: "/p.jpg", origin_country: ["GB"] }, { id: 2, name: "B", first_air_date: "", poster_path: null }]), [
    { tmdb_id: 1, name: "A", original_name: "", first_air_year: 2022, poster_url: "https://image.tmdb.org/t/p/w342/p.jpg", country: "GB" },
    { tmdb_id: 2, name: "B", original_name: "", first_air_year: "", poster_url: "", country: "" },
  ]);
  const many = Array.from({ length: 15 }, (_, i) => ({ id: i, name: `S${i}`, first_air_date: "2020-01-01", poster_path: null }));
  const fake = fakeFetch([{ body: { results: many } }]);
  assert.equal((await searchShows("s", "KEY", fake.fn)).length, 10);
  await assert.rejects(searchShows("s", "KEY", fakeFetch([{ status: 401 }]).fn));
});

test("resultLabel shows year and country when known", () => {
  assert.equal(resultLabel({ name: "Top Chef", first_air_year: 2006, country: "US" }), "Top Chef (2006, US)");
  assert.equal(resultLabel({ name: "Top Chef", first_air_year: 2013, country: "PL" }), "Top Chef (2013, PL)");
  assert.equal(resultLabel({ name: "New Show", first_air_year: "", country: "CA" }), "New Show (CA)");
  assert.equal(resultLabel({ name: "Mystery", first_air_year: "", country: "" }), "Mystery");
});
