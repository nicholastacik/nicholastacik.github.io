# Practice-Mode Browser Regression Harness — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A jsdom harness that loads the *real* generated research page and drives Practice mode through its screen transitions, persistence, keyboard, and save-failure paths — closing the gap the pure-scheduler unit tests can't cover.

**Architecture:** A Python module renders a small fixed fixture page through the real `build_research_data` + `render_html`. A Node (`node:test`) harness spawns that renderer once per file, loads the HTML into a fresh jsdom per test (`runScripts:"dangerously"`, fixed clock/RNG installed in `beforeParse`), drives the UI via events, and asserts. No production code changes — only new files under `jeopardy/tests/browser/`, a `.gitignore` line, and a CI workflow.

**Tech Stack:** Python (pandas) for the fixture; Node 24 + jsdom `^29.1.1` (dir-scoped devDependency) + `node:test`; GitHub Actions for CI.

## Global Constraints

- **Work in the worktree** `/Users/nick/Work/practice-harness-wt` on branch `feat/practice-harness`. All paths below are repo-relative.
- **No production code changes.** Only add: `jeopardy/tests/browser/*`, a line in `.gitignore`, and `.github/workflows/test.yml`. Do not touch `jeopardy/analysis/research.py` or `practice.js`.
- **jsdom pinned `^29.1.1`** (jsdom 30 requires Node `^24.15`; local Node is 24.4.0). jsdom 29 engines: `^20.19.0 || ^22.13.0 || >=24.0.0` — satisfied by local Node 24.4.0 and CI Node 24.
- **`"type": "module"`** and the jsdom dep live ONLY in `jeopardy/tests/browser/package.json`, scoping the first JS dependency to that directory.
- **localStorage key is exactly** `jeopardy-practice-v1`.
- **Determinism:** the harness installs a fixed `window.Date.now` (`FIXED_NOW`) and `window.Math.random = () => 0` in `beforeParse`, before page scripts run. Pure functions in the page read these.
- **Fixture render command:** `uv run --frozen --group analysis python -m jeopardy.tests.browser.render_fixture` (imports `research.py` → needs pandas from the `analysis` group), spawned with `cwd` = repo root resolved from `import.meta.url`.
- **Run the Node harness with a shell glob:** `node --test jeopardy/tests/browser/*.test.js` (a bare directory arg is unreliable on this Node version; a glob expands to explicit files).
- **pytest lives in the `scraper` dependency group** (not `analysis`); any pytest run needs `--group scraper --group analysis`. (The `render_fixture` *module* run needs only `--group analysis` — it imports pandas, not pytest.)
- **Full Python suite** (CI): `uv run --frozen --group scraper --group analysis python -m pytest jeopardy/tests -q` (analysis for pandas/sklearn, scraper for crawl/fetch test deps).
- **Never commit `node_modules/`.**
- **Commit trailer** on every commit (blank line before it):
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  ```

## Target ids / messages the harness drives (from the committed page — do not change them)

- Entry/overlay: `#practice-open`, `#practice`, `#practice-exit`, `#practice-body`, `#practice-progress`, `#practice-tally`, `#practice-notice`.
- Start screen: `#ptopic-all`, checkboxes `.ptopic-cb` (value = cluster id), radios `input[name=psize]` (values 10/20/30), `#pextra`, `#practice-start`, `#practice-startnote`, `#practice-reset`.
- Card: `#pcard-reveal`, grade buttons `.pgrade` with `data-g` in `{knew,unsure,missed}`, answer paragraph `.pcard-answer`, clue paragraph `.pcard-clue`.
- Summary: `#practice-again`, `#practice-done`.
- Messages: disabled note `"Nothing due — turn on Extra practice, or widen your era / topics."`; save-failure `"Progress isn't being saved (storage unavailable)."`; summary contains `"scheduled to come back later"`.

---

### Task 1: Python fixture renderer

**Files:**
- Create: `jeopardy/tests/browser/__init__.py`
- Create: `jeopardy/tests/browser/render_fixture.py`
- Create (Test): `jeopardy/tests/browser/test_render_fixture.py`

