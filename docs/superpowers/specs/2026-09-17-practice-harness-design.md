# Practice-Mode Browser Regression Harness — Design Spec

**Date:** 2026-09-17
**Status:** Approved design (review adjustments folded in), pending spec review
**Feature:** A headless-DOM (jsdom) regression harness that drives the real generated research page through Practice mode's screen transitions, persistence, and keyboard handling — closing the gap left by the pure-scheduler unit tests.

## Goal

The pure scheduler `jeopardy/analysis/practice.js` is fully unit-tested (`node:test`, 16 cases). The bugs that actually reached review, though, were all in the **inline DOM/localStorage/keyboard glue** embedded in `research.py`'s HTML template — screen transitions, `renderStart(prefill)` restoration, focus targets, the save-failure notice. Those are invisible to a pure-function test.

This harness loads the **real generated page** into jsdom and drives it the way a user would (events, not internal calls), asserting the state-machine, persistence, and keyboard behaviors. It is a new sub-project, independent of the (complete, unmerged) `feat/practice-mode` branch, and changes **no production code**.

## Non-goals

- Not a replacement for the manual browser check. jsdom has no layout engine, so a documented set of behaviors stays browser-verified (see "Browser-only checklist").
- Not Playwright / a real browser. No browser binary, no separate test runner.
- No production-code refactor. The glue stays inline in `research.py`; the harness tests the rendered page as-is (extraction is unnecessary because jsdom exercises the whole page).
- Not a general page-object framework. A small, focused set of flows.

## What jsdom can and cannot cover

**Covered (asserted by the harness):** screen transitions (start→card→summary→again/done/return-to-setup), `localStorage` load/save + reload, live Start enable/disable, `renderStart(prefill)` restoration, focus *targets* (`.focus()`/`document.activeElement` work in jsdom — including the disabled-Start→BODY bug), grade shortcuts `1/2/3`, and the save-failure notice.

**NOT covered — stays on the browser-only checklist:**
- **Native Space/Enter activation of buttons.** jsdom's event system only runs activation behavior for real `click` events, not for a dispatched `keydown` Space. So "Space actually closes Exit" cannot be asserted in jsdom. (We assert the *interception guard* a different way — see keyboard flow.)
- **Tab focus-trap cycling.** The trap filters candidates with `el.offsetParent !== null`; jsdom has no layout, so `offsetParent` is always null. Trap cycling is browser-only.
- **`inert` semantics.** jsdom does not implement `inert`; that the background is truly non-interactive is browser-only.

## Architecture

```
node --test jeopardy/tests/browser/
        │
        ├─ (once per test file, in a before() hook)
        │     spawn: uv run --frozen --group analysis python -m jeopardy.tests.browser.render_fixture
        │       cwd = resolved repo root (from import.meta.url), NOT the caller's cwd
        │       stdout = a small self-contained research page (fixed fixture DATA)
        │
        └─ (per test) makeDom(html, {seedStorage?, quota?})
              new JSDOM(html, { runScripts: "dangerously", url: "https://practice.test/",
                                storageQuota?, beforeParse(win){ install clock+RNG+seed } })
              → drive UI via events → assert DOM/activeElement/localStorage → dom.window.close()
```

The glue lives only in `research.py`'s template, so the harness renders through the **real Python generator** to test the real thing — no committed generated fixture to drift.

## Components & file structure

- **`jeopardy/tests/browser/__init__.py`** *(new)* — package marker so `python -m jeopardy.tests.browser.render_fixture` resolves (`jeopardy/__init__.py` and `jeopardy/tests/__init__.py` already exist).
- **`jeopardy/tests/browser/render_fixture.py`** *(new)* — builds the fixed fixture as small pandas DataFrames, calls the real `build_research_data(...)` then `render_html(...)`, and prints the HTML to stdout. Importable/runnable as a module (dir-independent). No new Python deps, but it imports `research.py` (→ pandas), so it must run under the **analysis** group: `uv run --frozen --group analysis python -m jeopardy.tests.browser.render_fixture`.
- **`jeopardy/tests/browser/harness.js`** *(new, ESM)* — `makeDom(html, opts)` helper: constructs the JSDOM with `runScripts:"dangerously"`, a fixed `url`, optional `storageQuota`, and a `beforeParse` that installs a fixed clock, a fixed RNG, and (optionally) seeded `localStorage` **before** page scripts run; wires error capture (see below) and returns `{ dom, window, document }`. Also small DOM-driver helpers (click by id, dispatch a key, read text).
- **`jeopardy/tests/browser/practice-ui.test.js`** *(new, ESM)* — the `node:test` suite: one `before()` renders the fixture HTML once; each test builds a fresh DOM, drives a flow, asserts, and closes the DOM.
- **`jeopardy/tests/browser/package.json`** *(new)* — `{ "private": true, "type": "module", "devDependencies": { "jsdom": "<pinned>" } }`. Scopes the JS dependency **and** `"type":"module"` to this directory only; the bare `node:test` files elsewhere are unaffected.
- **`jeopardy/tests/browser/package-lock.json`** *(new, committed)* — pins the exact jsdom (and transitive) versions for `npm ci`.
- **`.gitignore`** — add `jeopardy/tests/browser/node_modules/`.
- **`.github/workflows/test.yml`** *(new)* — CI (see below).

