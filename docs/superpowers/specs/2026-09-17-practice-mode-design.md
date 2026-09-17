# Practice Mode — Design Spec

**Date:** 2026-09-17
**Status:** Approved design, pending spec review
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
- **Session size:** 10 / **20** / 30 cards (20 default; ~ten minutes).
- The start screen shows the **current study window** (era) as read-only context;
  the session snapshots the era in effect when it starts. To change era, the user
  closes practice, adjusts the era pills, and reopens — keeps session settings fixed
  once running.
- **Start session** button. Disabled with a note ("No clues match — widen your era
  or topics") when the resulting pool is empty.
- A small **Reset progress** link (clears all saved practice history after a
  confirm) lives here.

### Screen 2 — Card loop

- Header: **Exit**, a progress indicator (`3 / 20`), and a running tally
  (`✓2 · ?1 · ✗0`).
- Card front: the clue text, plus its category and year. Answer hidden.
- **Reveal** button (or Space). On reveal: the answer appears (styled like the
  existing `.answer-text` gold), plus a **J-Archive** link for the source game.
- Three grade buttons — **Knew it / Unsure / Missed** (or keys 1 / 2 / 3) — visible
  only after reveal. Grading advances to the next card.
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

A new (unseen) card is treated as box 0. On grade:

- **Knew it** → `box = min(4, box + 1)`
- **Unsure** → `box` unchanged
- **Missed** → `box = 0`

Then `due = now + INTERVAL_DAYS[box] * 86_400_000`, and `seen = now`.

So a brand-new card: Knew it → box 1 (due tomorrow); Unsure → box 0 (due again next
session); Missed → box 0 (due now, and resurfaces in-session).

### Session assembly

Given the era/topic-filtered `pool` (clue ids), the saved `store`, `now`, `size`,
and an injected `rng`, the session queue is built in three tiers, truncated to `size`:

1. **Due** — `store[id].due <= now`, sorted by `due` ascending.
2. **Unseen** — `id` not in `store`, shuffled by `rng`.
3. **Not-yet-due** — remaining seen cards, sorted by `due` ascending (fills the
   session only when tiers 1–2 are short, so heavy re-practice still yields a full
   session).

Cross-topic **mixing** comes from the shuffled unseen tier spanning all selected
clusters. If the whole pool is smaller than `size`, the session is simply shorter.

### In-session resurfacing

When a card is graded **Missed**, in addition to the box/due update above it is
re-enqueued ~3 positions later in the *live* session queue (or at the end if fewer
than 3 remain), so it reappears once more before the session ends. This is a UI-queue
behavior only; it does not further change the persisted schedule.

## Persistence

One localStorage key:

```
"jeopardy-practice-v1" → {
  v: 1,
  cards: { "<clue_id>": { box: 0..4, due: <ms epoch>, seen: <ms epoch> } }
}
```

- Written after each grade (single card upsert).
- **Reset progress** removes the key after a typed/OK confirm.
- Read is wrapped in try/catch; corrupt or absent data falls back to an empty store.
- No lifetime stats are persisted (YAGNI) — the session tally is in-memory only.

## Components & file structure

The whole feature lives in `jeopardy/analysis/research.py`'s HTML template, plus one
new pure JS module. Working within the established single-file, inline-script pattern,
with one targeted improvement: the branching scheduler logic is factored out so it can
be unit-tested.

- **`jeopardy/analysis/practice.js`** *(new)* — pure, DOM-free scheduler. Exposed both
  as a browser global (`globalThis.Practice`) and as a CommonJS module
  (`module.exports`) so the same file is injected into the page **and** required by
  Node tests (single source of truth). No side effects, no `Date.now()` inside pure
  functions (time is passed in).
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

nextBox(box: int, grade: 'knew'|'unsure'|'missed') -> int
dueAfter(now: ms, box: int) -> ms             // now + INTERVAL_DAYS[box]*86400000
applyGrade(card | null, grade, now) -> { box, due, seen }   // card null = unseen (box 0)
assembleSession(pool: id[], store, now, size, rng: ()->[0,1)) -> id[]
```

The inline glue owns: building `pool` from `DATA`, reading/writing localStorage,
`Date.now()`, `Math.random` (passed to `assembleSession` as `rng`), the missed
re-enqueue, and all DOM.

## Accessibility & responsive

- Overlay is `role="dialog"`, `aria-modal="true"`, labelled; Exit is keyboard-reachable
  and Escape exits. Focus moves into the overlay on open and returns to the Practice
  button on close.
- Keyboard: Space reveals; 1/2/3 grade (after reveal). Buttons remain the primary path.
- Full-viewport overlay is inherently mobile-friendly; grade buttons are large tap
  targets. Respects `prefers-reduced-motion` (no card-flip animation, or a reduced one).
- Reuses existing CSS custom properties (`--gold`, `--panel`, etc.) for visual
  consistency with the board.

## Testing strategy

- **Pure scheduler (`practice.js`)** — unit-tested with Node's built-in runner
  (`node --test`, zero new dependencies). Cases: each grade's box transition (incl.
  clamp at 4 and reset to 0), `dueAfter` interval math, `assembleSession` tier ordering
  (due before unseen before not-yet-due), `size` truncation, era/topic pool respected,
  and deterministic shuffle via injected `rng`.
- **Python injection** — a test asserting `render_html` inlines the practice module
  (no literal `__PRACTICE_JS__` remains) and that the Practice button / overlay markup
  is present.
- **DOM/localStorage glue** — verified manually in-browser, consistent with how the
  rest of the page's JS (fetchWiki, eligibleClues, renderFingerprint) is verified today.

*Flagged for review:* this introduces the repo's first JS test surface. The alternative
is to keep everything inline and browser-verify only (matching current practice). I
recommend the small `node --test` module because the scheduler is the one piece with
real branching logic worth locking down, and it costs no dependencies.

## Flagged decisions (confirm during spec review)

1. **Testing:** add a zero-dep `node --test` module for the pure scheduler (recommended)
   vs. inline + browser-verify only.
2. **Practice button placement:** era bar, right-aligned (proposed) vs. topbar.
3. **Session snapshots the era at start** (proposed) vs. live-follows the era pills.
4. **Not-yet-due fill tier** included so sessions stay full (proposed) vs. drop it and
   let sessions run short when nothing is due.

## Out of scope / future

- A "due today" badge on the Practice button (count of scheduled-due cards).
- Per-topic mastery stats or a progress dashboard.
- Exporting/importing progress.
