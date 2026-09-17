# Practice Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a client-side, spaced-repetition Practice mode to the Jeopardy research page — pick topics, grade real clues Knew it / Unsure / Missed, missed cards resurface once per session, progress persists in localStorage.

**Architecture:** A new pure, DOM-free ES module (`jeopardy/analysis/practice.js`) holds all scheduling and session-queue logic, unit-tested with `node:test`. `research.py`'s `render_html` inlines that module (stripping its `export` line) via a `__PRACTICE_JS__` placeholder, then the page's existing inline IIFE gains the Practice button, a modal overlay, and the DOM/localStorage glue that calls the pure functions. `build_research_data` is unchanged — Practice reuses the already-embedded `DATA.clues` / `DATA.quiz` / `DATA.byEra`.

**Tech Stack:** Python (offline build), pandas; vanilla browser JS (ES2020) inlined in a self-contained HTML string; `node:test` for JS units; `pytest` for the Python injection test.

## Global Constraints

- **Pure module style:** `jeopardy/analysis/practice.js` uses only plain `function`/`const` declarations plus a single trailing `export { ... };`. No inline `export`, no `import`, no top-level side effects.
- **Purity:** pure functions take `now` and `rng` as parameters — never call `Date.now()` or `Math.random()` internally, and never touch the DOM or localStorage.
- **Export stripping:** `render_html` inlines the module with every line whose trimmed text starts with `export ` removed, so declarations become page-level globals.
- **localStorage key is exactly** `jeopardy-practice-v1`; stored shape is `{ v: 1, cards: { "<clue_id>": { box, due, seen } } }`.
- **Boxes** are integers `0..4`; `INTERVAL_DAYS = [0, 1, 3, 7, 21]` (days); `DAY_MS = 86400000`.
- **No new Python dependencies**, no new parquet, `build_research_data` signature and output unchanged.
- **Reuse existing page helpers** `escapeHtml` and `clueById` and the existing CSS custom properties (`--gold`, `--panel`, `--ink`, `--ash`, `--line`, `--radius`, etc.). Do not redefine them.
- **JS tests run with:** `node --test jeopardy/analysis/practice.test.js`
- **Python tests run with:** `uv run --group analysis pytest jeopardy/tests/test_research.py -q`
- **Commit trailer** on every commit:
  ```
  Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
  ```

---

### Task 1: Scheduling core (`nextBox`, `dueAfter`, `applyGrade`)

**Files:**
- Create: `jeopardy/analysis/practice.js`
- Create (Test): `jeopardy/analysis/practice.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `INTERVAL_DAYS: number[]` — `[0, 1, 3, 7, 21]`
  - `nextBox(box: int, grade: 'knew'|'unsure'|'missed') -> int`
  - `dueAfter(now: ms, box: int) -> ms` = `now + INTERVAL_DAYS[box] * 86400000`
  - `applyGrade(card: {box,due,seen}|null, grade, now: ms, promote: bool) -> {box, due, seen}`
    - `card === null` means an unseen card (box 0).
    - `promote === true` (normal): miss→box 0; knew→min(4,box+1); unsure→box unchanged; then `due = dueAfter(now, newBox)`.
    - `promote === false` (extra practice): miss→`{box:0, due:now, seen:now}`; knew/unsure→box and due **unchanged**, `seen = now`.

- [ ] **Step 1: Write the failing test**

Create `jeopardy/analysis/practice.test.js`:

```js
import { test } from "node:test";
import assert from "node:assert/strict";
import { INTERVAL_DAYS, nextBox, dueAfter, applyGrade } from "./practice.js";

const DAY = 86400000;

test("nextBox promotes, clamps at 4, resets on miss, holds on unsure", () => {
  assert.equal(nextBox(0, "knew"), 1);
  assert.equal(nextBox(4, "knew"), 4);
  assert.equal(nextBox(2, "unsure"), 2);
  assert.equal(nextBox(3, "missed"), 0);
});

test("dueAfter uses INTERVAL_DAYS per box", () => {
  assert.deepEqual(INTERVAL_DAYS, [0, 1, 3, 7, 21]);
  assert.equal(dueAfter(1000, 0), 1000);
  assert.equal(dueAfter(1000, 1), 1000 + 1 * DAY);
  assert.equal(dueAfter(1000, 4), 1000 + 21 * DAY);
});

test("applyGrade normal: new card knew -> box1 due tomorrow", () => {
  assert.deepEqual(applyGrade(null, "knew", 1000, true), { box: 1, due: 1000 + DAY, seen: 1000 });
});

test("applyGrade normal: unsure holds box, miss resets to box0 due now", () => {
  assert.deepEqual(applyGrade({ box: 2, due: 5, seen: 5 }, "unsure", 1000, true), { box: 2, due: 1000 + 3 * DAY, seen: 1000 });
  assert.deepEqual(applyGrade({ box: 3, due: 5, seen: 5 }, "missed", 1000, true), { box: 0, due: 1000, seen: 1000 });
});

test("applyGrade extra: correct leaves box+due unchanged, updates seen", () => {
  assert.deepEqual(applyGrade({ box: 3, due: 777, seen: 1 }, "knew", 1000, false), { box: 3, due: 777, seen: 1000 });
  assert.deepEqual(applyGrade({ box: 2, due: 888, seen: 1 }, "unsure", 1000, false), { box: 2, due: 888, seen: 1000 });
});