**Interfaces:**
- Consumes: `jeopardy.analysis.research.build_research_data`, `render_html` (existing).
- Produces:
  - `build_fixture_data() -> dict` — the embedded DATA dict.
  - `build_fixture_html() -> str` — the full self-contained page.
  - Runnable as `python -m jeopardy.tests.browser.render_fixture` → prints the HTML to stdout.

- [ ] **Step 1: Create the package marker**

Create `jeopardy/tests/browser/__init__.py` (empty file).

- [ ] **Step 2: Write the failing test**

Create `jeopardy/tests/browser/test_render_fixture.py`:

```python
from jeopardy.tests.browser.render_fixture import build_fixture_data, build_fixture_html


def test_fixture_data_has_two_topics_and_expected_clues():
    data = build_fixture_data()
    # two topics available to the picker
    assert set(data["quiz"].keys()) == {"1", "2"}
    # the out-of-era clue is kept in the store (excluded at runtime by the year filter)
    assert data["clues"]["old"]["year"] == 2005
    assert data["clues"]["a1"]["year"] == 2014
    # the twice-referenced id exists once in the store
    assert "dup" in data["clues"]
    # Topic Alpha (cluster 1) references dup in BOTH the general pool and an entity
    alpha = data["quiz"]["1"]
    dup_refs = sum(1 for ids in alpha.values() if "dup" in ids)
    assert dup_refs == 2


def test_fixture_html_is_self_contained_with_practice():
    html = build_fixture_html()
    for marker in ['id="practice-open"', 'id="practice"', "Topic Alpha", "Topic Beta",
                   "function assembleSession", "jeopardy-practice-v1"]:
        assert marker in html, marker
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run --frozen --group scraper --group analysis python -m pytest jeopardy/tests/browser/test_render_fixture.py -q`
Expected: FAIL — `ModuleNotFoundError: jeopardy.tests.browser.render_fixture`.

- [ ] **Step 4: Write the fixture renderer**

Create `jeopardy/tests/browser/render_fixture.py`:

```python
"""Render a small, fixed research page for the jsdom Practice-mode harness.

Builds tiny fixture DataFrames, runs them through the REAL build_research_data +
render_html, and prints the self-contained HTML to stdout. Run as:
    uv run --frozen --group analysis python -m jeopardy.tests.browser.render_fixture
"""
import pandas as pd

from jeopardy.analysis.research import build_research_data, render_html

# Two topics; era 2010 only, so the page's currentEra defaults to 2010.
_LABELS = {1: "Topic Alpha", 2: "Topic Beta"}


def _tokens_df():
    return pd.DataFrame([
        {"era": 2010, "cluster_id": 1, "rank": 1, "phrase": "Alpha One", "count": 10},
        {"era": 2010, "cluster_id": 1, "rank": 2, "phrase": "Alpha Two", "count": 8},
        {"era": 2010, "cluster_id": 2, "rank": 1, "phrase": "Beta One", "count": 6},
    ])


def _eras_df():
    return pd.DataFrame([
        {"era": 2010, "cluster_id": 1, "size": 100, "share": 0.05, "n_qualifying_phrases": 2},
        {"era": 2010, "cluster_id": 2, "size": 50, "share": 0.02, "n_qualifying_phrases": 1},
    ])


def _quiz_refs_df():
    # 'dup' is referenced in both the general pool and an entity -> must dedupe to one card.
    # 'old' is pre-2010 -> excluded by the era filter at runtime (era 2010).
    return pd.DataFrame([
        {"cluster_id": 1, "phrase": None, "clue_ids": ["g1", "g2", "dup"]},
        {"cluster_id": 1, "phrase": "Alpha One", "clue_ids": ["a1", "dup"]},
        {"cluster_id": 1, "phrase": "Alpha Two", "clue_ids": ["a2", "old"]},
        {"cluster_id": 2, "phrase": None, "clue_ids": ["b1", "b2"]},
    ])


def _clues_df():
    rows = [("g1", 2011), ("g2", 2012), ("dup", 2013), ("a1", 2014),
            ("a2", 2015), ("old", 2005), ("b1", 2016), ("b2", 2017)]
    return pd.DataFrame([
        {"clue_id": cid, "clue": f"Clue text for {cid}", "answer": f"Answer {cid}",
         "year": yr, "category": "FIXTURE CATEGORY", "game_id": 1000 + i}
        for i, (cid, yr) in enumerate(rows)
    ])


def build_fixture_data():
    return build_research_data(_tokens_df(), _eras_df(), _LABELS,
                               fingerprints_df=None, quiz_refs_df=_quiz_refs_df(),
                               clues_df=_clues_df())


def build_fixture_html():
    return render_html(build_fixture_data())


if __name__ == "__main__":
    print(build_fixture_html())
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run --frozen --group scraper --group analysis python -m pytest jeopardy/tests/browser/test_render_fixture.py -q`
Expected: PASS — 2 tests.

