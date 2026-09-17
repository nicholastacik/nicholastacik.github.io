# Practice Mode — Design Spec

**Date:** 2026-09-17
**Status:** Approved (design + spec-review refinements folded in)
**Feature:** A dedicated spaced-repetition practice mode for the Jeopardy research tool ("The Board").

## Goal

Add a cross-topic flashcard practice loop to the research page: the user picks
topics, sees real clues answer-hidden, self-grades **Knew it / Unsure / Missed**,
missed cards resurface, and progress persists locally so a spaced-repetition
schedule surfaces due cards on return. Everything runs client-side in the
self-contained HTML page — no server, no account, no new offline data.

This is distinct from the existing per-entity **Sample clue** button (a single
one-off self-test scoped to whatever entity is selected). Practice mode is a
dedicated, multi-topic study session with scheduling and durable progress.

## Non-goals

- No server, no login, no cross-device sync. Progress is per-browser (localStorage).
- No new parquet artifacts, no changes to the offline pipeline, no new embedded data.
- Not a full SM-2 / Anki-grade algorithm. A deliberately simple Leitner-lite schedule.
- No leaderboard, no timed/speed scoring, no audio, no Daily-Double wagering.
- Does not touch the existing Sample clue feature.

## User experience

### Entry

A **Practice** button in the era bar (right-aligned, always visible). Clicking it
opens a full-viewport overlay (`#practice`) above the three-pane layout. **Exit**
returns the user to the research view exactly as they left it (selected type,
entity, era, scroll all preserved — the overlay never mutates research state).

### Screen 1 — Start

- **Topic picker:** a checkbox list of every category type that has a clue pool
  (all types with `DATA.quiz[clusterId]` entries), labeled by type name and
  ordered as in the current era's list. A **Select all / none** toggle. Default:
  all selected.
- **Session size:** 10 / **20** / 30 **distinct** cards (20 default; ~ten minutes).
  Retries (see In-session resurfacing) do not count against this number.
- **Extra practice** toggle (default off): normally a session draws only *due* and
  *unseen* cards, so once you have cleared a small pool there is nothing to study and
  Start is disabled. Turning Extra practice on also pulls in already-scheduled
  (not-yet-due) cards **and** switches grading to no-promote semantics (correct answers
  leave the schedule untouched; only misses reset it) — so drilling a tiny pool like
  "Plants & Botany · Since 2020" (five cards) can't inflate mastery to box 4 in four
  rapid sessions.
- The start screen shows the **current study window** (era) as read-only context;
  the session snapshots the era in effect when it starts. To change era, the user
  closes practice, adjusts the era pills, and reopens — keeps session settings fixed
  once running.