## The fixture (`render_fixture.py`)

Small but **two topics**, so "selection preserved" and "reset to all" are distinguishable, and rich enough to exercise the era filter and dedup:

- **Two clusters/topics**, both labelable and present in the current era's `byEra` (default era 2010): e.g. `Topic A` (cluster 1) and `Topic B` (cluster 2), each with at least one recurring entity.
- **`Topic A` deck** (the one the tests select): ~5–6 **distinct** eligible clue ids after era-filtering and dedup, including:
  - **A clue outside the selected era** (year < 2010) — must be excluded from the pool when era = 2010.
  - **A clue id referenced more than once** across quiz keys (e.g. in both the general pool `""` and a per-entity key) — must be **deduped** to a single deck card.
- **`Topic B` deck** — a couple of distinct ids of its own, so selecting only Topic A and later "reset to all" yields observably different topic sets.
- Every referenced clue id present in the clues store with `{clue, answer, year, category, game_id}` and stable, known ids so tests can assert specific cards.

Fixed, known data → deterministic decks (combined with the injected clock/RNG).

## Determinism & jsdom setup (`harness.js`)

- **`runScripts: "dangerously"`** — required to execute the trusted, self-generated page's inline scripts.
- **Fixed `url`** (e.g. `https://practice.test/`) — gives the window a working `localStorage` origin.
- **`beforeParse(window)`** installs, before any page script runs:
  - `window.Date.now = () => FIXED_MS` (a constant) so all due-date math is reproducible.
  - `window.Math.random = () => 0` (or a fixed short sequence) so `assembleSession`'s shuffle is deterministic.
  - When a test needs pre-existing progress (the reload test), seed `window.localStorage.setItem('jeopardy-practice-v1', <json>)` here.
- **`storageQuota: 0`** (save-failure test only) — makes a real `setItem` throw a genuine `QuotaExceededError`, so we test the actual failure path with **no monkey-patching** of storage methods.
- **Error capture:** attach a `virtualConsole` that fails the test on `jsdomError`, and register `window` `error` / `unhandledrejection` listeners that collect exceptions; any **unexpected** page-script error fails the test rather than merely printing to stderr.
- **Lifecycle:** a **fresh JSDOM per test**; call `dom.window.close()` in an `afterEach`/`finally` to release timers and listeners.

## Flows asserted

Each test builds a fresh DOM from the shared fixture HTML, then:

1. **Full small-deck session (single topic, size override).** Open Practice; deselect `Topic B`, keep `Topic A`; choose **10** (overriding the default 20). Start. For each card: click **Reveal**, assert the answer + J-Archive link appear, click a grade (**Knew it**). At the end assert the summary shows the correct tally (`N knew · 0 · 0`), the "N scheduled to come back later" count, and that `document.activeElement` is **Practice again**. Also assert the deck honored the single-topic selection, the era filter (the pre-2010 clue never appeared), and dedup (the twice-referenced id appeared once).

2. **Missed card resurfaces (through the real DOM).** Start `Topic A`; grade the first card **Missed**; assert it reappears **after three intervening cards — or at the end when fewer than three remain** (matching `min(3, remaining)`). Miss it again on its retry; assert it is **not** re-queued (one retry per card) and the session ends.

3. **Persistence across reload.** Run a session grading some cards **Missed**; read `window.localStorage`; build a **fresh JSDOM seeded with that storage** (via `beforeParse`); open Practice and Start the same topic; assert the previously-missed (now-due) cards surface first — i.e. save→load round-trips through `sanitizeStore`.