- [ ] **Step 6: Verify the module prints a page from the repo root**

Run: `uv run --frozen --group analysis python -m jeopardy.tests.browser.render_fixture | head -c 120`
Expected: begins with `<!doctype html`.

- [ ] **Step 7: Commit**

```bash
git add jeopardy/tests/browser/__init__.py jeopardy/tests/browser/render_fixture.py jeopardy/tests/browser/test_render_fixture.py
git commit -m "test: fixture renderer for the practice-mode jsdom harness

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: npm scaffolding + jsdom lock

**Files:**
- Create: `jeopardy/tests/browser/package.json`
- Create: `jeopardy/tests/browser/package-lock.json` (generated by `npm install`)
- Modify: `.gitignore` (append the harness `node_modules`)

**Interfaces:**
- Produces: an installable, locked jsdom dependency scoped to `jeopardy/tests/browser/`; `import { JSDOM } from "jsdom"` resolves for later tasks.

- [ ] **Step 1: Create `package.json`**

Create `jeopardy/tests/browser/package.json`:

```json
{
  "name": "jeopardy-practice-harness",
  "private": true,
  "type": "module",
  "description": "jsdom regression harness for the research page's Practice mode",
  "devDependencies": {
    "jsdom": "^29.1.1"
  }
}
```

- [ ] **Step 2: Ignore the harness node_modules**

Append to `.gitignore` (repo root):

```
jeopardy/tests/browser/node_modules/
```

- [ ] **Step 3: Install jsdom (writes the lockfile)**

Run: `npm install --prefix jeopardy/tests/browser`
Expected: creates `jeopardy/tests/browser/node_modules/` and `jeopardy/tests/browser/package-lock.json`, resolving jsdom 29.x.

- [ ] **Step 4: Verify jsdom loads**

Run: `node --input-type=module -e "import('jsdom').then(m => { if (!m.JSDOM) { process.exit(1); } console.log('jsdom ok'); })" --eval-file-cwd jeopardy/tests/browser 2>/dev/null || (cd jeopardy/tests/browser && node --input-type=module -e "import('jsdom').then(m=>{if(!m.JSDOM)process.exit(1);console.log('jsdom ok')})")`
Expected: prints `jsdom ok`. (The `cd` fallback ensures Node resolves `jsdom` from the harness `node_modules`.)

- [ ] **Step 5: Confirm the lockfile pins jsdom**

Run: `grep -m1 '"jsdom"' jeopardy/tests/browser/package-lock.json`
Expected: a line referencing jsdom (version 29.x).

- [ ] **Step 6: Commit (lockfile + manifest only, never node_modules)**

```bash
git add jeopardy/tests/browser/package.json jeopardy/tests/browser/package-lock.json .gitignore
git commit -m "build: scope jsdom devDependency to the practice harness dir

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Harness helpers (`harness.js`) + self-test

**Files:**
- Create: `jeopardy/tests/browser/harness.js`
- Create (Test): `jeopardy/tests/browser/harness.test.js`