- **Start session** button. Disabled with a note ("Nothing due — turn on Extra
  practice, or widen your era / topics") when the resulting pool is empty.
- A small **Reset progress** link (clears all saved practice history after a
  confirm) lives here.

### Screen 2 — Card loop

- Header: **Exit**, a progress indicator counting **distinct cards** with retries
  called out separately — e.g. `12 / 20 cards · 3 retries remaining` — and a running
  tally (`✓2 · ?1 · ✗0`).
- Card front: the clue text, plus its category and year. Answer hidden.
- **Reveal** button (Space on the card screen). On reveal: the answer appears (styled
  like the existing `.answer-text` gold), plus a **J-Archive** link for the source game;
  focus moves to the first grade button.
- Three grade buttons — **Knew it / Unsure / Missed** (keys 1 / 2 / 3, active only after
  reveal) — visible only after reveal. Grading advances to the next card and moves focus
  to its Reveal button (or, on the last card, into the summary screen).
- Cards are drawn mixed across the selected topics (see Scheduling).

### Screen 3 — Summary

Shown when the session queue is exhausted:

- Tally: `18 knew · 5 unsure · 7 missed` (grades given this session; a resurfaced
  card counts each time it is graded).
- A line: `N cards scheduled to come back later.`
- Buttons: **Practice again** (same topics/size/era, reassembles from the updated
  schedule) and **Done** (exit to research).

## Data — reuses what the page already embeds

No new data. The practice deck is derived entirely from the existing payload:

- `DATA.clues[clueId]` → `{clue, answer, year, category, game_id}` — the card content.
- `DATA.quiz[clusterId]` → `{ "": [general ids], "<phrase>": [entity ids], ... }` —
  the per-topic clue-id pool.
- `DATA.byEra[era]` → `[{cluster_id, name, ...}]` — topic names for the picker.
- `DATA.jarchive` — the game-URL template for the source link.

**Pool for a session** = for each selected cluster, the deduped union of all its
`DATA.quiz` clue ids, keeping only ids present in `DATA.clues` with `year >=`
the snapshotted era. (Same construction as `eligibleClues()`'s `anyClues`, unioned
across the selected clusters.) A **card's identity for scheduling is its `clue_id`.**

Every id in `DATA.quiz` is already guaranteed present in `DATA.clues` (the store is
pruned to referenced ids in `run_fingerprints`), so the pool is always resolvable.

## Scheduling — Leitner-lite

Each card carries a **box** 0–4 and a **due** timestamp. Boxes map to intervals:

| Box | Interval to next due |
|-----|----------------------|
| 0   | 0 days (same/next session) |
| 1   | 1 day  |
| 2   | 3 days |
| 3   | 7 days |
| 4   | 21 days |

`INTERVAL_DAYS = [0, 1, 3, 7, 21]`.

### Grade transitions

Grading has two modes. **Normal** mode (default sessions) promotes on success;
**Extra practice** mode never promotes, so repeated drilling of a small pool can't
inflate mastery. A new (unseen) card is treated as box 0.

**Normal mode (`promote = true`):**

- **Knew it** → `box = min(4, box + 1)`
- **Unsure** → `box` unchanged
- **Missed** → `box = 0`

Then `due = now + INTERVAL_DAYS[box] * 86_400_000`.

**Extra practice mode (`promote = false`):**

- **Knew it** / **Unsure** → `box` and `due` **unchanged** (correct answers don't
  advance the schedule).
- **Missed** → `box = 0`, `due = now` (misses can still reset).

In both modes `seen = now`. So a brand-new card in normal mode: Knew it → box 1 (due
tomorrow); Unsure → box 0 (due again next session); Missed → box 0 (due now, and
resurfaces in-session).

### Session assembly

Given the era/topic-filtered `pool` (clue ids), the saved `store`, `now`, `size`, an
`extra` flag, and an injected `rng`, `assembleSession` selects up to `size` **distinct**
ids in tier order:

1. **Due** — `store[id].due <= now`, sorted by `due` ascending.
2. **Unseen** — `id` not in `store`, shuffled by `rng`.
3. **Not-yet-due** — remaining seen cards, sorted by `due` ascending — **only when
   `extra` is true.** A normal session stops after tiers 1–2; if that yields nothing,
   the caller disables Start (or the user turns on Extra practice). This is the fix for
   mastery inflation: not-yet-due cards are reachable only in the no-promote Extra mode.

Cross-topic **mixing** comes from the shuffled unseen tier spanning all selected
clusters. If the available pool is smaller than `size`, the session is simply shorter.

### In-session resurfacing

The live session queue is managed by the **pure module** (not ad-hoc in the glue), so
the retry rules are testable. Each queue entry is `{ id, retried }`.

When the current card is graded, `gradeCurrent(session, grade)` pops it and:

- **Missed** and not yet retried → re-enqueue `{ id, retried: true }` at position
  `min(3, remaining)` (≈3 cards later, or the end if fewer remain). This is the card's
  **one and only** retry this session.
- **Missed** but already retried, or any non-missed grade → drop it (no re-enqueue).

So each clue gets **at most one retry per session**, even if the retry is also missed —
repeatedly-missed cards can never keep extending the queue. Retries are a UI-queue
behavior only; they do not further change the persisted schedule beyond the single
box/due update the miss already applied.

`sessionProgress(session)` derives `{ done, size, retriesPending }` from the queue:
`size` = distinct ids the session started with, `done` = `size − (distinct ids still in
queue)`, `retriesPending` = queued entries with `retried = true`. This drives the
`12 / 20 cards · 3 retries remaining` header.

## Persistence

One localStorage key:

```
"jeopardy-practice-v1" → {
  v: 1,
  cards: { "<clue_id>": { box: 0..4, due: <ms epoch>, seen: <ms epoch> } }
}
```

- Written after each grade (single card upsert).
- **Reset progress** removes the key after an OK/confirm.
- No lifetime stats are persisted (YAGNI) — the session tally is in-memory only.

**Read** is wrapped in try/catch (getItem and `JSON.parse` can both throw), then run
through the pure `sanitizeStore` validator — valid JSON can still hold junk. It requires
`v === 1`, and keeps only card records whose `box` is an integer in `0..4` and whose
`due` and `seen` are finite numbers; anything else is dropped. A wrong/absent version or
unparseable blob yields an empty store.

**Write** is also wrapped in try/catch: `setItem` throws on quota exhaustion or in
privacy modes that disable storage (`QuotaExceededError`, `SecurityError`). On the first
write failure the session **keeps running from the in-memory store** and shows a small,
dismissible "Progress isn't being saved" notice; grading continues to work for the rest
of the session, it just won't persist.

## Components & file structure

The whole feature lives in `jeopardy/analysis/research.py`'s HTML template, plus one
new pure JS module. Working within the established single-file, inline-script pattern,
with one targeted improvement: the branching scheduler logic is factored out so it can
be unit-tested.

- **`jeopardy/analysis/practice.js`** *(new)* — pure, DOM-free scheduler and session
  queue. Written as an **ES module** (`export`), matching the repo's existing
  `posts/montreal_events/events/events-core.js` so Node's `node:test` can `import` it
  directly. Function declarations are plain (`function nextBox(...)`) with a single
  trailing `export { ... }`. `render_html` inlines the file with its `export` line(s)
  stripped, so the declarations become page-level globals the inline glue calls — one
  source of truth, injected into the page and imported by tests. No side effects; no
  `Date.now()`/`Math.random()` inside pure functions (time and `rng` are passed in).
- **`jeopardy/analysis/research.py`**:
  - `render_html` gains a `__PRACTICE_JS__` placeholder; the module file is read and
    inlined into a `<script>` before the main IIFE.
  - Template additions: practice CSS block; the **Practice** button in the era bar;
    the `#practice` overlay container; the inline practice **UI/glue** code (localStorage
    read/write, DOM rendering of the three screens, event wiring) inside the existing
    IIFE, calling into `Practice.*` for all scheduling decisions.
  - `build_research_data` is **unchanged** — it already embeds `clues`, `quiz`, `byEra`,
    and `jarchive`.

### Interfaces — `practice.js` pure functions

```
INTERVAL_DAYS: number[]                       // [0, 1, 3, 7, 21]
GRADES: 'knew' | 'unsure' | 'missed'

// scheduling
nextBox(box: int, grade: GRADE) -> int
dueAfter(now: ms, box: int) -> ms             // now + INTERVAL_DAYS[box]*86400000
applyGrade(card | null, grade: GRADE, now: ms, promote: bool) -> { box, due, seen }
    // card null = unseen (box 0). promote=false => knew/unsure leave box+due unchanged
    //                                              (seen=now); missed => box 0, due=now.
assembleSession(pool: id[], store, now: ms, size: int, extra: bool, rng: ()->[0,1)) -> id[]
    // distinct ids, tier order due→unseen→(not-yet-due only if extra), truncated to size.

// session queue (in-session retries)
initSession(ids: id[]) -> { queue: [{id, retried:false}], size: int }
gradeCurrent(session, grade: GRADE) -> session   // pops current; requeues a first miss once
sessionProgress(session) -> { done: int, size: int, retriesPending: int }

// persistence validation
sanitizeStore(parsed: any) -> { v: 1, cards: { [id]: {box,due,seen} } }   // drops invalid records
```

The inline glue owns: building `pool` from `DATA`, reading/writing localStorage (with
try/catch and the save-failure notice), `Date.now()`, `Math.random` (passed to
`assembleSession` as `rng`), modal/focus/keyboard handling, and all DOM.

## Accessibility & responsive

Follows the W3C APG modal-dialog pattern:

- **Container:** `role="dialog"`, `aria-modal="true"`, labelled by its heading.
- **Focus containment:** while open, Tab/Shift-Tab cycle within the overlay only (focus
  trap). The rest of the page is made inert (`inert` where supported, else
  `aria-hidden="true"` on the layout) and background scroll is locked (`overflow:hidden`
  on `body`).
- **Focus movement:** on open, focus goes to the first control (start screen: the topic
  list / Start; card screen: Reveal). On **Reveal**, focus moves to the first grade
  button. After **grading**, focus moves to the next card's Reveal button — or, on the
  last card, to the summary's **Practice again**. On close (Exit/Escape), focus returns
  to the **Practice** button.
- **Escape** closes the overlay from anywhere inside it.
- **Keyboard shortcuts are scoped to the card screen** and ignored when focus is in an
  input/checkbox: Space reveals; 1/2/3 grade (only after reveal). On the start screen
  Space toggles the focused topic checkbox normally — the shortcuts never hijack it.
  Buttons remain the primary path throughout.
- Full-viewport overlay is inherently mobile-friendly; grade buttons are large tap
  targets. Respects `prefers-reduced-motion`.
- Reuses existing CSS custom properties (`--gold`, `--panel`, etc.) for visual
  consistency with the board.

## Testing strategy

- **Pure module (`practice.js`)** — unit-tested with Node's built-in runner
  (`node --test`, zero new dependencies), following the existing
  `posts/montreal_events/events/events-core.test.js` (`import { test } from "node:test"`).
  Cases:
  - `nextBox` / `applyGrade` — each grade's transition, clamp at box 4, reset to 0, and
    **both modes**: `promote=false` leaves box+due unchanged on knew/unsure but still
    resets on miss.
  - `dueAfter` — interval math for every box.
  - `assembleSession` — tier ordering (due → unseen → not-yet-due), `extra=false`
    excludes the not-yet-due tier, `size` truncation, distinctness, deterministic shuffle
    via injected `rng`.
  - `gradeCurrent` / session queue — a first miss requeues once at `min(3, remaining)`; a
    **second miss of the same card does not requeue** (finite retries); a **one-card
    pool** (miss → single retry → miss again → session ends); **missing the final card**
    still yields exactly one retry. `sessionProgress` counts distinct `done` and
    `retriesPending` correctly across these.
  - `sanitizeStore` — drops records with out-of-range/non-integer `box`, non-finite
    `due`/`seen`, and returns an empty store on wrong/missing `v`.
- **Python injection** — a test asserting `render_html` inlines the practice module
  (no literal `__PRACTICE_JS__` remains) and that the Practice button / overlay markup
  is present.
- **DOM/localStorage glue** — verified manually in-browser, consistent with how the
  rest of the page's JS (fetchWiki, eligibleClues, renderFingerprint) is verified today.

## Resolved decisions

1. **Testing:** ✅ zero-dep `node --test` module for the pure scheduler. (Not the repo's
   first JS test surface — `posts/montreal_events/events/events-core.test.js` already uses
   `node:test`; we follow its conventions.)
2. **Practice button placement:** ✅ era bar, right-aligned.
3. **Era handling:** ✅ session snapshots the era at start.
4. **Not-yet-due cards:** ✅ **not** included automatically. Reachable only via the opt-in
   **Extra practice** mode, which additionally uses no-promote grading so repeated drilling
   of a small pool can't inflate mastery (refinement 1).

## Out of scope / future

- A "due today" badge on the Practice button (count of scheduled-due cards).
- Per-topic mastery stats or a progress dashboard.
- Exporting/importing progress.