test("applyGrade extra: miss still resets", () => {
  assert.deepEqual(applyGrade({ box: 4, due: 999, seen: 1 }, "missed", 1000, false), { box: 0, due: 1000, seen: 1000 });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test jeopardy/analysis/practice.test.js`
Expected: FAIL — `Cannot find module .../practice.js` (file does not exist yet).

- [ ] **Step 3: Write minimal implementation**

Create `jeopardy/analysis/practice.js`:

```js
// Pure, DOM-free spaced-repetition scheduler + session queue for the research page's
// Practice mode. No imports, no Date.now()/Math.random() inside — time and rng are
// passed in. The single trailing `export { ... }` is stripped when inlined into the page.

const INTERVAL_DAYS = [0, 1, 3, 7, 21];
const DAY_MS = 86400000;

function nextBox(box, grade) {
  if (grade === "missed") return 0;
  if (grade === "knew") return Math.min(4, box + 1);
  return box; // 'unsure' holds
}

function dueAfter(now, box) {
  return now + INTERVAL_DAYS[box] * DAY_MS;
}

function applyGrade(card, grade, now, promote) {
  const box = card ? card.box : 0;
  if (!promote) {
    if (grade === "missed") return { box: 0, due: now, seen: now };
    return { box, due: card ? card.due : dueAfter(now, box), seen: now };
  }
  const nb = nextBox(box, grade);
  return { box: nb, due: dueAfter(now, nb), seen: now };
}

export { INTERVAL_DAYS, nextBox, dueAfter, applyGrade };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test jeopardy/analysis/practice.test.js`
Expected: PASS — 6 tests pass.

- [ ] **Step 5: Commit**

```bash
git add jeopardy/analysis/practice.js jeopardy/analysis/practice.test.js
git commit -m "feat: practice scheduler core (box transitions + due dates)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Session assembly (`assembleSession`)

**Files:**
- Modify: `jeopardy/analysis/practice.js`
- Modify (Test): `jeopardy/analysis/practice.test.js`

**Interfaces:**
- Consumes: nothing from Task 1 (same file, independent function).
- Produces:
  - `assembleSession(pool: id[], store: {[id]:{box,due,seen}}, now: ms, size: int, extra: bool, rng: ()->[0,1)) -> id[]`
    - Partitions `pool` into **due** (`store[id].due <= now`), **unseen** (`id` not in `store`), **future** (rest).
    - Due sorted by `due` asc; unseen shuffled by `rng` (Fisher–Yates); future sorted by `due` asc.
    - Order = `extra ? [due, unseen, future] : [due, unseen]`, truncated to `size`.
    - `pool` is assumed distinct (the caller dedupes).

- [ ] **Step 1: Write the failing test**

Append to `jeopardy/analysis/practice.test.js`:

```js
import { assembleSession } from "./practice.js";

test("assembleSession: due before unseen, future excluded when not extra", () => {
  const store = { a: { box: 0, due: 500, seen: 1 }, b: { box: 1, due: 2000, seen: 1 } };
  const ids = assembleSession(["a", "b", "c", "d"], store, 1000, 10, false, () => 0);
  assert.equal(ids[0], "a");            // due first
  assert.ok(!ids.includes("b"));        // future excluded when extra=false
  assert.deepEqual(ids.slice(1).sort(), ["c", "d"]); // unseen included
});

test("assembleSession: future tier included only when extra", () => {
  const store = { b: { box: 1, due: 2000, seen: 1 } };
  assert.deepEqual(assembleSession(["b"], store, 1000, 10, true, () => 0), ["b"]);
});

test("assembleSession: truncates to size", () => {
  assert.equal(assembleSession(["a", "b", "c", "d", "e"], {}, 1000, 3, false, () => 0).length, 3);
});

test("assembleSession: shuffles unseen deterministically via rng", () => {
  // rng()===0 -> Fisher-Yates swaps each i with index 0: ["a","b","c"] -> ["b","c","a"]
  assert.deepEqual(assembleSession(["a", "b", "c"], {}, 1000, 3, false, () => 0), ["b", "c", "a"]);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test jeopardy/analysis/practice.test.js`
Expected: FAIL — `assembleSession` is not exported.

- [ ] **Step 3: Write minimal implementation**

In `jeopardy/analysis/practice.js`, add before the `export` line:

```js
function _shuffle(arr, rng) {
  for (let i = arr.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    const tmp = arr[i];
    arr[i] = arr[j];
    arr[j] = tmp;
  }
  return arr;
}

function assembleSession(pool, store, now, size, extra, rng) {
  const due = [], unseen = [], future = [];
  for (const id of pool) {
    const rec = store[id];
    if (!rec) unseen.push(id);
    else if (rec.due <= now) due.push(id);
    else future.push(id);
  }
  due.sort((x, y) => store[x].due - store[y].due);
  _shuffle(unseen, rng);
  future.sort((x, y) => store[x].due - store[y].due);
  const ordered = extra ? due.concat(unseen, future) : due.concat(unseen);
  return ordered.slice(0, size);
}
```

Update the export line to:

```js
export { INTERVAL_DAYS, nextBox, dueAfter, applyGrade, assembleSession };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test jeopardy/analysis/practice.test.js`
Expected: PASS — 10 tests pass.

- [ ] **Step 5: Commit**

```bash
git add jeopardy/analysis/practice.js jeopardy/analysis/practice.test.js
git commit -m "feat: practice session assembly (due/unseen/future tiers)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Session queue with finite retries (`initSession`, `gradeCurrent`, `sessionProgress`)

**Files:**
- Modify: `jeopardy/analysis/practice.js`
- Modify (Test): `jeopardy/analysis/practice.test.js`

**Interfaces:**
- Consumes: nothing (same file).
- Produces:
  - `initSession(ids: id[]) -> { queue: [{id, retried:false}], size: int }` (`size` = `ids.length`).
  - `gradeCurrent(session, grade) -> session'` — returns a **new** session; pops `queue[0]`; if `grade === 'missed'` and the popped entry's `retried` is false, re-inserts `{id, retried:true}` at index `min(3, remainingLength)`; otherwise drops it. Guarantees at most one retry per id.
  - `sessionProgress(session) -> { done, size, retriesPending }` where `done = size − (distinct ids still in queue)`, `retriesPending = count of queue entries with retried===true`.

- [ ] **Step 1: Write the failing test**

Append to `jeopardy/analysis/practice.test.js`:

```js
import { initSession, gradeCurrent, sessionProgress } from "./practice.js";

test("gradeCurrent drops a card on a non-missed grade", () => {
  let s = initSession(["a", "b"]);
  s = gradeCurrent(s, "knew");
  assert.deepEqual(s.queue.map(e => e.id), ["b"]);
  assert.deepEqual(sessionProgress(s), { done: 1, size: 2, retriesPending: 0 });
});

test("gradeCurrent requeues a first miss once at min(3, remaining)", () => {
  let s = initSession(["a", "b", "c", "d", "e"]);
  s = gradeCurrent(s, "missed"); // pop a; 4 remain; insert at index 3
  assert.deepEqual(s.queue.map(e => e.id), ["b", "c", "d", "a", "e"]);
  assert.equal(s.queue.find(e => e.id === "a").retried, true);
  assert.deepEqual(sessionProgress(s), { done: 0, size: 5, retriesPending: 1 });
});

test("a second miss of the same card does not requeue (finite retries)", () => {
  let s = initSession(["a"]);
  s = gradeCurrent(s, "missed");                 // -> [a(retried)]
  assert.deepEqual(s.queue.map(e => e.id), ["a"]);
  assert.deepEqual(sessionProgress(s), { done: 0, size: 1, retriesPending: 1 });
  s = gradeCurrent(s, "missed");                 // already retried -> dropped
  assert.deepEqual(s.queue, []);
  assert.deepEqual(sessionProgress(s), { done: 1, size: 1, retriesPending: 0 });
});

test("missing the final card yields exactly one retry", () => {
  let s = initSession(["a", "b"]);
  s = gradeCurrent(s, "knew");                   // -> [b]
  s = gradeCurrent(s, "missed");                 // pop b; 0 remain; insert at index 0
  assert.deepEqual(s.queue.map(e => e.id), ["b"]);
  s = gradeCurrent(s, "missed");                 // retried -> dropped, session ends
  assert.deepEqual(s.queue, []);
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test jeopardy/analysis/practice.test.js`
Expected: FAIL — `initSession` is not exported.

- [ ] **Step 3: Write minimal implementation**

In `jeopardy/analysis/practice.js`, add before the `export` line:

```js
function initSession(ids) {
  return { queue: ids.map(id => ({ id, retried: false })), size: ids.length };
}

function gradeCurrent(session, grade) {
  const queue = session.queue.slice();
  const cur = queue.shift();
  if (cur && grade === "missed" && !cur.retried) {
    const pos = Math.min(3, queue.length);
    queue.splice(pos, 0, { id: cur.id, retried: true });
  }
  return { queue, size: session.size };
}

function sessionProgress(session) {
  const remaining = new Set(session.queue.map(e => e.id));
  const retriesPending = session.queue.filter(e => e.retried).length;
  return { done: session.size - remaining.size, size: session.size, retriesPending };
}
```

Update the export line to:

```js
export { INTERVAL_DAYS, nextBox, dueAfter, applyGrade, assembleSession, initSession, gradeCurrent, sessionProgress };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test jeopardy/analysis/practice.test.js`
Expected: PASS — 14 tests pass.

- [ ] **Step 5: Commit**

```bash
git add jeopardy/analysis/practice.js jeopardy/analysis/practice.test.js
git commit -m "feat: practice session queue with one-retry-per-card

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Persistence validator (`sanitizeStore`)

**Files:**
- Modify: `jeopardy/analysis/practice.js`
- Modify (Test): `jeopardy/analysis/practice.test.js`

**Interfaces:**
- Consumes: nothing (same file).
- Produces:
  - `sanitizeStore(parsed: any) -> { v: 1, cards: { [id]: {box,due,seen} } }` — returns an empty store unless `parsed.v === 1` and `parsed.cards` is a non-null object; keeps only records where `box` is an integer in `0..4` and `due`/`seen` are finite numbers.

- [ ] **Step 1: Write the failing test**

Append to `jeopardy/analysis/practice.test.js`:

```js
import { sanitizeStore } from "./practice.js";

test("sanitizeStore returns empty on wrong/missing version or bad shape", () => {
  assert.deepEqual(sanitizeStore(null), { v: 1, cards: {} });
  assert.deepEqual(sanitizeStore({ v: 2, cards: { a: { box: 0, due: 1, seen: 1 } } }), { v: 1, cards: {} });
  assert.deepEqual(sanitizeStore({ cards: {} }), { v: 1, cards: {} });
  assert.deepEqual(sanitizeStore({ v: 1, cards: null }), { v: 1, cards: {} });
});

test("sanitizeStore drops invalid records, keeps valid ones", () => {
  const parsed = { v: 1, cards: {
    good: { box: 2, due: 100, seen: 50 },
    badBox: { box: 9, due: 100, seen: 50 },
    floatBox: { box: 1.5, due: 100, seen: 50 },
    nanDue: { box: 0, due: NaN, seen: 50 },
    infSeen: { box: 0, due: 100, seen: Infinity },
    notObj: 5,
  } };
  assert.deepEqual(sanitizeStore(parsed), { v: 1, cards: { good: { box: 2, due: 100, seen: 50 } } });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test jeopardy/analysis/practice.test.js`
Expected: FAIL — `sanitizeStore` is not exported.

- [ ] **Step 3: Write minimal implementation**

In `jeopardy/analysis/practice.js`, add before the `export` line:

```js
function sanitizeStore(parsed) {
  if (!parsed || parsed.v !== 1 || typeof parsed.cards !== "object" || parsed.cards === null) {
    return { v: 1, cards: {} };
  }
  const cards = {};
  for (const id in parsed.cards) {
    const c = parsed.cards[id];
    if (!c || typeof c !== "object") continue;
    if (!Number.isInteger(c.box) || c.box < 0 || c.box > 4) continue;
    if (!Number.isFinite(c.due) || !Number.isFinite(c.seen)) continue;
    cards[id] = { box: c.box, due: c.due, seen: c.seen };
  }
  return { v: 1, cards };
}
```

Update the export line to:

```js
export { INTERVAL_DAYS, nextBox, dueAfter, applyGrade, assembleSession, initSession, gradeCurrent, sessionProgress, sanitizeStore };
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test jeopardy/analysis/practice.test.js`
Expected: PASS — 16 tests pass.

- [ ] **Step 5: Commit**

```bash
git add jeopardy/analysis/practice.js jeopardy/analysis/practice.test.js
git commit -m "feat: practice store validator (sanitizeStore)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Inject the module into `render_html`

**Files:**
- Modify: `jeopardy/analysis/research.py` (`render_html`, and add a helper + template placeholder)
- Modify (Test): `jeopardy/tests/test_research.py`

**Interfaces:**
- Consumes: `jeopardy/analysis/practice.js` (from Tasks 1–4).
- Produces: `render_html(data)` inlines the practice module at the `__PRACTICE_JS__` placeholder with `export` lines stripped. The functions `assembleSession`, `applyGrade`, `initSession`, `gradeCurrent`, `sessionProgress`, `sanitizeStore` are available as globals in the page. No literal `__PRACTICE_JS__` remains.

- [ ] **Step 1: Write the failing test**

Append to `jeopardy/tests/test_research.py`:

```python
def test_render_html_injects_practice_module():
    data = build_research_data(_tokens_df(), _eras_df(), _labels())
    html = render_html(data)
    assert "__PRACTICE_JS__" not in html          # placeholder replaced
    assert "function assembleSession" in html      # module inlined
    assert "function sanitizeStore" in html
    assert "\nexport {" not in html                # ES-module export line stripped
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --group analysis pytest jeopardy/tests/test_research.py::test_render_html_injects_practice_module -q`
Expected: FAIL — `__PRACTICE_JS__` is still present (no placeholder in template yet) / module not inlined.

- [ ] **Step 3: Add the placeholder to the template**

In `jeopardy/analysis/research.py`, inside `_HTML_TEMPLATE`, add a script tag holding the module immediately before the existing `<script>` that defines `const DATA`. Find:

```html
  <script>
    const DATA = __DATA_JSON__;
```

Replace with:

```html
  <script>__PRACTICE_JS__</script>
  <script>
    const DATA = __DATA_JSON__;
```

- [ ] **Step 4: Add the injection helper and update `render_html`**

In `jeopardy/analysis/research.py`, add near the top (after the existing imports):

```python
from pathlib import Path

_PRACTICE_JS_PATH = Path(__file__).resolve().parent / "practice.js"


def _practice_js() -> str:
    src = _PRACTICE_JS_PATH.read_text(encoding="utf-8")
    # Strip ES-module export lines so the declarations inline as page-level globals.
    return "\n".join(ln for ln in src.splitlines() if not ln.lstrip().startswith("export "))
```

Replace the existing `render_html`:

```python
def render_html(data: dict) -> str:
    """Render the self-contained research page with `data` embedded as JSON."""
    payload = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
    html = _HTML_TEMPLATE.replace("__PRACTICE_JS__", _practice_js())
    return html.replace("__DATA_JSON__", payload)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --group analysis pytest jeopardy/tests/test_research.py::test_render_html_injects_practice_module -q`
Expected: PASS.

- [ ] **Step 6: Run the full research test file (no regressions)**

Run: `uv run --group analysis pytest jeopardy/tests/test_research.py -q`
Expected: PASS — all existing tests plus the new one.

- [ ] **Step 7: Commit**

```bash
git add jeopardy/analysis/research.py jeopardy/tests/test_research.py
git commit -m "feat: inline practice.js module into research page

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Practice overlay shell, era-bar button, CSS, and Start screen

**Files:**
- Modify: `jeopardy/analysis/research.py` (CSS block, era-bar HTML, overlay HTML, inline JS glue)
- Modify (Test): `jeopardy/tests/test_research.py`

**Interfaces:**
- Consumes: page globals `assembleSession`, `sanitizeStore` (Task 2, 4); existing page helpers `escapeHtml`, `clueById`, and the module-scope `currentEra`, `DATA`.
- Produces (inside the existing IIFE, used by Task 7):
  - `practice` state object; `overlay`, `pBody`, `pProgress`, `pTally`, `pNotice` element refs.
  - `loadStore()`, `saveCard(id, rec)`, `resetProgress()`, `practicePool(clusterIds, era)`.
  - `openPractice()`, `closePractice()`, `practiceKeys(e)` (Escape + focus-trap; the card-screen shortcuts are added in Task 7), `renderStart()`, `startSession()`.
  - `startSession()` calls `nextCard()` (defined in Task 7). This task provides a temporary `nextCard` stub so Start is testable in isolation; Task 7 replaces it.

- [ ] **Step 1: Write the failing test**

Append to `jeopardy/tests/test_research.py`:

```python
def test_render_html_has_practice_entry_and_start_screen():
    data = build_research_data(_tokens_df(), _eras_df(), _labels())
    html = render_html(data)
    for marker in [
        'id="practice-open"', 'id="practice"', 'aria-modal="true"',
        'openPractice', 'closePractice', 'renderStart', 'startSession',
        'practicePool', 'id="pextra"', 'name="psize"', 'practice-reset',
    ]:
        assert marker in html, marker
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --group analysis pytest jeopardy/tests/test_research.py::test_render_html_has_practice_entry_and_start_screen -q`
Expected: FAIL — markers absent.

- [ ] **Step 3: Add the Practice CSS block**

In `jeopardy/analysis/research.py`, inside `<style>`, immediately before the closing `</style>` line, add:

```css
  .practice-open {
    margin-left: auto;
    font-family: var(--mono); font-size: 12.5px; letter-spacing: 0.03em;
    background: var(--gold); border: 1px solid var(--gold); color: var(--ink);
    font-weight: 600; border-radius: var(--radius); padding: 6px 16px; cursor: pointer;
  }
  .practice-open:hover { background: var(--paper); border-color: var(--paper); }
  .practice-overlay {
    position: fixed; inset: 0; z-index: 50; background: rgba(6, 12, 38, 0.96);
    display: flex; align-items: flex-start; justify-content: center; overflow-y: auto;
  }
  .practice-overlay[hidden] { display: none; }
  .practice-inner {
    width: min(680px, 100%); margin: clamp(16px, 5vh, 64px) 16px;
    background: var(--panel); border: 1px solid var(--line); border-radius: var(--radius);
    padding: clamp(18px, 3vw, 30px);
  }
  .practice-head { display: flex; align-items: center; gap: 14px; margin-bottom: 18px; }
  .practice-exit {
    font-family: var(--mono); font-size: 12px; text-transform: uppercase; letter-spacing: 0.04em;
    background: var(--panel-2); border: 1px solid var(--line); color: var(--ash);
    border-radius: var(--radius); padding: 6px 12px; cursor: pointer;
  }
  .practice-exit:hover { color: var(--paper); border-color: var(--gold-dim); }
  .practice-progress { font-family: var(--mono); font-size: 12px; color: var(--ash); }
  .practice-tally { font-family: var(--mono); font-size: 12px; color: var(--gold); margin-left: auto; }
  .practice-notice {
    margin-bottom: 14px; padding: 8px 12px; border: 1px solid var(--brick);
    border-radius: var(--radius); color: var(--brick); font-size: 13px;
  }
  .practice-title { font-family: var(--display); text-transform: uppercase; letter-spacing: 0.03em; font-size: 26px; margin: 0 0 6px; }
  .practice-sub { color: var(--ash); font-family: var(--mono); font-size: 12px; margin: 0 0 18px; }
  .practice-topics { display: flex; flex-direction: column; gap: 4px; max-height: 40vh; overflow-y: auto; margin-bottom: 18px; }
  .ptopic { font-size: 14px; cursor: pointer; }
  .practice-opts { display: flex; align-items: center; gap: 14px; margin-bottom: 14px; font-size: 14px; }
  .popt-label { font-family: var(--mono); font-size: 11px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--ash); }
  .pextra { display: block; font-size: 14px; margin-bottom: 18px; cursor: pointer; }
  .pextra-note { color: var(--ash); font-size: 12px; }
  .practice-actions { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
  .practice-start {
    font-family: var(--mono); font-size: 13px; letter-spacing: 0.04em; text-transform: uppercase;
    background: var(--gold); border: 1px solid var(--gold); color: var(--ink); font-weight: 600;
    border-radius: var(--radius); padding: 9px 18px; cursor: pointer;
  }
  .practice-start:hover { background: var(--paper); border-color: var(--paper); }
  .practice-startnote { color: var(--brick); font-size: 13px; }
  .practice-reset {
    font-family: var(--mono); font-size: 11px; text-transform: uppercase; letter-spacing: 0.04em;
    background: transparent; border: 1px solid var(--line); color: var(--ash);
    border-radius: var(--radius); padding: 6px 12px; cursor: pointer;
  }
  .practice-reset:hover { color: var(--brick); border-color: var(--brick); }
  .pcard-scope { font-family: var(--mono); font-size: 11px; color: var(--ash); margin: 0 0 10px; }
  .pcard-clue { font-size: 18px; line-height: 1.5; margin: 0 0 18px; }
  .pcard-answer { font-size: 16px; color: var(--gold); margin: 0 0 16px; }
  .pcard-grades { display: flex; gap: 10px; flex-wrap: wrap; }
  .pgrade {
    font-size: 14px; background: var(--panel-2); border: 1px solid var(--line); color: var(--paper);
    border-radius: var(--radius); padding: 10px 16px; cursor: pointer;
  }
  .pgrade:hover { border-color: var(--gold); }
  .pgrade span { font-family: var(--mono); font-size: 11px; color: var(--ash); margin-left: 6px; }
  .psummary-tally { font-size: 16px; margin: 0 0 8px; }
  .psummary-sched { color: var(--ash); font-size: 14px; margin: 0 0 18px; }
```

- [ ] **Step 4: Add the Practice button to the era bar**

Find in the template:

```html
  <div class="era-bar" role="group" aria-label="Study era">
    <span class="era-bar-label">Study window (cumulative)</span>
    <div id="era-toggle" class="era-toggle"></div>
  </div>
```

Replace with:

```html
  <div class="era-bar" role="group" aria-label="Study era">
    <span class="era-bar-label">Study window (cumulative)</span>
    <div id="era-toggle" class="era-toggle"></div>
    <button type="button" id="practice-open" class="practice-open">Practice &#9654;</button>
  </div>
```

- [ ] **Step 5: Add the overlay container**

Find the closing of the layout / the footer start:

```html
  <footer class="footer">
```

Insert immediately before it:

```html
  <div id="practice" class="practice-overlay" role="dialog" aria-modal="true" aria-label="Practice session" hidden>
    <div class="practice-inner">
      <header class="practice-head">
        <button type="button" id="practice-exit" class="practice-exit">Exit</button>
        <span id="practice-progress" class="practice-progress"></span>
        <span id="practice-tally" class="practice-tally"></span>
      </header>
      <div id="practice-notice" class="practice-notice" hidden></div>
      <div id="practice-body" class="practice-body"></div>
    </div>
  </div>
```

- [ ] **Step 6: Add the glue (shell + Start screen) inside the IIFE**

In the inline `<script>` IIFE, find the init block at the very end:

```js
      renderEraToggle();
      renderSide('');
      renderMain();
      renderDetailEmpty();
    })();
```

Insert the following **before** those four `render*()` init calls (so the functions are defined, then wired):

```js
      // ---- Practice mode ----
      const PKEY = 'jeopardy-practice-v1';
      const practice = {
        screen: 'start', config: null, store: { v: 1, cards: {} },
        session: null, current: null, revealed: false,
        tally: { knew: 0, unsure: 0, missed: 0 }, seen: new Set(),
        saveFailed: false, returnFocus: null,
      };
      const overlay = document.getElementById('practice');
      const pBody = document.getElementById('practice-body');
      const pProgress = document.getElementById('practice-progress');
      const pTally = document.getElementById('practice-tally');
      const pNotice = document.getElementById('practice-notice');
      const layoutEl = document.querySelector('.layout');

      // Task 7 replaces this stub with the real card loop.
      function nextCard() { /* replaced in Task 7 */ }

      function loadStore() {
        try { return sanitizeStore(JSON.parse(localStorage.getItem(PKEY))); }
        catch (e) { return { v: 1, cards: {} }; }
      }
      function saveCard(id, rec) {
        practice.store.cards[id] = rec;
        try { localStorage.setItem(PKEY, JSON.stringify(practice.store)); }
        catch (e) {
          practice.saveFailed = true;
          pNotice.textContent = "Progress isn't being saved (storage unavailable).";
          pNotice.hidden = false;
        }
      }
      function resetProgress() {
        try { localStorage.removeItem(PKEY); } catch (e) { /* ignore */ }
        practice.store = { v: 1, cards: {} };
      }
      function practicePool(clusterIds, era) {
        const ids = new Set();
        for (const cid of clusterIds) {
          const refs = (DATA.quiz && DATA.quiz[String(cid)]) || {};
          for (const key in refs) for (const id of refs[key]) ids.add(id);
        }
        const out = [];
        for (const id of ids) { const c = clueById(id); if (c && c.year >= era) out.push(id); }
        return out;
      }

      function renderStart() {
        practice.screen = 'start';
        pProgress.textContent = ''; pTally.textContent = '';
        const list = DATA.byEra[String(currentEra)] || [];
        const nameById = {};
        for (const d of list) nameById[d.cluster_id] = d.name;
        const clusters = Object.keys(DATA.quiz || {}).map(Number)
          .filter(cid => nameById[cid] !== undefined)
          .sort((a, b) => (nameById[a] || '').localeCompare(nameById[b] || ''));
        let html = '<h2 class="practice-title">Practice</h2>' +
          '<p class="practice-sub">Study window: ' +
          (currentEra === DATA.eras[0] ? 'All-time' : 'Since ' + currentEra) + '</p>' +
          '<div class="practice-topics" role="group" aria-label="Topics">' +
          '<label class="ptopic"><input type="checkbox" id="ptopic-all" checked> <b>Select all / none</b></label>';
        for (const cid of clusters) {
          html += '<label class="ptopic"><input type="checkbox" class="ptopic-cb" value="' + cid + '" checked> ' +
            escapeHtml(nameById[cid]) + '</label>';
        }
        html += '</div>' +
          '<div class="practice-opts"><span class="popt-label">Cards</span>' +
          '<label><input type="radio" name="psize" value="10"> 10</label>' +
          '<label><input type="radio" name="psize" value="20" checked> 20</label>' +
          '<label><input type="radio" name="psize" value="30"> 30</label></div>' +
          '<label class="pextra"><input type="checkbox" id="pextra"> Extra practice ' +
          '<span class="pextra-note">(drill everything; correct answers don\\'t change your schedule)</span></label>' +
          '<div class="practice-actions">' +
          '<button type="button" id="practice-start" class="practice-start">Start session</button>' +
          '<span id="practice-startnote" class="practice-startnote"></span></div>' +
          '<button type="button" id="practice-reset" class="practice-reset">Reset progress</button>';
        pBody.innerHTML = html;
        const all = document.getElementById('ptopic-all');
        const cbs = () => Array.from(pBody.querySelectorAll('.ptopic-cb'));
        all.addEventListener('change', () => { cbs().forEach(cb => { cb.checked = all.checked; }); });
        cbs().forEach(cb => cb.addEventListener('change', () => { all.checked = cbs().every(c => c.checked); }));
        document.getElementById('practice-start').addEventListener('click', startSession);
        document.getElementById('practice-reset').addEventListener('click', () => {
          if (window.confirm('Erase all saved practice progress?')) resetProgress();
        });
      }

      function startSession() {
        const cids = Array.from(pBody.querySelectorAll('.ptopic-cb')).filter(cb => cb.checked).map(cb => Number(cb.value));
        const sizeEl = pBody.querySelector('input[name=psize]:checked');
        const size = Number(sizeEl ? sizeEl.value : 20);
        const extra = document.getElementById('pextra').checked;
        const era = currentEra;
        const pool = practicePool(cids, era);
        const ids = assembleSession(pool, practice.store.cards, Date.now(), size, extra, Math.random);
        const note = document.getElementById('practice-startnote');
        if (!ids.length) {
          note.textContent = extra
            ? 'No clues match — widen your era or topics.'
            : 'Nothing due — turn on Extra practice, or widen your era / topics.';
          return;
        }
        practice.config = { clusterIds: cids, size, extra, era };
        practice.session = initSession(ids);
        practice.tally = { knew: 0, unsure: 0, missed: 0 };
        practice.seen = new Set();
        nextCard();
      }

      function trapTab(e) {
        if (e.key !== 'Tab') return;
        const items = Array.from(overlay.querySelectorAll('button, input, a[href], [tabindex]:not([tabindex="-1"])'))
          .filter(el => !el.disabled && el.offsetParent !== null);
        if (!items.length) return;
        const first = items[0], last = items[items.length - 1];
        if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
        else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
      }
      function practiceKeys(e) {
        if (e.key === 'Escape') { closePractice(); return; }
        trapTab(e);
        // Card-screen shortcuts (Space / 1-2-3) are added in Task 7.
      }
      function openPractice() {
        practice.returnFocus = document.activeElement;
        practice.store = loadStore();
        practice.saveFailed = false; pNotice.hidden = true;
        overlay.hidden = false;
        document.body.style.overflow = 'hidden';
        if (layoutEl) layoutEl.setAttribute('aria-hidden', 'true');
        renderStart();
        document.addEventListener('keydown', practiceKeys);
        const firstFocus = pBody.querySelector('input, button');
        if (firstFocus) firstFocus.focus();
      }
      function closePractice() {
        overlay.hidden = true;
        document.body.style.overflow = '';
        if (layoutEl) layoutEl.removeAttribute('aria-hidden');
        document.removeEventListener('keydown', practiceKeys);
        if (practice.returnFocus && practice.returnFocus.focus) practice.returnFocus.focus();
      }
      document.getElementById('practice-exit').addEventListener('click', closePractice);
      document.getElementById('practice-open').addEventListener('click', openPractice);

```

- [ ] **Step 7: Run the marker test and the full research file**

Run: `uv run --group analysis pytest jeopardy/tests/test_research.py -q`
Expected: PASS — the new `test_render_html_has_practice_entry_and_start_screen` and all existing tests.

- [ ] **Step 8: Manual browser check**

Run: `uv run --group analysis python -m jeopardy research` (regenerates `posts/jeopardy_ds/research/index.html`), open it, click **Practice**. Verify: overlay opens; topics listed with Select all/none working; size + Extra toggle present; Reset asks for confirm; Escape and Exit close and return focus to the Practice button; clicking Start with topics selected does not error (card screen is a stub until Task 7).

- [ ] **Step 9: Commit**

```bash
git add jeopardy/analysis/research.py jeopardy/tests/test_research.py
git commit -m "feat: practice overlay shell, era-bar entry, start screen

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Card loop, grading/persistence wiring, summary, keyboard shortcuts

**Files:**
- Modify: `jeopardy/analysis/research.py` (replace the `nextCard` stub; add `renderCard`, `reveal`, `grade`, `renderSummary`, `updateProgressHeader`; extend `practiceKeys`)
- Modify (Test): `jeopardy/tests/test_research.py`

**Interfaces:**
- Consumes: page globals `applyGrade`, `gradeCurrent`, `sessionProgress` (Tasks 1, 3); Task 6's `practice`, `pBody`, `pProgress`, `pTally`, `saveCard`, `practicePool`, `assembleSession`, `initSession`, `closePractice`, `renderStart`, `escapeHtml`, `clueById`.
- Produces: the full three-screen loop; `practiceKeys` now handles Space (reveal) and 1/2/3 (grade) on the card screen.

- [ ] **Step 1: Write the failing test**

Append to `jeopardy/tests/test_research.py`:

```python
def test_render_html_has_card_loop_and_summary():
    data = build_research_data(_tokens_df(), _eras_df(), _labels())
    html = render_html(data)
    for marker in [
        'renderCard', 'renderSummary', 'updateProgressHeader',
        'pcard-reveal', 'class="pgrade"', 'data-g="missed"',
        'practice-again', 'scheduled to come back later',
        "applyGrade(", "gradeCurrent(", "sessionProgress(",
    ]:
        assert marker in html, marker
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --group analysis pytest jeopardy/tests/test_research.py::test_render_html_has_card_loop_and_summary -q`
Expected: FAIL — markers absent.

- [ ] **Step 3: Replace the `nextCard` stub with the real card loop**

In `jeopardy/analysis/research.py`, find the stub added in Task 6:

```js
      // Task 7 replaces this stub with the real card loop.
      function nextCard() { /* replaced in Task 7 */ }
```

Replace it with:

```js
      function nextCard() {
        if (!practice.session.queue.length) { renderSummary(); return; }
        practice.current = practice.session.queue[0].id;
        practice.revealed = false;
        practice.screen = 'card';
        renderCard();
      }
      function updateProgressHeader() {
        const p = sessionProgress(practice.session);
        pProgress.textContent = p.done + ' / ' + p.size + ' cards' +
          (p.retriesPending ? ' · ' + p.retriesPending + ' retr' + (p.retriesPending === 1 ? 'y' : 'ies') + ' remaining' : '');
        pTally.textContent = '✓' + practice.tally.knew + ' · ?' + practice.tally.unsure + ' · ✗' + practice.tally.missed;
      }
      function renderCard() {
        updateProgressHeader();
        const c = clueById(practice.current);
        let html = '<div class="pcard"><p class="pcard-scope">' + escapeHtml(c.category) + ' · ' + c.year + '</p>' +
          '<p class="pcard-clue">' + escapeHtml(c.clue) + '</p>';
        if (!practice.revealed) {
          html += '<button type="button" id="pcard-reveal" class="practice-start">Reveal</button>';
        } else {
          const url = escapeHtml(DATA.jarchive.replace('{game_id}', c.game_id));
          html += '<p class="pcard-answer">' + escapeHtml(c.answer) +
            ' · <a href="' + url + '" target="_blank" rel="noopener">J-Archive ↗</a></p>' +
            '<div class="pcard-grades">' +
            '<button type="button" class="pgrade" data-g="knew">Knew it <span>1</span></button>' +
            '<button type="button" class="pgrade" data-g="unsure">Unsure <span>2</span></button>' +
            '<button type="button" class="pgrade" data-g="missed">Missed <span>3</span></button></div>';
        }
        html += '</div>';
        pBody.innerHTML = html;
        if (!practice.revealed) {
          const rb = document.getElementById('pcard-reveal');
          rb.addEventListener('click', reveal);
          rb.focus();
        } else {
          pBody.querySelectorAll('.pgrade').forEach(b => b.addEventListener('click', () => grade(b.dataset.g)));
          const first = pBody.querySelector('.pgrade');
          if (first) first.focus();
        }
      }
      function reveal() { practice.revealed = true; renderCard(); }
      function grade(g) {
        practice.tally[g] = (practice.tally[g] || 0) + 1;
        practice.seen.add(practice.current);
        const rec = applyGrade(practice.store.cards[practice.current] || null, g, Date.now(), !practice.config.extra);
        saveCard(practice.current, rec);
        practice.session = gradeCurrent(practice.session, g);
        nextCard();
      }
      function renderSummary() {
        practice.screen = 'summary';
        updateProgressHeader();
        const now = Date.now();
        let scheduled = 0;
        for (const id of practice.seen) {
          const r = practice.store.cards[id];
          if (r && r.due > now) scheduled++;
        }
        const t = practice.tally;
        pBody.innerHTML = '<h2 class="practice-title">Session complete</h2>' +
          '<p class="psummary-tally">' + t.knew + ' knew · ' + t.unsure + ' unsure · ' + t.missed + ' missed</p>' +
          '<p class="psummary-sched">' + scheduled + ' card' + (scheduled === 1 ? '' : 's') + ' scheduled to come back later.</p>' +
          '<div class="practice-actions">' +
          '<button type="button" id="practice-again" class="practice-start">Practice again</button>' +
          '<button type="button" id="practice-done" class="practice-reset">Done</button></div>';
        document.getElementById('practice-again').addEventListener('click', () => {
          const ids = assembleSession(practicePool(practice.config.clusterIds, practice.config.era),
            practice.store.cards, Date.now(), practice.config.size, practice.config.extra, Math.random);
          if (!ids.length) { renderStart(); return; }
          practice.session = initSession(ids);
          practice.tally = { knew: 0, unsure: 0, missed: 0 };
          practice.seen = new Set();
          nextCard();
        });
        document.getElementById('practice-done').addEventListener('click', closePractice);
      }
```

- [ ] **Step 4: Extend `practiceKeys` with card-screen shortcuts**

Find the Task 6 `practiceKeys`:

```js
      function practiceKeys(e) {
        if (e.key === 'Escape') { closePractice(); return; }
        trapTab(e);
        // Card-screen shortcuts (Space / 1-2-3) are added in Task 7.
      }
```

Replace with:

```js
      function practiceKeys(e) {
        if (e.key === 'Escape') { closePractice(); return; }
        trapTab(e);
        if (practice.screen !== 'card') return;
        const tag = (e.target.tagName || '').toLowerCase();
        if (tag === 'input' || tag === 'textarea') return;
        if (!practice.revealed) {
          // The reveal button handles its own Space natively; only fill in when focus is elsewhere.
          if (e.key === ' ' && e.target.id !== 'pcard-reveal') { e.preventDefault(); reveal(); }
        } else if (e.key === '1' || e.key === '2' || e.key === '3') {
          grade({ '1': 'knew', '2': 'unsure', '3': 'missed' }[e.key]);
        }
      }
```

- [ ] **Step 5: Run the marker test and the full research file**

Run: `uv run --group analysis pytest jeopardy/tests/test_research.py -q`
Expected: PASS — new test plus all existing.

- [ ] **Step 6: Run the full test suites (no regressions)**

Run: `node --test jeopardy/analysis/practice.test.js`
Expected: PASS — 16 JS tests.

Run: `uv run --group analysis pytest jeopardy/tests/ -q`
Expected: PASS — full Python suite.

- [ ] **Step 7: Manual browser check**

Run: `uv run --group analysis python -m jeopardy research`, open `posts/jeopardy_ds/research/index.html`, click **Practice** → Start. Verify:
- Clue shows answer-hidden; **Reveal** (or Space) shows answer + J-Archive link; focus lands on Knew it.
- 1/2/3 grade and advance; header shows `done / size cards` and retries; a Missed card reappears once (~3 later); repeatedly missing it does not extend the session forever.
- Session ends → summary with tally + "N cards scheduled to come back later"; **Practice again** starts a fresh session, **Done** exits.
- Reload the page, reopen Practice, Start: previously-missed cards resurface first (persistence works). In a private window or with storage blocked, grading still works and the "Progress isn't being saved" notice appears.

- [ ] **Step 8: Commit**

```bash
git add jeopardy/analysis/research.py jeopardy/tests/test_research.py
git commit -m "feat: practice card loop, grading, persistence, summary

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

**1. Spec coverage** (against `docs/superpowers/specs/2026-09-17-practice-mode-design.md`):
- Entry / era-bar button / overlay / Exit returns focus → Task 6.
- Start screen: topic picker + Select all/none, size 10/20/30 distinct, Extra practice toggle, era snapshot, Start-disabled note, Reset progress → Task 6.
- Card loop: clue + category/year, Reveal, three grades, J-Archive link, progress with distinct cards + retries, tally → Task 7.
- Summary: tally, scheduled count, Practice again / Done → Task 7.
- Data reuse (no pipeline change), pool construction → Task 6 `practicePool`; `build_research_data` untouched (verified by existing passing tests).
- Scheduling: `INTERVAL_DAYS`, transitions both modes → Task 1; `assembleSession` tiers + `extra` gate → Task 2.
- In-session resurfacing (one retry per card) + `sessionProgress` → Task 3.
- Persistence: key, shape, read try/catch + `sanitizeStore`, write try/catch + notice → Task 4 (`sanitizeStore`) + Task 6 (`loadStore`/`saveCard`).
- Module as ESM, injected with export-strip → Task 5.
- Accessibility: role/aria-modal, focus trap, scroll lock, background aria-hidden, Escape, focus movement, card-scoped shortcuts → Tasks 6–7.
- Testing: `node:test` for the pure module, Python injection/marker tests → Tasks 1–7.
- No spec requirement is left without a task.

**2. Placeholder scan:** No "TBD"/"TODO"/"handle edge cases"/"similar to Task N". Every code step shows complete code.

**3. Type consistency:** Function names and signatures are identical across tasks and the spec's Interfaces block: `applyGrade(card, grade, now, promote)`, `assembleSession(pool, store, now, size, extra, rng)`, `gradeCurrent(session, grade)`, `sessionProgress(session)`, `sanitizeStore(parsed)`. The store shape `{v:1, cards:{id:{box,due,seen}}}` and localStorage key `jeopardy-practice-v1` match everywhere. The export line accumulates the same names the Python injection strips.

**Note for executor:** Tasks 6 and 7 edit the same inline `<script>`; the Task 7 stub-replacement anchors on the exact stub comment from Task 6, so run them in order.