**Interfaces:**
- Consumes: Task 1's `render_fixture` module (via spawn), Task 2's jsdom.
- Produces (all ESM exports from `harness.js`):
  - `FIXED_NOW: number` — the fixed clock (ms).
  - `PKEY: string` — `"jeopardy-practice-v1"`.
  - `renderFixtureHtml() -> string` — spawns the Python renderer at the repo root and returns the page HTML.
  - `makeDom(html, { seedStorage?, quota? }) -> { dom, window, document, errors }` — fresh jsdom with fixed clock/RNG, optional seeded storage, optional `storageQuota`, and an `errors` array capturing `jsdomError` / window `error` / `unhandledrejection`.
  - `clickId(document, id)` — click an element by id.
  - `setChecked(el, value)` — set a checkbox/radio `checked` and dispatch a bubbling `change`.
  - `dispatchKey(el, key) -> KeyboardEvent` — dispatch a bubbling, cancelable `keydown` and return the event.

- [ ] **Step 1: Write the failing test**

Create `jeopardy/tests/browser/harness.test.js`:

```js
import { test, before, after } from "node:test";
import assert from "node:assert/strict";
import { renderFixtureHtml, makeDom } from "./harness.js";

let html;
before(() => { html = renderFixtureHtml(); });

test("fixture page loads in jsdom with the Practice entry and no script errors", () => {
  const { document, errors, dom } = makeDom(html);
  try {
    assert.ok(document.getElementById("practice-open"), "Practice button present");
    assert.ok(document.getElementById("practice"), "overlay present");
    assert.equal(errors.length, 0, "no page-script errors: " + errors.map(String).join(" | "));
  } finally {
    dom.window.close();
  }
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test jeopardy/tests/browser/harness.test.js`
Expected: FAIL — cannot find `./harness.js`.

- [ ] **Step 3: Write `harness.js`**

Create `jeopardy/tests/browser/harness.js`:

```js
// Test-only helpers for driving the real generated research page in jsdom.
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { JSDOM, VirtualConsole } from "jsdom";

export const FIXED_NOW = Date.UTC(2026, 0, 15); // fixed clock for reproducible due-dates
export const PKEY = "jeopardy-practice-v1";

// This file lives at <repo>/jeopardy/tests/browser/harness.js -> repo root is three up.
const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

export function renderFixtureHtml() {
  return execFileSync(
    "uv",
    ["run", "--frozen", "--group", "analysis", "python", "-m",
     "jeopardy.tests.browser.render_fixture"],
    { cwd: REPO_ROOT, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 }
  );
}

export function makeDom(html, { seedStorage, quota } = {}) {
  const errors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", (e) => errors.push(e));
  const options = {
    runScripts: "dangerously",
    url: "https://practice.test/",
    virtualConsole,
    beforeParse(window) {
      window.Date.now = () => FIXED_NOW;
      window.Math.random = () => 0;
      window.addEventListener("error", (e) => errors.push(e.error || new Error(e.message)));
      window.addEventListener("unhandledrejection", (e) => errors.push(e.reason));
      if (seedStorage !== undefined) window.localStorage.setItem(PKEY, seedStorage);
    },
  };
  if (quota !== undefined) options.storageQuota = quota;
  const dom = new JSDOM(html, options);
  return { dom, window: dom.window, document: dom.window.document, errors };
}

export function clickId(document, id) {
  const el = document.getElementById(id);
  if (!el) throw new Error("no element #" + id);
  el.click();
}

export function setChecked(el, value) {
  el.checked = value;
  el.dispatchEvent(new el.ownerDocument.defaultView.Event("change", { bubbles: true }));
}

export function dispatchKey(el, key) {
  const KeyboardEvent = el.ownerDocument.defaultView.KeyboardEvent;
  const ev = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
  el.dispatchEvent(ev);
  return ev;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test jeopardy/tests/browser/harness.test.js`
Expected: PASS — 1 test (the `before` hook shells `uv` to render the fixture).

- [ ] **Step 5: Commit**