4. **No-due return to setup (the fixed bug).** With a tiny/exhausted deck, click **Practice again** when nothing is due; assert `renderStart` **preserved** the earlier selection (only `Topic A` checked, size 10 — *not* reset to all/20), **Start is disabled**, and `document.activeElement` is the **Extra-practice checkbox** (`#pextra`), i.e. focus stayed inside the dialog rather than falling to BODY. For the note, assert the **actual disabled-state message** — `"Nothing due — turn on Extra practice, or widen your era / topics."` — *not* the `renderStart` prefill note (`"Nothing left due…"`), which `updateStartAvailability()` immediately overwrites when nothing is due. (Assert the message text or its meaning; the prefill note being dead in this path is a known, harmless practice-mode quirk, not something this harness fixes.)

5. **Keyboard — interception guard (narrowed per jsdom's limits).**
   - Focus the **Exit** button; dispatch a **bubbling, cancelable** `keydown` Space `KeyboardEvent`; assert `event.defaultPrevented === false` **and** the answer stays hidden. (The pre-fix handler would have `preventDefault`ed and revealed — this catches that regression. jsdom won't natively *activate* Exit via Space, so "Space closes Exit" is browser-only.)
   - After a **Reveal**, dispatch `keydown` `1`/`2`/`3` and assert the card is graded and the session advances (these are custom handlers, not native activation, so jsdom runs them).
   - Assert **clicking** Exit closes Practice and restores focus to the Practice button (via `click`, which jsdom activates).

6. **Save-failure notice.** Build the DOM with `storageQuota: 0`; run a grade; assert the "Progress isn't being saved" notice becomes visible **and** grading still advances (session continues from the in-memory store).

## Browser-only checklist (documented, not automated)

Recorded in the harness (a comment/README header) and in the practice-mode plan's manual step: real **Space/Enter activation** of Exit/Reveal/grade buttons; **Tab focus-trap** cycling; **`inert`** background non-interactivity; visual focus rings and reduced-motion.

## CI

Today `.github/workflows/publish.yml` runs `uv sync` + `quarto render` + deploy on push to `main`; there is **no test step** (not even pytest). Add a dedicated **`.github/workflows/test.yml`**:

- **Triggers:** `push` (all branches), `pull_request`, and `workflow_dispatch`.
- **Job `test`** on `ubuntu-latest`:
  1. `actions/checkout@v4`
  2. `astral-sh/setup-uv@v6`; `uv sync --frozen`
  3. `actions/setup-node@v4` with an **explicit Node version** compatible with the pinned jsdom (Node 22 LTS).
  4. `uv run --frozen --group scraper --group analysis python -m pytest jeopardy/tests -q` — the Python suite (currently unguarded in CI). Both groups are required: `analysis` for pandas/sklearn and `scraper` for the crawl/fetch test dependencies.
  5. `node --test jeopardy/analysis/practice.test.js` — the pure-scheduler suite.
  6. `npm ci --prefix jeopardy/tests/browser` then `node --test jeopardy/tests/browser/` — the jsdom harness (the harness's `before()` shells `uv run --frozen --group analysis python -m jeopardy.tests.browser.render_fixture`, so uv/Python from step 2 must be available).

This runs the full test matrix on every push, so regressions show red before a merge. `publish.yml` stays as-is (deploy on `main`). *Optional hardening (flagged, not included by default):* gate deploy on tests by moving the test job into `publish.yml` with `build: needs: test` — only worth it if you want a red test to block deployment.

## Testing the harness itself

The harness *is* the test. Its own correctness is established by: the six flows above passing against the current (fixed) code, and — as a sanity check during implementation — confirming at least one flow **fails** when run against the pre-fix code (e.g. flow 4 against the disabled-Start-focus bug, flow 5 against the old Space-interception handler). No meta-tests beyond that.

## Resolved decisions

1. **Tool:** ✅ jsdom (one dir-scoped devDependency), not Playwright. Accepted limits documented above.
2. **Page acquisition:** ✅ render at test time via `uv run --frozen --group analysis python -m jeopardy.tests.browser.render_fixture` (drift-proof), rendered once per file and reused across fresh DOMs.
3. **Determinism:** ✅ fixed clock + fixed RNG installed in `beforeParse`; fixed two-topic fixture.
4. **Keyboard scope:** ✅ assert the interception guard (`defaultPrevented===false` + answer hidden) and `1/2/3` grading in jsdom; real Space→Exit activation is browser-only.
5. **Save-failure:** ✅ `storageQuota: 0` (real quota exception), no storage monkey-patching.
6. **CI:** ✅ new `test.yml` (push/PR/dispatch) running pytest + both Node suites, with a committed `package-lock.json` and a pinned Node version; deploy-gating left optional.

## Out of scope / future

- Playwright layer for the browser-only checklist (trap, inert, native key activation).
- Extending the harness to other interactive pages.
