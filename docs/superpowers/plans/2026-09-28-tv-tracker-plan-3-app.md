# TV Tracker Plan 3: The App

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A static, mobile-first web app at `posts/tv_tracker/app/`. It signs in with Google, reads the Sheet, shows the Feed / This Week / Shows views, and writes Noted, Track, Ignore and Untrack straight back to the Sheet.

**Architecture:** Plain ES modules, with no framework and no build step. Pure logic lives in `state.js` (row parsing, visibility, schedule, freshness, write plans as Sheets `batchUpdate` requests) and `actions.js` (fresh-read, key-check and write sequences, and the auth-expiry retry). I/O is split across `sheets.js` (Sheets REST via `fetch`), `auth.js` (Google Identity Services token model) and `tmdb.js` (search). `app.js` is the only DOM code. The column layout lives in `headers.js`, and a Python test checks it against the job's `HEADERS`.

**Tech Stack:** Browser ES modules, Google Identity Services, Sheets API v4 REST, TMDB v3, `node --test`.

**Spec:** `docs/superpowers/specs/2026-09-27-tv-tracker-design.md` (rev 4), App section and Security requirements. Build order step 3. Plan 2's ledger carried two app requirements (below).

## Global Constraints

- Worktree `/Users/nick/Work/nicholastacik.github.io-tv-tracker`, branch `tv-tracker`.
- JS tests: `node --test posts/tv_tracker/app/*.test.js` (Node 24). Python contract test runs with the existing `uv run --group tv-tracker python -m pytest tv-tracker/tests -q`.
- **Reads use `valueRenderOption=UNFORMATTED_VALUE`**, so booleans arrive as `true`/`false` and numbers as numbers. `truthy()` also accepts `"TRUE"`/`"True"` strings (from hand edits). *(Carried from Plan 2.)*
- **Date-only airstamps are local dates.** Never pass `"YYYY-MM-DD"` to `new Date()` for display. Compare day strings, and build day labels by UTC arithmetic on the string. *(Carried from Plan 2.)*
- Column ownership: the app writes only `Cards.status` + `Cards.updated_at`, `Tracked.active` + `Tracked.updated_at` (+ `Tracked.added_at` when re-tracking an inactive show), and appends to `Tracked`. It never deletes or reorders rows.
- Every write is **one `spreadsheets.batchUpdate`**, which is atomic across tabs. Before it, the app re-reads the target tabs in one `values.batchGet`. A card write aborts (StaleError, then reload) if the key at the cached row no longer matches.
- Track and Untrack build target rows from the **fresh** Tracked read (catching duplicates another device appended). Duplicates are tolerated; readers collapse by `tmdb_id`.
- Visibility: `status == "new"` AND `current` truthy AND (type is `suggestion` OR the show is active).
- Auth: GIS token model, scope `https://www.googleapis.com/auth/spreadsheets`. Token requests only from a click. A 401 keeps the pending action, shows "Reconnect Google", and retries it after reconnecting. A 403 on read shows "This app is private". The token is kept in `localStorage` until expiry (survives reloads within the hour).
- **Security:** no third-party scripts except `https://accounts.google.com/gsi/client`. All Sheet/LLM text is inserted with `textContent` (never `innerHTML`). Only `http(s)` URLs become links or images. `config.js` is public: Sheet ID, OAuth client ID and a TMDB **v3 API key**. The job's read-access token stays secret.
- Times are shown in Eastern (America/Toronto).
- The Tracked `source` column may contain `import`, `search` or `suggestion`. The app treats them all the same.

## Review Focus

1. **LLM or news text containing HTML/script** (`<img src=x onerror=…>`) or a `javascript:` link: rendered as inert text, no link. → `safeUrl` test in Task 1; `el()` uses `append(string)` (text nodes).
2. **A streaming date-only airing** (`2026-09-30`) viewed in the evening in Toronto: listed on Wednesday, not Tuesday. → test in Task 2.
3. **Hand-edited Sheet values** (`"TRUE"` strings, a blank `tmdb_id`): treated as the job treats them. → tests in Task 1.
4. **Token expiry mid-write:** the action is kept, reconnect is offered, and the action is retried once. → test in Task 6.
5. **Another device tracked the same show since page load:** Untrack deactivates both rows. → test in Task 6.

---

## File Structure

```
posts/tv_tracker/app/
  index.html      # shell: views, tab bar, gate, toast; loads GIS + app.js
  styles.css      # mobile-first, light/dark
  config.js       # CONFIG = {SHEET_ID, CLIENT_ID, TMDB_API_KEY}  (public)
  headers.js      # HEADERS (JSON-compatible), shared contract with tv-tracker/job/sheet.py
  state.js        # pure: parsing, visibility, schedule, freshness, write plans, safeUrl
  sheets.js       # SheetsClient, AuthError, ForbiddenError, SheetsError, tabRange
  auth.js         # Auth (GIS token client + localStorage)
  tmdb.js         # searchUrl, mapResults, searchShows
  actions.js      # markCard, trackShow, untrackShow, perform, resumePending, StaleError
  app.js          # DOM rendering and event wiring
  *.test.js       # node --test
tv-tracker/tests/test_contract.py   # headers.js == job HEADERS
_quarto.yml                        # + resources: posts/tv_tracker/app/**
.github/workflows/test.yml         # + node --test posts/tv_tracker/app/
```

---

### Task 1: Shared headers and core state

**Files:**
- Create: `posts/tv_tracker/app/headers.js`, `posts/tv_tracker/app/state.js`
- Create: `tv-tracker/tests/test_contract.py`
- Test: `posts/tv_tracker/app/state.test.js`

**Interfaces:**
- Produces: `HEADERS`; `TZ`; `truthy(value) -> boolean`; `rowsFromValues(tab, values) -> Array<object>` (fields plus `_row`; blank rows skipped; missing cells `""`); `activeIds(trackedRows) -> Set<number>`; `activeShows(trackedRows) -> Array<{tmdb_id, name, poster_url, first_air_year}>` (collapsed, sorted by name); `visibleCards(cards, trackedRows) -> Array` (newest `created_at` first, then `date` desc); `safeUrl(url) -> string | null`; `domain(url) -> string`.

- [ ] **Step 1: Write the failing tests**

`tv-tracker/tests/test_contract.py`:
```python
import json
from pathlib import Path

from job.sheet import HEADERS

APP_HEADERS = Path(__file__).resolve().parents[2] / "posts/tv_tracker/app/headers.js"


def test_app_headers_match_job_headers():
    text = APP_HEADERS.read_text()
    literal = text.split("=", 1)[1].strip().rstrip(";")
    assert json.loads(literal) == HEADERS
```

`posts/tv_tracker/app/state.test.js`:
```js
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
```

- [ ] **Step 2: Run to verify failure**

Run: `node --test posts/tv_tracker/app/*.test.js ; uv run --group tv-tracker python -m pytest tv-tracker/tests/test_contract.py -q`
Expected: FAIL. Node reports `Cannot find module …/headers.js`; pytest reports `FileNotFoundError` for `headers.js`.