```bash
git add jeopardy/tests/browser/harness.js jeopardy/tests/browser/harness.test.js
git commit -m "test: jsdom harness helpers (makeDom, fixture spawn, drivers)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Flows 1–3 — session, missed-resurface, persistence

**Files:**
- Create (Test): `jeopardy/tests/browser/practice-ui.test.js`

**Interfaces:**
- Consumes: `harness.js` (`renderFixtureHtml`, `makeDom`, `clickId`, `setChecked`, `PKEY`).
- Produces: three passing flows. Later task appends flows 4–6 to the same file.

Helpers used below (define once near the top of the test file):
- `selectOnlyAlpha(document)` — uncheck the `Topic Beta` checkbox (`.ptopic-cb[value="2"]`), leaving Alpha.
- `setSize(document, n)` — check the `input[name=psize][value="n"]` radio (dispatch change).
- `cardId(document)` — read `.pcard-clue` text `"Clue text for X"` → `X`.
- `runToSummary(document, gradeFor)` — loop: while a `#pcard-reveal` exists, read `cardId`, click reveal, click the grade returned by `gradeFor(id, index)`; stop when `#practice-again` appears; return the ordered list of card ids seen.

- [ ] **Step 1: Write the failing tests**

Create `jeopardy/tests/browser/practice-ui.test.js`:

```js
import { test, before } from "node:test";
import assert from "node:assert/strict";
import { renderFixtureHtml, makeDom, clickId, setChecked, PKEY } from "./harness.js";

let html;
before(() => { html = renderFixtureHtml(); });

// ---- shared driver helpers ----
function selectOnlyAlpha(document) {
  const beta = document.querySelector('.ptopic-cb[value="2"]');
  setChecked(beta, false);
}
function setSize(document, n) {
  const radio = document.querySelector(`input[name=psize][value="${n}"]`);
  setChecked(radio, true);
}
function cardId(document) {
  const p = document.querySelector(".pcard-clue");
  const m = p && /Clue text for (\w+)/.exec(p.textContent);
  return m ? m[1] : null;
}
function grade(document, g) {
  document.querySelector(`.pgrade[data-g="${g}"]`).click();
}
function runToSummary(document, gradeFor) {
  const seen = [];
  let guard = 0;
  while (document.getElementById("pcard-reveal") && guard++ < 100) {
    const id = cardId(document);
    seen.push(id);
    clickId(document, "pcard-reveal");
    grade(document, gradeFor(id, seen.length - 1));
  }
  return seen;
}

test("flow 1: full single-topic session -> summary (dedupe + era filter)", () => {
  const { document, dom, errors } = makeDom(html);
  try {
    clickId(document, "practice-open");
    selectOnlyAlpha(document);
    setSize(document, 10);
    clickId(document, "practice-start");
    const seen = runToSummary(document, () => "knew");
    // Alpha refs = {g1,g2,dup,a1,a2,old}; 'old' era-excluded, 'dup' deduped -> 5 distinct cards
    assert.equal(seen.length, 5, "deck is 5 distinct eligible cards");
    assert.ok(!seen.includes("old"), "pre-2010 clue excluded");
    assert.equal(seen.filter((x) => x === "dup").length, 1, "duplicate ref deduped");
    assert.ok(!seen.some((x) => ["b1", "b2"].includes(x)), "Topic Beta excluded");
    // summary
    const again = document.getElementById("practice-again");
    assert.ok(again, "summary shown");
    assert.match(document.getElementById("practice-tally").textContent, /5/);
    assert.match(document.getElementById("practice-body").textContent, /5 cards scheduled to come back later/);
    assert.equal(document.activeElement, again, "focus on Practice again");
    assert.equal(errors.length, 0, errors.map(String).join(" | "));
  } finally { dom.window.close(); }
});

test("flow 2: a missed card resurfaces once after three intervening cards", () => {
  const { document, dom } = makeDom(html);
  try {
    clickId(document, "practice-open");
    selectOnlyAlpha(document);
    clickId(document, "practice-start");
    // Miss the first card and its single retry; know everything else.
    const firstId = cardId(document);
    const seen = runToSummary(document, (id) => (id === firstId ? "missed" : "knew"));
    const positions = seen.map((x, i) => (x === firstId ? i : -1)).filter((i) => i >= 0);
    assert.equal(positions.length, 2, "missed card seen exactly twice (one retry)");
    assert.equal(positions[1] - positions[0], 4, "retry is after 3 intervening cards (min(3, remaining))");
  } finally { dom.window.close(); }
});

test("flow 3: progress persists across a reload (missed cards come back due)", () => {
  // Session 1: miss two cards (and their retries), know the rest; capture storage.
  let saved;
  {
    const { document, dom, window } = makeDom(html);
    const missed = new Set();
    clickId(document, "practice-open");
    selectOnlyAlpha(document);
    clickId(document, "practice-start");
    // miss the first two distinct cards (and any retry of them), know the rest
    const firstTwo = [];
    runToSummary(document, (id) => {
      if (firstTwo.length < 2 && !firstTwo.includes(id)) firstTwo.push(id);
      if (firstTwo.includes(id)) { missed.add(id); return "missed"; }
      return "knew";
    });
    saved = window.localStorage.getItem(PKEY);
    globalThis.__missed = [...missed];
    dom.window.close();
  }
  // Session 2: fresh DOM seeded with saved progress; only the due (missed) cards appear.
  {
    const { document, dom } = makeDom(html, { seedStorage: saved });
    clickId(document, "practice-open");
    selectOnlyAlpha(document);
    clickId(document, "practice-start");
    const seen = runToSummary(document, () => "knew");
    assert.deepEqual(seen.slice().sort(), globalThis.__missed.slice().sort(),
      "reload surfaces exactly the previously-missed (now-due) cards");
    dom.window.close();
  }
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test jeopardy/tests/browser/practice-ui.test.js`
Expected: FAIL — file has assertions but before it existed there was nothing; if run before any driver bug is fixed, failures pinpoint issues. (If they pass immediately, that's fine — the code under test already works; this is a regression harness, so green-on-first-run against correct code is expected. The meaningful "red" check is Step 3.)

- [ ] **Step 3: Prove the harness bites (run against the pre-fix behavior once)**

Temporarily edit the *fixture's* rendered page is not possible without touching production; instead confirm flow 2's arithmetic by asserting the exact retry gap (already `=== 4`). To confirm the suite genuinely fails on wrong behavior, run flow 1 with a deliberately wrong expected count locally (change `5` to `6`), observe FAIL, then revert. Do not commit the temporary change.

Run: `node --test jeopardy/tests/browser/practice-ui.test.js`
Expected after revert: PASS — 3 tests.

- [ ] **Step 4: Run to verify they pass**

Run: `node --test jeopardy/tests/browser/practice-ui.test.js`
Expected: PASS — 3 tests.

- [ ] **Step 5: Commit**

```bash
git add jeopardy/tests/browser/practice-ui.test.js
git commit -m "test: jsdom flows — full session, missed-resurface, persistence

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Flows 4–6 — no-due return, keyboard, save-failure

**Files:**
- Modify (Test): `jeopardy/tests/browser/practice-ui.test.js`

**Interfaces:**
- Consumes: the same imports + driver helpers from Task 4 (append to the file; do not re-import or redefine helpers).

- [ ] **Step 1: Append the failing tests**

Append to `jeopardy/tests/browser/practice-ui.test.js` (also add `dispatchKey` to the existing import from `./harness.js`):

```js
test("flow 4: Practice again with nothing due returns to setup, settings preserved", () => {
  const { document, dom } = makeDom(html);
  try {
    clickId(document, "practice-open");
    selectOnlyAlpha(document);
    setSize(document, 10);
    clickId(document, "practice-start");
    runToSummary(document, () => "knew"); // all knew -> all future-due
    clickId(document, "practice-again");  // nothing due -> back to setup
    // settings preserved
    assert.equal(document.querySelector('.ptopic-cb[value="1"]').checked, true, "Alpha still checked");
    assert.equal(document.querySelector('.ptopic-cb[value="2"]').checked, false, "Beta still unchecked");
    assert.equal(document.querySelector("input[name=psize]:checked").value, "10", "size 10 preserved");
    const start = document.getElementById("practice-start");
    assert.equal(start.disabled, true, "Start disabled (nothing due)");
    // the ACTUAL disabled-state note (updateStartAvailability overwrites the prefill note)
    assert.equal(document.getElementById("practice-startnote").textContent,
      "Nothing due — turn on Extra practice, or widen your era / topics.");
    assert.equal(document.activeElement, document.getElementById("pextra"),
      "focus on Extra-practice checkbox, not lost to BODY");
  } finally { dom.window.close(); }
});

test("flow 5: keyboard — Space does not hijack a focused button; 1/2/3 grade; click Exit closes", () => {
  const { document, dom } = makeDom(html);
  try {
    clickId(document, "practice-open");
    selectOnlyAlpha(document);
    clickId(document, "practice-start");
    // Space on the focused Exit button must NOT be intercepted (no reveal, not prevented)
    const exit = document.getElementById("practice-exit");
    exit.focus();
    const ev = dispatchKey(exit, " ");
    assert.equal(ev.defaultPrevented, false, "Space not preventDefaulted on Exit");
    assert.equal(document.querySelector(".pcard-answer"), null, "answer still hidden");
    // After reveal, digit keys grade and advance
    const before = cardId(document);
    clickId(document, "pcard-reveal");
    dispatchKey(document.body, "1"); // '1' = knew
    assert.notEqual(cardId(document), before, "grading via '1' advanced the card");
    // Clicking Exit closes the overlay and restores focus to the opener
    clickId(document, "practice-exit");
    assert.equal(document.getElementById("practice").hidden, true, "overlay closed");
    assert.equal(document.activeElement, document.getElementById("practice-open"),
      "focus restored to Practice button");
  } finally { dom.window.close(); }
});

test("flow 6: save failure shows the notice and grading still continues", () => {
  const { document, dom } = makeDom(html, { quota: 0 }); // setItem throws QuotaExceededError
  try {
    clickId(document, "practice-open");
    selectOnlyAlpha(document);
    clickId(document, "practice-start");
    const before = cardId(document);
    clickId(document, "pcard-reveal");
    grade(document, "knew"); // triggers saveCard -> setItem throws -> notice
    const notice = document.getElementById("practice-notice");
    assert.equal(notice.hidden, false, "notice shown");
    assert.match(notice.textContent, /Progress isn't being saved/);
    assert.notEqual(cardId(document), before, "session advanced despite save failure");
  } finally { dom.window.close(); }
});
```

Change the Task-4 import line at the top of the file from:

```js
import { renderFixtureHtml, makeDom, clickId, setChecked, PKEY } from "./harness.js";
```

to:

```js
import { renderFixtureHtml, makeDom, clickId, setChecked, dispatchKey, PKEY } from "./harness.js";
```

- [ ] **Step 2: Run tests to verify the new ones exercise real behavior**

Run: `node --test jeopardy/tests/browser/practice-ui.test.js`
Expected: PASS — 6 tests total. (These flows encode the exact bugs already fixed: flow 4 the disabled-Start focus bug, flow 5 the Space-interception bug.)

- [ ] **Step 3: Confirm the suite bites**

Locally, temporarily change flow 4's expected note to `"WRONG"`; run; observe FAIL; revert. Do not commit the temporary change.

Run: `node --test jeopardy/tests/browser/practice-ui.test.js`
Expected after revert: PASS — 6 tests.

- [ ] **Step 4: Commit**

```bash
git add jeopardy/tests/browser/practice-ui.test.js
git commit -m "test: jsdom flows — no-due return, keyboard guard, save failure

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: CI workflow + browser-only checklist

**Files:**
- Create: `.github/workflows/test.yml`
- Modify: `jeopardy/tests/browser/harness.js` (prepend a browser-only checklist comment)

**Interfaces:**
- Consumes: all prior tasks (runs their tests in CI).
- Produces: a `test` workflow running the full matrix on push / PR / dispatch.

- [ ] **Step 1: Add the browser-only checklist as a header comment**

Prepend to `jeopardy/tests/browser/harness.js` (above the first `import`):

```js
// Browser-only checklist — NOT covered by jsdom (verify manually in a real browser):
//  * native Space/Enter ACTIVATION of Exit/Reveal/grade buttons (jsdom runs activation
//    only for real click events, not dispatched key events);
//  * Tab focus-trap cycling (jsdom has no layout, so offsetParent is always null);
//  * inert background non-interactivity (jsdom does not implement `inert`);
//  * visual focus rings and prefers-reduced-motion.
```

- [ ] **Step 2: Create the workflow**

Create `.github/workflows/test.yml`:

```yaml
name: Tests

on:
  push:
  pull_request:
  workflow_dispatch:

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Check out
        uses: actions/checkout@v4

      - name: Set up uv
        uses: astral-sh/setup-uv@v6

      - name: Sync dependencies
        run: uv sync --frozen

      - name: Set up Node
        uses: actions/setup-node@v4
        with:
          node-version: '24'

      - name: Python tests
        run: uv run --frozen --group scraper --group analysis python -m pytest jeopardy/tests -q

      - name: JS unit tests (pure scheduler)
        run: node --test jeopardy/analysis/practice.test.js

      - name: Install harness dependencies
        run: npm ci --prefix jeopardy/tests/browser

      - name: Browser regression (jsdom)
        run: node --test jeopardy/tests/browser/*.test.js
```

- [ ] **Step 3: Validate the commands the workflow will run (locally)**

Run each and confirm success:
```bash
uv run --frozen --group scraper --group analysis python -m pytest jeopardy/tests -q
node --test jeopardy/analysis/practice.test.js
npm ci --prefix jeopardy/tests/browser
node --test jeopardy/tests/browser/*.test.js
```
Expected: pytest passes; pure-scheduler 16 pass; `npm ci` installs from the lockfile; the jsdom harness (Tasks 1/3/4/5 tests) passes.

- [ ] **Step 4: Validate the workflow YAML parses**

Run: `python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/test.yml')); print('yaml ok')"`
Expected: `yaml ok`. (PyYAML ships with the analysis env; if unavailable, run under `uv run --group analysis python -c ...`.)

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/test.yml jeopardy/tests/browser/harness.js
git commit -m "ci: run pytest + pure-scheduler + jsdom harness on push/PR

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage** (against `docs/superpowers/specs/2026-09-17-practice-harness-design.md`):
- Component `__init__.py` / `render_fixture.py` → Task 1; `package.json`/`package-lock.json`/`.gitignore` → Task 2; `harness.js` (makeDom, beforeParse clock/RNG/seed, storageQuota, error capture) → Task 3; `practice-ui.test.js` six flows → Tasks 4–5; `test.yml` + browser-only checklist → Task 6.
- Fixture requirements (two topics, out-of-era clue, duplicate ref) → Task 1 fixture + asserted in `test_render_fixture.py` and flow 1.
- Determinism (fixed `Date.now`/`Math.random` in `beforeParse`) → Task 3 `makeDom`.
- Page acquisition (render at test time via `uv run --frozen --group analysis python -m …`, once per file) → Task 3 `renderFixtureHtml` + Task 4/5 `before()`.
- All six flows with the spec's exact assertions (incl. flow 4 asserting the *actual* disabled-state note, flow 5 the Space-interception guard via `defaultPrevented===false` + hidden answer, flow 6 `storageQuota:0`) → Tasks 4–5.
- CI groups exactly per spec (`--group scraper --group analysis`, `python -m pytest`) → Task 6.
- Browser-only checklist documented → Task 6.

**2. Placeholder scan:** No "TBD"/"handle errors"/"similar to". Every code step has complete code. Task 4 Step 3 / Task 5 Step 3 are explicit "prove-it-bites" steps with a concrete temporary edit + revert, not a placeholder.

**3. Type/name consistency:** `renderFixtureHtml`, `makeDom({seedStorage,quota})`, `clickId`, `setChecked`, `dispatchKey`, `PKEY`, `FIXED_NOW` are defined in Task 3 and used with the same signatures in Tasks 4–5. Element ids/classes and message strings match the "Target ids / messages" section (verified against the committed page). The fixture's cluster ids (1=Alpha, 2=Beta) are used consistently in the fixture, `test_render_fixture.py`, and the flow selectors (`.ptopic-cb[value="1"|"2"]`).

**Note for executor:** run all tasks inside the worktree `/Users/nick/Work/practice-harness-wt`. Tasks 4 and 5 edit the same file; Task 5 appends and widens the import line — apply in order.