- [ ] **Step 3: Implement**

`posts/tv_tracker/app/headers.js` (keys quoted so the literal is valid JSON):
```js
export const HEADERS = {
  "Tracked": ["tmdb_id", "tvmaze_id", "name", "first_air_year", "poster_url", "added_at", "source", "active", "updated_at"],
  "Cards": ["card_id", "type", "tmdb_id", "show_name", "headline", "body", "date", "link", "image_url", "source_url", "created_at", "current", "status", "updated_at"],
  "Schedule": ["tmdb_id", "airstamp", "show_name", "episode_label", "network", "image_url", "refreshed_at"],
  "Meta": ["key", "value"]
};
```

`posts/tv_tracker/app/state.js`:
```js
import { HEADERS } from "./headers.js";

export const TZ = "America/Toronto";

export function truthy(value) {
  return String(value).trim().toUpperCase() === "TRUE";
}

export function rowsFromValues(tab, values = []) {
  const header = HEADERS[tab];
  const rows = [];
  (values ?? []).slice(1).forEach((cells, index) => {
    if (!cells.some((cell) => cell !== "" && cell !== null && cell !== undefined)) return;
    const row = { _row: index + 2 };
    header.forEach((column, j) => {
      row[column] = cells[j] ?? "";
    });
    rows.push(row);
  });
  return rows;
}

function isActive(row) {
  return row.tmdb_id !== "" && Number.isFinite(Number(row.tmdb_id)) && truthy(row.active);
}

export function activeIds(trackedRows) {
  return new Set(trackedRows.filter(isActive).map((row) => Number(row.tmdb_id)));
}

export function activeShows(trackedRows) {
  const shows = new Map();
  for (const row of trackedRows.filter(isActive)) {
    const id = Number(row.tmdb_id);
    if (!shows.has(id)) {
      shows.set(id, { tmdb_id: id, name: String(row.name), poster_url: row.poster_url, first_air_year: row.first_air_year });
    }
  }
  return [...shows.values()].sort((a, b) => a.name.localeCompare(b.name));
}

export function visibleCards(cards, trackedRows) {
  const active = activeIds(trackedRows);
  return cards
    .filter(
      (card) =>
        card.status === "new" && truthy(card.current) && (card.type === "suggestion" || active.has(Number(card.tmdb_id))),
    )
    .sort(
      (a, b) =>
        Date.parse(b.created_at) - Date.parse(a.created_at) || String(b.date).localeCompare(String(a.date)),
    );
}

export function safeUrl(url) {
  return /^https?:\/\/[^/]/i.test(String(url ?? "")) ? String(url) : null;
}

export function domain(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}
```

- [ ] **Step 4: Run to verify pass**

Run: `node --test posts/tv_tracker/app/*.test.js && uv run --group tv-tracker python -m pytest tv-tracker/tests -q`
Expected: 5 JS tests pass; the Python suite passes including `test_app_headers_match_job_headers`

- [ ] **Step 5: Commit**

```bash
git add posts/tv_tracker/app/headers.js posts/tv_tracker/app/state.js posts/tv_tracker/app/state.test.js tv-tracker/tests/test_contract.py
git commit -m "feat(tv-tracker): app core state with a headers contract shared with the job

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Dates, schedule and freshness

**Files:**
- Modify: `posts/tv_tracker/app/state.js` (append)
- Test: `posts/tv_tracker/app/schedule.test.js`

**Interfaces:**
- Produces: `torontoDate(date = new Date()) -> "YYYY-MM-DD"`; `addDays(day, n)`; `weekStart(day) -> "YYYY-MM-DD"` (Monday); `inWeek(stamp, today) -> boolean`; `dayLabel(day) -> "Mon, Sep 28"`; `timeLabel(airstamp) -> "9:00 PM" | ""`; `scheduleDays(rows, trackedRows, today) -> Array<{day, label, isToday, items}>` (7 days, items sorted, `item.time` added, inactive shows excluded); `scheduleHeader(metaRows, today, nowMs) -> {kind: "stale-week" | "failed" | "ok", text}`.

- [ ] **Step 1: Write the failing tests**

`posts/tv_tracker/app/schedule.test.js`:
```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { dayLabel, inWeek, scheduleDays, scheduleHeader, timeLabel, torontoDate, weekStart } from "./state.js";

test("torontoDate uses Eastern time", () => {
  assert.equal(torontoDate(new Date("2026-09-29T01:30:00Z")), "2026-09-28");
  assert.equal(torontoDate(new Date("2026-12-08T04:59:00Z")), "2026-12-07");
});

test("weekStart is Monday; inWeek covers Mon..Sun", () => {
  assert.equal(weekStart("2026-09-30"), "2026-09-28");
  assert.equal(weekStart("2026-09-28"), "2026-09-28");
  assert.equal(weekStart("2026-10-04"), "2026-09-28");
  assert.ok(inWeek("2026-09-28", "2026-09-30") && inWeek("2026-10-04T21:00-04:00", "2026-09-30"));
  assert.ok(!inWeek("2026-09-27", "2026-09-30") && !inWeek("2026-10-05", "2026-09-30"));
});

test("labels never shift date-only values", () => {
  assert.equal(dayLabel("2026-09-28"), "Mon, Sep 28");
  assert.equal(dayLabel("2026-10-04"), "Sun, Oct 4");
  assert.equal(timeLabel("2026-09-28T21:00-04:00"), "9:00 PM");
  assert.equal(timeLabel("2026-09-28T00:30-04:00"), "12:30 AM");
  assert.equal(timeLabel("2026-09-28T12:05-04:00"), "12:05 PM");
  assert.equal(timeLabel("2026-09-30"), "");
});

test("scheduleDays groups by local day and drops inactive shows", () => {
  const rows = [
    { tmdb_id: 3, airstamp: "2026-09-30", show_name: "Streamer" },
    { tmdb_id: 1, airstamp: "2026-09-28T21:00-04:00", show_name: "Late" },
    { tmdb_id: 1, airstamp: "2026-09-28T20:00-04:00", show_name: "Early" },
    { tmdb_id: 2, airstamp: "2026-09-29T20:00-04:00", show_name: "Untracked" },
  ];
  const trackedRows = [{ tmdb_id: 1, active: true }, { tmdb_id: 3, active: true }, { tmdb_id: 2, active: false }];
  const days = scheduleDays(rows, trackedRows, "2026-09-30");
  assert.equal(days.length, 7);
  assert.deepEqual(days.map((d) => d.day), ["2026-09-28", "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02", "2026-10-03", "2026-10-04"]);
  assert.deepEqual(days[0].items.map((i) => [i.show_name, i.time]), [["Early", "8:00 PM"], ["Late", "9:00 PM"]]);
  assert.deepEqual(days[1].items, []);
  assert.deepEqual(days[2].items.map((i) => [i.show_name, i.time]), [["Streamer", ""]]);
  assert.ok(days[2].isToday && !days[0].isToday);
});

const meta = (values) => Object.entries(values).map(([key, value]) => ({ key, value }));
const NOW = Date.parse("2026-09-28T09:00:00-04:00");

test("scheduleHeader states", () => {
  const ok = { last_run_at: "2026-09-28T06:02:00-04:00", last_run_ok: true, schedule_week: "2026-09-28", failed_shows: "", failed_steps: "" };
  assert.deepEqual(scheduleHeader(meta(ok), "2026-09-28", NOW), { kind: "ok", text: "Updated 6:02 AM" });
  assert.equal(scheduleHeader(meta({ ...ok, schedule_week: "2026-09-21" }), "2026-09-28", NOW).kind, "stale-week");
  assert.equal(scheduleHeader([], "2026-09-28", NOW).text, "This week hasn't refreshed yet");
  assert.deepEqual(scheduleHeader(meta({ ...ok, last_run_ok: false, failed_shows: "Slow Horses" }), "2026-09-28", NOW), {
    kind: "failed",
    text: "Couldn't refresh: Slow Horses — showing last known times",
  });
  const old = { ...ok, last_run_at: "2026-09-26T20:00:00-04:00" };
  assert.equal(scheduleHeader(meta(old), "2026-09-28", NOW).text, "Couldn't refresh — showing last known times");
});
```

- [ ] **Step 2: Run to verify failure**

Run: `node --test posts/tv_tracker/app/*.test.js`
Expected: FAIL, `SyntaxError: The requested module './state.js' does not provide an export named 'dayLabel'`

- [ ] **Step 3: Implement (append to `state.js`)**

```js
const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function torontoDate(date = new Date()) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
}

function utc(day) {
  return new Date(`${day}T00:00:00Z`);
}

export function addDays(day, n) {
  const date = utc(day);
  date.setUTCDate(date.getUTCDate() + n);
  return date.toISOString().slice(0, 10);
}

export function weekStart(day) {
  return addDays(day, -((utc(day).getUTCDay() + 6) % 7));
}

export function inWeek(stamp, today) {
  const start = weekStart(today);
  const day = String(stamp).slice(0, 10);
  return day >= start && day < addDays(start, 7);
}

export function dayLabel(day) {
  const date = utc(day);
  return `${WEEKDAYS[date.getUTCDay()]}, ${MONTHS[date.getUTCMonth()]} ${date.getUTCDate()}`;
}

export function timeLabel(airstamp) {
  const match = /T(\d{2}):(\d{2})/.exec(String(airstamp));
  if (!match) return "";
  const hour = Number(match[1]);
  return `${hour % 12 || 12}:${match[2]} ${hour >= 12 ? "PM" : "AM"}`;
}

export function scheduleDays(rows, trackedRows, today) {
  const active = activeIds(trackedRows);
  const start = weekStart(today);
  return Array.from({ length: 7 }, (_, i) => addDays(start, i)).map((day) => ({
    day,
    label: dayLabel(day),
    isToday: day === today,
    items: rows
      .filter((row) => String(row.airstamp).slice(0, 10) === day && active.has(Number(row.tmdb_id)))
      .sort((a, b) => String(a.airstamp).localeCompare(String(b.airstamp)))
      .map((row) => ({ ...row, time: timeLabel(row.airstamp) })),
  }));
}

function clock(ms) {
  return new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" })
    .format(new Date(ms))
    .replace(/ /g, " ");
}

export function scheduleHeader(metaRows, today, nowMs) {
  const meta = Object.fromEntries(metaRows.map((row) => [row.key, row.value]));
  if (meta.schedule_week !== weekStart(today)) return { kind: "stale-week", text: "This week hasn't refreshed yet" };
  const last = Date.parse(meta.last_run_at);
  if (!truthy(meta.last_run_ok) || !(nowMs - last <= 36 * 3600 * 1000)) {
    const names = meta.failed_shows ? `: ${meta.failed_shows}` : "";
    return { kind: "failed", text: `Couldn't refresh${names} — showing last known times` };
  }
  return { kind: "ok", text: `Updated ${clock(last)}` };
}
```

- [ ] **Step 4: Run to verify pass**

Run: `node --test posts/tv_tracker/app/*.test.js`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add posts/tv_tracker/app/state.js posts/tv_tracker/app/schedule.test.js
git commit -m "feat(tv-tracker): app schedule grouping and freshness header in Eastern time

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Write plans (Sheets batchUpdate requests)

**Files:**
- Modify: `posts/tv_tracker/app/state.js` (append)
- Test: `posts/tv_tracker/app/plans.test.js`

**Interfaces:**
- Produces: `toCell(value)`; `planCardStatus(card, status, nowIso, sheetIds) -> requests`; `planTrack({tracked, show, source, card, today, nowIso, sheetIds}) -> requests`; `planUntrack({tracked, tmdbId, nowIso, sheetIds}) -> requests`. `show` is `{tmdb_id, name, first_air_year, poster_url}`; `sheetIds` maps tab title to numeric sheetId.

- [ ] **Step 1: Write the failing tests**

`posts/tv_tracker/app/plans.test.js`:
```js
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
```

- [ ] **Step 2: Run to verify failure**

Run: `node --test posts/tv_tracker/app/*.test.js`
Expected: FAIL, `does not provide an export named 'planCardStatus'`

- [ ] **Step 3: Implement (append to `state.js`)**

```js
export function toCell(value) {
  if (typeof value === "boolean") return { userEnteredValue: { boolValue: value } };
  if (typeof value === "number") return { userEnteredValue: { numberValue: value } };
  return { userEnteredValue: { stringValue: String(value ?? "") } };
}

function updateRow(sheetIds, tab, row, firstColumn, values) {
  const column = HEADERS[tab].indexOf(firstColumn);
  return {
    updateCells: {
      range: {
        sheetId: sheetIds[tab],
        startRowIndex: row - 1,
        endRowIndex: row,
        startColumnIndex: column,
        endColumnIndex: column + values.length,
      },
      rows: [{ values: values.map(toCell) }],
      fields: "userEnteredValue",
    },
  };
}

export function planCardStatus(card, status, nowIso, sheetIds) {
  return [updateRow(sheetIds, "Cards", card._row, "status", [status, nowIso])];
}

export function planTrack({ tracked, show, source, card, today, nowIso, sheetIds }) {
  const requests = card ? planCardStatus(card, "tracked", nowIso, sheetIds) : [];
  const rows = tracked.filter((row) => Number(row.tmdb_id) === show.tmdb_id);
  if (rows.length === 0) {
    const row = {
      tmdb_id: show.tmdb_id,
      tvmaze_id: "",
      name: show.name,
      first_air_year: show.first_air_year ?? "",
      poster_url: show.poster_url ?? "",
      added_at: today,
      source,
      active: true,
      updated_at: nowIso,
    };
    requests.push({
      appendCells: {
        sheetId: sheetIds.Tracked,
        rows: [{ values: HEADERS.Tracked.map((column) => toCell(row[column])) }],
        fields: "userEnteredValue",
      },
    });
    return requests;
  }
  const wasActive = rows.some((row) => truthy(row.active));
  for (const row of rows) {
    if (!wasActive) requests.push(updateRow(sheetIds, "Tracked", row._row, "added_at", [today]));
    requests.push(updateRow(sheetIds, "Tracked", row._row, "active", [true, nowIso]));
  }
  return requests;
}

export function planUntrack({ tracked, tmdbId, nowIso, sheetIds }) {
  return tracked
    .filter((row) => Number(row.tmdb_id) === tmdbId)
    .map((row) => updateRow(sheetIds, "Tracked", row._row, "active", [false, nowIso]));
}
```

- [ ] **Step 4: Run to verify pass**

Run: `node --test posts/tv_tracker/app/*.test.js`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add posts/tv_tracker/app/state.js posts/tv_tracker/app/plans.test.js
git commit -m "feat(tv-tracker): app write plans as atomic Sheets batchUpdate requests

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Sheets and TMDB clients

**Files:**
- Create: `posts/tv_tracker/app/sheets.js`, `posts/tv_tracker/app/tmdb.js`
- Test: `posts/tv_tracker/app/clients.test.js`

**Interfaces:**
- Consumes: `HEADERS`, `rowsFromValues`.
- Produces: `class AuthError`, `class ForbiddenError`, `class SheetsError(status, body)`; `tabRange(tab) -> "Cards!A:N"`; `class SheetsClient({sheetId, getToken, fetchFn})` with `get(ranges) -> Promise<Array<values>>`, `readAll() -> Promise<{Tracked, Cards, Schedule, Meta}>`, `sheetIds() -> Promise<{title: id}>` (cached), `batchUpdate(requests)`. `searchUrl(query, apiKey)`, `mapResults(results)`, `searchShows(query, apiKey, fetchFn) -> Promise<Array<show>>` (at most 10).

- [ ] **Step 1: Write the failing tests**

`posts/tv_tracker/app/clients.test.js`:
```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { HEADERS } from "./headers.js";
import { AuthError, ForbiddenError, SheetsClient, SheetsError, tabRange } from "./sheets.js";
import { mapResults, searchShows, searchUrl } from "./tmdb.js";

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
  assert.equal(tabRange("Tracked"), "Tracked!A:I");
  assert.equal(tabRange("Meta"), "Meta!A:B");
});

test("get sends unformatted batchGet with bearer token", async () => {
  const { sheets, calls } = client([{ body: { valueRanges: [{ values: [["a"]] }, {}] } }]);
  assert.deepEqual(await sheets.get(["Cards!A:A", "Tracked!A:I"]), [[["a"]], []]);
  const url = new URL(calls[0].url);
  assert.equal(url.origin + url.pathname, "https://sheets.googleapis.com/v4/spreadsheets/SID/values:batchGet");
  assert.equal(url.searchParams.get("valueRenderOption"), "UNFORMATTED_VALUE");
  assert.deepEqual(url.searchParams.getAll("ranges"), ["Cards!A:A", "Tracked!A:I"]);
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
  assert.deepEqual(mapResults([{ id: 1, name: "A", first_air_date: "2022-04-01", poster_path: "/p.jpg" }, { id: 2, name: "B", first_air_date: "", poster_path: null }]), [
    { tmdb_id: 1, name: "A", first_air_year: 2022, poster_url: "https://image.tmdb.org/t/p/w342/p.jpg" },
    { tmdb_id: 2, name: "B", first_air_year: "", poster_url: "" },
  ]);
  const many = Array.from({ length: 15 }, (_, i) => ({ id: i, name: `S${i}`, first_air_date: "2020-01-01", poster_path: null }));
  const fake = fakeFetch([{ body: { results: many } }]);
  assert.equal((await searchShows("s", "KEY", fake.fn)).length, 10);
  await assert.rejects(searchShows("s", "KEY", fakeFetch([{ status: 401 }]).fn));
});
```

- [ ] **Step 2: Run to verify failure**

Run: `node --test posts/tv_tracker/app/*.test.js`
Expected: FAIL, `Cannot find module …/sheets.js`

- [ ] **Step 3: Implement**

`posts/tv_tracker/app/sheets.js`:
```js
import { HEADERS } from "./headers.js";
import { rowsFromValues } from "./state.js";

const BASE = "https://sheets.googleapis.com/v4/spreadsheets";

export class AuthError extends Error {}
export class ForbiddenError extends Error {}
export class SheetsError extends Error {
  constructor(status, body) {
    super(`Sheets API ${status}`);
    this.status = status;
    this.body = body;
  }
}

export function tabRange(tab) {
  return `${tab}!A:${String.fromCharCode(64 + HEADERS[tab].length)}`;
}

export class SheetsClient {
  constructor({ sheetId, getToken, fetchFn = (...args) => fetch(...args) }) {
    this.sheetId = sheetId;
    this.getToken = getToken;
    this.fetchFn = fetchFn;
    this.ids = null;
  }

  async call(path, init = {}) {
    const response = await this.fetchFn(`${BASE}/${this.sheetId}${path}`, {
      ...init,
      headers: { Authorization: `Bearer ${this.getToken()}`, "Content-Type": "application/json" },
    });
    if (response.status === 401) throw new AuthError("Google session expired");
    if (response.status === 403) throw new ForbiddenError("No access to this Sheet");
    if (!response.ok) throw new SheetsError(response.status, await response.text());
    return response.json();
  }

  async get(ranges) {
    const params = new URLSearchParams({ valueRenderOption: "UNFORMATTED_VALUE" });
    for (const range of ranges) params.append("ranges", range);
    const data = await this.call(`/values:batchGet?${params}`);
    return data.valueRanges.map((valueRange) => valueRange.values ?? []);
  }

  async readAll() {
    const tabs = Object.keys(HEADERS);
    const values = await this.get(tabs.map(tabRange));
    return Object.fromEntries(tabs.map((tab, i) => [tab, rowsFromValues(tab, values[i])]));
  }

  async sheetIds() {
    if (!this.ids) {
      const data = await this.call("?fields=sheets.properties(sheetId,title)");
      this.ids = Object.fromEntries(data.sheets.map((sheet) => [sheet.properties.title, sheet.properties.sheetId]));
    }
    return this.ids;
  }

  async batchUpdate(requests) {
    return this.call(":batchUpdate", { method: "POST", body: JSON.stringify({ requests }) });
  }
}
```

`posts/tv_tracker/app/tmdb.js`:
```js
export function searchUrl(query, apiKey) {
  return `https://api.themoviedb.org/3/search/tv?${new URLSearchParams({ query, api_key: apiKey })}`;
}

export function mapResults(results) {
  return results.map((result) => ({
    tmdb_id: result.id,
    name: result.name,
    first_air_year: Number(String(result.first_air_date ?? "").slice(0, 4)) || "",
    poster_url: result.poster_path ? `https://image.tmdb.org/t/p/w342${result.poster_path}` : "",
  }));
}

export async function searchShows(query, apiKey, fetchFn = (...args) => fetch(...args)) {
  const response = await fetchFn(searchUrl(query, apiKey));
  if (!response.ok) throw new Error(`TMDB ${response.status}`);
  return mapResults((await response.json()).results).slice(0, 10);
}
```

- [ ] **Step 4: Run to verify pass**

Run: `node --test posts/tv_tracker/app/*.test.js`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add posts/tv_tracker/app/sheets.js posts/tv_tracker/app/tmdb.js posts/tv_tracker/app/clients.test.js
git commit -m "feat(tv-tracker): Sheets REST and TMDB search clients for the app

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Google sign-in

**Files:**
- Create: `posts/tv_tracker/app/auth.js`
- Test: `posts/tv_tracker/app/auth.test.js`

**Interfaces:**
- Produces: `class Auth({clientId, scope, storage, now})` with `token`, `valid() -> boolean` (true until 60 s before expiry), `expire()`, `connect() -> Promise` (must be called from a click; uses `globalThis.google.accounts.oauth2.initTokenClient`). Persists `{token, expiresAt}` under `tv-tracker-token`; tolerates `storage` being `null` or throwing.

- [ ] **Step 1: Write the failing tests**

`posts/tv_tracker/app/auth.test.js`:
```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { Auth } from "./auth.js";

function memoryStorage(initial = {}) {
  const map = new Map(Object.entries(initial));
  return { getItem: (k) => map.get(k) ?? null, setItem: (k, v) => map.set(k, v), removeItem: (k) => map.delete(k), map };
}

const opts = (storage, t = 1_000_000) => ({ clientId: "CID", scope: "S", storage, now: () => t });

function fakeGoogle(response) {
  const seen = {};
  globalThis.google = {
    accounts: {
      oauth2: {
        initTokenClient: (config) => {
          seen.config = config;
          return { requestAccessToken: (args) => { seen.args = args; config.callback(response); } };
        },
      },
    },
  };
  return seen;
}

test("restores an unexpired saved token and ignores an expired one", () => {
  const fresh = memoryStorage({ "tv-tracker-token": JSON.stringify({ token: "saved", expiresAt: 2_000_000 }) });
  assert.equal(new Auth(opts(fresh)).token, "saved");
  assert.ok(new Auth(opts(fresh)).valid());
  const stale = memoryStorage({ "tv-tracker-token": JSON.stringify({ token: "old", expiresAt: 500 }) });
  assert.equal(new Auth(opts(stale)).token, null);
});

test("valid is false within a minute of expiry", () => {
  const storage = memoryStorage({ "tv-tracker-token": JSON.stringify({ token: "t", expiresAt: 1_030_000 }) });
  assert.ok(!new Auth(opts(storage)).valid());
});

test("connect stores the token from Google", async () => {
  const seen = fakeGoogle({ access_token: "new", expires_in: 3599 });
  const storage = memoryStorage();
  const auth = new Auth(opts(storage));
  await auth.connect();
  assert.equal(seen.config.client_id, "CID");
  assert.equal(seen.config.scope, "S");
  assert.equal(auth.token, "new");
  assert.ok(auth.valid());
  assert.deepEqual(JSON.parse(storage.map.get("tv-tracker-token")), { token: "new", expiresAt: 1_000_000 + 3_599_000 });
});

test("connect rejects on a Google error and expire clears", async () => {
  fakeGoogle({ error: "access_denied" });
  const storage = memoryStorage({ "tv-tracker-token": JSON.stringify({ token: "t", expiresAt: 2_000_000 }) });
  const auth = new Auth(opts(storage));
  await assert.rejects(auth.connect(), /access_denied/);
  auth.expire();
  assert.equal(auth.token, null);
  assert.ok(!storage.map.has("tv-tracker-token"));
});

test("works without storage", () => {
  const auth = new Auth(opts(null));
  assert.equal(auth.token, null);
  auth.expire();
});
```

- [ ] **Step 2: Run to verify failure**

Run: `node --test posts/tv_tracker/app/*.test.js`
Expected: FAIL, `Cannot find module …/auth.js`

- [ ] **Step 3: Implement**

`posts/tv_tracker/app/auth.js`:
```js
const KEY = "tv-tracker-token";

export class Auth {
  constructor({ clientId, scope, storage, now = () => Date.now() }) {
    this.clientId = clientId;
    this.scope = scope;
    this.storage = storage;
    this.now = now;
    this.token = null;
    this.expiresAt = 0;
    try {
      const saved = JSON.parse(this.storage.getItem(KEY));
      if (saved && saved.expiresAt > this.now()) {
        this.token = saved.token;
        this.expiresAt = saved.expiresAt;
      }
    } catch {
      // no storage or bad data: start signed out
    }
  }

  valid() {
    return Boolean(this.token) && this.expiresAt - 60_000 > this.now();
  }

  expire() {
    this.token = null;
    this.expiresAt = 0;
    try {
      this.storage.removeItem(KEY);
    } catch {
      // nothing saved
    }
  }

  connect() {
    return new Promise((resolve, reject) => {
      const client = globalThis.google.accounts.oauth2.initTokenClient({
        client_id: this.clientId,
        scope: this.scope,
        callback: (response) => {
          if (response.error) {
            reject(new Error(response.error));
            return;
          }
          this.token = response.access_token;
          this.expiresAt = this.now() + Number(response.expires_in) * 1000;
          try {
            this.storage.setItem(KEY, JSON.stringify({ token: this.token, expiresAt: this.expiresAt }));
          } catch {
            // token still works for this page
          }
          resolve();
        },
        error_callback: (error) => reject(new Error(error?.type ?? "popup_closed")),
      });
      client.requestAccessToken({ prompt: "" });
    });
  }
}
```

- [ ] **Step 4: Run to verify pass**

Run: `node --test posts/tv_tracker/app/*.test.js`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add posts/tv_tracker/app/auth.js posts/tv_tracker/app/auth.test.js
git commit -m "feat(tv-tracker): Google Identity Services token auth with reload persistence

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: Write actions and auth retry

**Files:**
- Create: `posts/tv_tracker/app/actions.js`
- Test: `posts/tv_tracker/app/actions.test.js`

**Interfaces:**
- Consumes: `planCardStatus`, `planTrack`, `planUntrack`, `rowsFromValues`, `AuthError`, `tabRange`.
- Produces: `class StaleError`; `markCard(ctx, card, status)`; `trackShow(ctx, show, source, card = null)`; `untrackShow(ctx, tmdbId)`; `perform(ctx, action) -> Promise<"done" | "pending">` (on `AuthError`: stores `ctx.pending = action`, calls `ctx.onAuthNeeded()`); `resumePending(ctx)`. `ctx` is `{sheets, nowIso(), today(), pending, onAuthNeeded()}`.

- [ ] **Step 1: Write the failing tests**

`posts/tv_tracker/app/actions.test.js`:
```js
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
```

- [ ] **Step 2: Run to verify failure**

Run: `node --test posts/tv_tracker/app/*.test.js`
Expected: FAIL, `Cannot find module …/actions.js`

- [ ] **Step 3: Implement**

`posts/tv_tracker/app/actions.js`:
```js
import { AuthError, tabRange } from "./sheets.js";
import { planCardStatus, planTrack, planUntrack, rowsFromValues } from "./state.js";

export class StaleError extends Error {}

function checkKey(columnA, card) {
  if (String(columnA[card._row - 1]?.[0] ?? "") !== card.card_id) {
    throw new StaleError("The Sheet changed since it loaded");
  }
}

export async function markCard(ctx, card, status) {
  const [cardKeys] = await ctx.sheets.get(["Cards!A:A"]);
  checkKey(cardKeys, card);
  await ctx.sheets.batchUpdate(planCardStatus(card, status, ctx.nowIso(), await ctx.sheets.sheetIds()));
}

export async function trackShow(ctx, show, source, card = null) {
  const [trackedValues, cardKeys] = await ctx.sheets.get([tabRange("Tracked"), "Cards!A:A"]);
  if (card) checkKey(cardKeys, card);
  const requests = planTrack({
    tracked: rowsFromValues("Tracked", trackedValues),
    show,
    source,
    card,
    today: ctx.today(),
    nowIso: ctx.nowIso(),
    sheetIds: await ctx.sheets.sheetIds(),
  });
  await ctx.sheets.batchUpdate(requests);
}

export async function untrackShow(ctx, tmdbId) {
  const [trackedValues] = await ctx.sheets.get([tabRange("Tracked")]);
  const requests = planUntrack({
    tracked: rowsFromValues("Tracked", trackedValues),
    tmdbId,
    nowIso: ctx.nowIso(),
    sheetIds: await ctx.sheets.sheetIds(),
  });
  if (requests.length) await ctx.sheets.batchUpdate(requests);
}

export async function perform(ctx, action) {
  try {
    await action();
    return "done";
  } catch (error) {
    if (error instanceof AuthError) {
      ctx.pending = action;
      ctx.onAuthNeeded();
      return "pending";
    }
    throw error;
  }
}

export async function resumePending(ctx) {
  const action = ctx.pending;
  ctx.pending = null;
  return action ? perform(ctx, action) : null;
}
```

- [ ] **Step 4: Run to verify pass**

Run: `node --test posts/tv_tracker/app/*.test.js`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add posts/tv_tracker/app/actions.js posts/tv_tracker/app/actions.test.js
git commit -m "feat(tv-tracker): app write actions with key checks and auth-expiry retry

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The page, wiring and publishing

**Files:**
- Create: `posts/tv_tracker/app/index.html`, `posts/tv_tracker/app/styles.css`, `posts/tv_tracker/app/config.js`, `posts/tv_tracker/app/app.js`
- Modify: `_quarto.yml` (resources), `.github/workflows/test.yml` (node step)

**Interfaces:**
- Consumes: everything above. DOM only; verified manually in Task 8.

- [ ] **Step 1: Write the files**

`posts/tv_tracker/app/config.js` (values filled in Task 8; all public by design):
```js
export const CONFIG = {
  SHEET_ID: "",
  CLIENT_ID: "",
  TMDB_API_KEY: "",
};
```

`posts/tv_tracker/app/index.html`:
```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover" />
    <meta name="robots" content="noindex" />
    <meta name="theme-color" content="#14161a" />
    <title>TV Tracker</title>
    <link rel="stylesheet" href="styles.css" />
    <script src="https://accounts.google.com/gsi/client" async></script>
    <script type="module" src="app.js"></script>
  </head>
  <body>
    <header class="top">
      <h1>TV Tracker</h1>
      <button id="refresh" class="icon" aria-label="Refresh">↻</button>
    </header>
    <main>
      <section id="view-feed" class="view">
        <p id="feed-empty" class="empty" hidden>All caught up.</p>
        <ul id="feed" class="cards"></ul>
      </section>
      <section id="view-week" class="view" hidden>
        <p id="week-status" class="status"></p>
        <div id="week"></div>
      </section>
      <section id="view-shows" class="view" hidden>
        <input id="search" type="search" placeholder="Search to track a show" autocomplete="off" />
        <ul id="results" class="shows"></ul>
        <h2>Tracking</h2>
        <ul id="tracked" class="shows"></ul>
      </section>
    </main>
    <nav class="tabs">
      <button data-view="feed" class="active">Feed</button>
      <button data-view="week">This Week</button>
      <button data-view="shows">Shows</button>
    </nav>
    <div id="gate" class="gate" hidden>
      <div class="gate-box">
        <h2>TV Tracker</h2>
        <p id="gate-text"></p>
        <button id="connect" class="primary">Connect Google</button>
      </div>
    </div>
    <div id="toast" class="toast" role="status" hidden></div>
  </body>
</html>
```

`posts/tv_tracker/app/styles.css`:
```css
:root {
  color-scheme: light dark;
  --bg: #f4f4f1;
  --panel: #ffffff;
  --text: #16181c;
  --muted: #62666e;
  --line: #dedfdb;
  --accent: #d9480f;
  --accent-text: #ffffff;
  --radius: 12px;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #14161a;
    --panel: #1e2127;
    --text: #eceef2;
    --muted: #9aa0aa;
    --line: #2d3139;
    --accent: #ff6b35;
    --accent-text: #14161a;
  }
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  padding: env(safe-area-inset-top, 0) 16px calc(72px + env(safe-area-inset-bottom, 0));
}
.top { display: flex; align-items: center; justify-content: space-between; padding-block: 12px; }
.top h1 { font-size: 1.25rem; margin: 0; }
button {
  font: inherit; border: 1px solid var(--line); background: var(--panel); color: var(--text);
  border-radius: 999px; padding: 6px 14px; cursor: pointer;
}
button.primary { background: var(--accent); border-color: var(--accent); color: var(--accent-text); font-weight: 600; }
button.icon { font-size: 1.2rem; padding: 4px 10px; }
ul { list-style: none; margin: 0; padding: 0; }
.cards { display: grid; gap: 12px; }
.card {
  display: grid; grid-template-columns: 84px 1fr; gap: 12px; background: var(--panel);
  border: 1px solid var(--line); border-radius: var(--radius); padding: 10px; overflow: hidden;
}
.card img, .card .noimg { width: 84px; aspect-ratio: 2 / 3; object-fit: cover; border-radius: 8px; background: var(--line); }
.card .body { min-width: 0; display: flex; flex-direction: column; gap: 4px; }
.card h3 { margin: 0; font-size: 1rem; }
.card p { margin: 0; }
.kind { font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.06em; color: var(--accent); font-weight: 700; }
.sub { font-weight: 500; }
.detail, .meta { color: var(--muted); font-size: 0.88rem; }
.meta a { color: inherit; }
.actions { display: flex; gap: 8px; margin-top: auto; padding-top: 6px; }
.empty { color: var(--muted); text-align: center; padding: 32px 0; }
.status { color: var(--muted); font-size: 0.9rem; margin: 0 0 8px; }
.status.stale-week, .status.failed { color: var(--accent); }
.day { margin-bottom: 16px; }
.day h3 { font-size: 0.95rem; margin: 0 0 6px; color: var(--muted); }
.day.today h3 { color: var(--accent); }
.airings li, .shows li {
  display: flex; align-items: center; gap: 10px; background: var(--panel); border: 1px solid var(--line);
  border-radius: var(--radius); padding: 8px; margin-bottom: 8px;
}
.airings img, .airings .noimg, .shows img, .shows .noimg {
  width: 44px; aspect-ratio: 2 / 3; object-fit: cover; border-radius: 6px; background: var(--line); flex: none;
}
.airings p { margin: 2px 0 0; }
.shows li span { flex: 1; min-width: 0; }
.tag { color: var(--muted); font-size: 0.85rem; flex: none !important; }
#search {
  width: 100%; font: inherit; padding: 10px 14px; border-radius: 999px; border: 1px solid var(--line);
  background: var(--panel); color: var(--text); margin-bottom: 12px;
}
h2 { font-size: 1rem; margin: 20px 0 8px; }
.tabs {
  position: fixed; left: 0; right: 0; bottom: 0; display: grid; grid-template-columns: repeat(3, 1fr);
  background: var(--panel); border-top: 1px solid var(--line); padding: 8px 8px calc(8px + env(safe-area-inset-bottom, 0));
}
.tabs button { border: none; background: none; border-radius: 8px; color: var(--muted); }
.tabs button.active { color: var(--accent); font-weight: 700; }
.gate { position: fixed; inset: 0; background: var(--bg); display: grid; place-items: center; padding: 24px; }
.gate-box { text-align: center; max-width: 320px; }
.toast {
  position: fixed; left: 16px; right: 16px; bottom: calc(80px + env(safe-area-inset-bottom, 0));
  background: var(--text); color: var(--bg); padding: 10px 14px; border-radius: var(--radius); text-align: center;
}
[hidden] { display: none !important; }
```

`posts/tv_tracker/app/app.js`:
```js
import { CONFIG } from "./config.js";
import { Auth } from "./auth.js";
import { AuthError, ForbiddenError, SheetsClient } from "./sheets.js";
import { StaleError, markCard, perform, resumePending, trackShow, untrackShow } from "./actions.js";
import { searchShows } from "./tmdb.js";
import { activeShows, dayLabel, domain, safeUrl, scheduleDays, scheduleHeader, torontoDate, visibleCards } from "./state.js";

const SCOPE = "https://www.googleapis.com/auth/spreadsheets";
const TYPE_LABEL = { episode: "New episode", season: "Season date", news: "News", suggestion: "You might like" };

function storage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

const auth = new Auth({ clientId: CONFIG.CLIENT_ID, scope: SCOPE, storage: storage() });
const sheets = new SheetsClient({ sheetId: CONFIG.SHEET_ID, getToken: () => auth.token });
const ctx = {
  sheets,
  nowIso: () => new Date().toISOString(),
  today: () => torontoDate(),
  pending: null,
  onAuthNeeded: () => {
    auth.expire();
    showGate("Your Google session expired. Reconnect to save.", "Reconnect Google");
  },
};
let data = null;
let results = [];

const $ = (id) => document.getElementById(id);

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "onclick") node.addEventListener("click", value);
    else if (key === "class") node.className = value;
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child !== null && child !== undefined && child !== false) node.append(child);
  }
  return node;
}

function poster(url) {
  const src = safeUrl(url);
  return src ? el("img", { src, alt: "", loading: "lazy" }) : el("div", { class: "noimg" });
}

function link(url, text) {
  const href = safeUrl(url);
  return href ? el("a", { href, target: "_blank", rel: "noopener noreferrer" }, text) : null;
}

function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    node.hidden = true;
  }, 4000);
}

function showGate(text, button) {
  $("gate-text").textContent = text;
  $("connect").hidden = !button;
  if (button) $("connect").textContent = button;
  $("gate").hidden = false;
}

async function load() {
  try {
    data = await sheets.readAll();
    $("gate").hidden = true;
    render();
  } catch (error) {
    if (error instanceof ForbiddenError) showGate("This app is private.", null);
    else if (error instanceof AuthError) ctx.onAuthNeeded();
    else toast("Couldn't load the Sheet");
  }
}

async function failed(error) {
  if (error instanceof StaleError) {
    toast("The Sheet changed, so it was reloaded");
    await load();
  } else if (error instanceof ForbiddenError) {
    showGate("This app is private.", null);
  } else {
    toast("Couldn't save");
  }
}

async function write(action, undo) {
  try {
    if ((await perform(ctx, action)) === "done") await load();
  } catch (error) {
    undo();
    render();
    await failed(error);
  }
}

function setStatus(card, status) {
  card.status = status;
  render();
  write(
    () => markCard(ctx, card, status),
    () => {
      card.status = "new";
    },
  );
}

function pendingSuggestion(tmdbId) {
  return data.Cards.find((c) => c.type === "suggestion" && c.status === "new" && Number(c.tmdb_id) === tmdbId) ?? null;
}

function track(show, source, card = null) {
  const row = { tmdb_id: show.tmdb_id, name: show.name, poster_url: show.poster_url, active: true, _row: 0 };
  if (card) card.status = "tracked";
  data.Tracked.push(row);
  render();
  toast(`Tracking ${show.name}. Episodes appear after the next daily update.`);
  write(
    () => trackShow(ctx, show, source, card),
    () => {
      if (card) card.status = "new";
      data.Tracked = data.Tracked.filter((r) => r !== row);
    },
  );
}

function untrack(tmdbId) {
  const changed = data.Tracked.filter((r) => Number(r.tmdb_id) === tmdbId);
  const before = changed.map((r) => r.active);
  for (const r of changed) r.active = false;
  render();
  write(
    () => untrackShow(ctx, tmdbId),
    () => changed.forEach((r, i) => {
      r.active = before[i];
    }),
  );
}

function formatDay(value) {
  return /^\d{4}-\d{2}-\d{2}/.test(String(value)) ? dayLabel(String(value).slice(0, 10)) : String(value);
}

function cardView(card) {
  const suggestion = card.type === "suggestion";
  const linkText = card.type === "news" ? domain(card.link) : String(card.link).includes("imdb.com") ? "IMDb" : "TMDB";
  const buttons = suggestion
    ? [
        el("button", { class: "primary", onclick: () => track({ tmdb_id: Number(card.tmdb_id), name: String(card.show_name), first_air_year: Number(card.date) || "", poster_url: card.image_url }, "suggestion", card) }, "Track"),
        el("button", { onclick: () => setStatus(card, "ignored") }, "Ignore"),
      ]
    : [el("button", { class: "primary", onclick: () => setStatus(card, "noted") }, "Noted")];
  const when = suggestion ? `First aired ${card.date}` : formatDay(card.date);
  const source = link(card.link, linkText);
  return el(
    "li",
    { class: `card ${card.type}` },
    poster(card.image_url),
    el(
      "div",
      { class: "body" },
      el("p", { class: "kind" }, TYPE_LABEL[card.type] ?? String(card.type)),
      el("h3", {}, String(card.show_name)),
      el("p", { class: "sub" }, String(suggestion ? card.body : card.headline)),
      card.type === "news" && card.body ? el("p", { class: "detail" }, String(card.body)) : null,
      el("p", { class: "meta" }, when, source ? " · " : "", source),
      el("div", { class: "actions" }, buttons),
    ),
  );
}

function renderFeed() {
  const cards = visibleCards(data.Cards, data.Tracked);
  $("feed-empty").hidden = cards.length > 0;
  $("feed").replaceChildren(...cards.map(cardView));
}

function renderWeek() {
  const today = torontoDate();
  const header = scheduleHeader(data.Meta, today, Date.now());
  const status = $("week-status");
  status.textContent = header.text;
  status.className = `status ${header.kind}`;
  const days = scheduleDays(data.Schedule, data.Tracked, today);
  const container = $("week");
  if (!days.some((day) => day.items.length)) {
    container.replaceChildren(el("p", { class: "empty" }, header.kind === "ok" ? "Nothing airing this week." : "No schedule yet."));
    return;
  }
  container.replaceChildren(
    ...days
      .filter((day) => day.items.length || day.isToday)
      .map((day) =>
        el(
          "section",
          { class: day.isToday ? "day today" : "day" },
          el("h3", {}, day.isToday ? `Today · ${day.label}` : day.label),
          day.items.length
            ? el(
                "ul",
                { class: "airings" },
                day.items.map((item) =>
                  el(
                    "li",
                    {},
                    poster(item.image_url),
                    el(
                      "div",
                      {},
                      el("strong", {}, String(item.show_name)),
                      el("p", {}, String(item.episode_label)),
                      el("p", { class: "meta" }, [item.time, item.network].filter(Boolean).join(" · ")),
                    ),
                  ),
                ),
              )
            : el("p", { class: "meta" }, "Nothing today."),
        ),
      ),
  );
}

function renderResults() {
  const tracking = new Set(activeShows(data.Tracked).map((s) => s.tmdb_id));
  $("results").replaceChildren(
    ...results.map((show) =>
      el(
        "li",
        {},
        poster(show.poster_url),
        el("span", {}, show.first_air_year ? `${show.name} (${show.first_air_year})` : show.name),
        tracking.has(show.tmdb_id)
          ? el("span", { class: "tag" }, "Tracking")
          : el("button", { class: "primary", onclick: () => track(show, "search", pendingSuggestion(show.tmdb_id)) }, "Track"),
      ),
    ),
  );
}

function renderShows() {
  $("tracked").replaceChildren(
    ...activeShows(data.Tracked).map((show) =>
      el("li", {}, poster(show.poster_url), el("span", {}, show.name), el("button", { onclick: () => untrack(show.tmdb_id) }, "Untrack")),
    ),
  );
  renderResults();
}

function render() {
  if (!data) return;
  renderFeed();
  renderWeek();
  renderShows();
}

let searchTimer;
$("search").addEventListener("input", (event) => {
  clearTimeout(searchTimer);
  const query = event.target.value.trim();
  searchTimer = setTimeout(async () => {
    if (!query) {
      results = [];
    } else {
      try {
        results = await searchShows(query, CONFIG.TMDB_API_KEY);
      } catch {
        toast("Search failed");
        return;
      }
    }
    if (data) renderResults();
  }, 300);
});

for (const button of document.querySelectorAll(".tabs button")) {
  button.addEventListener("click", () => {
    for (const other of document.querySelectorAll(".tabs button")) other.classList.toggle("active", other === button);
    for (const view of document.querySelectorAll(".view")) view.hidden = view.id !== `view-${button.dataset.view}`;
  });
}

$("connect").addEventListener("click", async () => {
  try {
    await auth.connect();
  } catch {
    toast("Google sign-in didn't finish");
    return;
  }
  $("gate").hidden = true;
  if (ctx.pending) {
    try {
      await resumePending(ctx);
    } catch (error) {
      await failed(error);
    }
  }
  await load();
});

$("refresh").addEventListener("click", () => {
  if (auth.valid()) load();
  else showGate("Connect your Google account to load your shows.", "Connect Google");
});

if (auth.valid()) load();
else showGate("Connect your Google account to load your shows.", "Connect Google");
```

In `_quarto.yml`, add under `resources:` after `- "posts/chess/app/**"`:
```yaml
    - "posts/tv_tracker/app/**"
```

In `.github/workflows/test.yml`, after the `TV tracker tests` step, add:
```yaml
      - name: TV tracker app tests
        run: node --test posts/tv_tracker/app/*.test.js
```

- [ ] **Step 2: Verify**

Run: `node --test posts/tv_tracker/app/*.test.js && uv run --group tv-tracker python -m pytest tv-tracker/tests -q && node --check posts/tv_tracker/app/app.js`
Expected: all pass; `app.js` parses. (Module resolution in `app.js` is exercised in Task 8's browser check.)

Run a static smoke test: `python3 -m http.server 8000 --directory posts/tv_tracker/app` in the background, then `curl -s localhost:8000/ | grep -c "TV Tracker"` → `2` (title and gate heading). Stop the server.

- [ ] **Step 3: Commit**

```bash
git add posts/tv_tracker/app/index.html posts/tv_tracker/app/styles.css posts/tv_tracker/app/config.js posts/tv_tracker/app/app.js _quarto.yml .github/workflows/test.yml
git commit -m "feat(tv-tracker): app page with feed, this week and shows views

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: OAuth client, local check and publish (needs Nick)

- [ ] **Step 1: OAuth client (Nick, manual, same Google Cloud project `tv-tracker`)**
  1. **Google Auth Platform → Branding:** app name "TV Tracker", your email as support and developer contact.
  2. **Audience:** User type **External**, then **Publish app** (moves it to "In production"; no verification needed for personal use).
  3. **Data access → Add or remove scopes:** add `https://www.googleapis.com/auth/spreadsheets`.
  4. **Clients → Create client → Web application**, name "TV Tracker web". Authorized JavaScript origins: `https://nicholastacik.github.io` and `http://localhost:8000`. No redirect URIs. Copy the **Client ID**.
  5. TMDB → Settings → API: copy the **API Key** (the short v3 key, not the long Read Access Token).

- [ ] **Step 2: Fill `config.js`** with `SHEET_ID` (from `.env`), `CLIENT_ID` and `TMDB_API_KEY`. Commit. These values are public by design.

- [ ] **Step 3: Local browser check (Nick)**

Run: `python3 -m http.server 8000 --directory posts/tv_tracker/app` and open `http://localhost:8000`.
Check: Connect Google → the consent screen shows the "unverified app" warning once (Advanced → continue) → the feed shows the Sheet's cards; This Week shows the schedule in Eastern; Shows lists 11 shows; search finds a show. Mark one card **Noted** and confirm its `status` changes in the Sheet. Reload: it stays gone and no sign-in is needed.

- [ ] **Step 4: Publish (ask Nick):** push `tv-tracker` to `main`. The Publish workflow deploys to `https://nicholastacik.github.io/posts/tv_tracker/app/`. Open it on the phone, sign in, and optionally Add to Home Screen.

- [ ] **Step 5: Notes:** append app findings (aggregate) to `posts/tv_tracker/notes/BUILD_NOTES.md` and commit.
