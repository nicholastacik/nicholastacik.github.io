# Engine-Verified Repertoire Trainer — Design

**Date:** 2026-09-17
**Status:** Approved (design), pending implementation plan
**Depends on:** the chess hardening pass (branch `chess-hardening-clean`) — the
movable board extends `board.ts` and the trainer relies on the corrected
variation tree. Hardening should merge before (or together with) this work.

## Purpose

Let the user drill an opening they've studied *from memory*: pick a line, play
their own side's moves, and get told immediately when they stray from the book —
with the engine showing its best move and how much a mismatch loses. This is the "keystone"
interaction: the same "evaluate this position" plumbing powers the parked
chess.com blunder trainer, which will reuse it with a different position source.

## Scope

**In scope (v1):**
- A "Practice" mode inside the existing study view.
- Drill **one line at a time** (a root-to-leaf path through the study tree).
- **Strict repertoire grading**: only the exact book move passes.
- On a repertoire mismatch, **auto**-show how much the move loses vs the engine's
  best line, plus the correct book move; the user retries or reveals.
- The opponent's moves auto-play from the book.
- A movable board (chessground) with legal-move enforcement + promotion.
- End-of-line summary (moves, mistakes, retries).
- Remember completed lines per study in `localStorage`.

**Out of scope (v1), deliberately:**
- Spaced-repetition scheduling / due-dates (the "scaling" step; a separate
  jeopardy-research practice mode is building an SRS pattern — do not duplicate
  it here).
- The chess.com blunder trainer (parked as the next project; this is its base).
- Whole-tree "opponent varies" drilling and random spot-quizzes (we chose
  one-line-at-a-time).
- Grading off-book-but-good moves as anything other than "wrong" (we chose
  strict repertoire).
- Accounts / cross-device sync.

## Key decisions (from brainstorming)

- **Position source:** the existing opening studies. Reuses content, useful now,
  and is the exact plumbing the blunder trainer reuses later.
- **Grading:** strict — the exact book move is correct; anything else is a
  **repertoire mismatch** (not necessarily a chess mistake). The engine is
  **not** used to grade correctness.
- **Engine's role:** on a mismatch only, measure how much the played move loses
  relative to the engine's best line. The engine's move is described as the
  **best response**, and an eval-drop is **only asserted when the loss supports
  it** — an off-book move (or another of the study's own variations) can be
  perfectly playable, in which case the feedback says "playable alternative"
  rather than claiming a punishment. It never claims the played move beats the
  book move. The study's authored `comment` supplies the positive "why."
- **Session shape:** one line at a time; the user selects which line.
- **Engine provider:** pluggable `EvalProvider` interface; default
  **chess-api.com** (Stockfish 18, browser-oriented), with **stockfish.online**
  as a drop-in alternate and bundled-WASM as a later fallback.
- **Wrong-move feedback:** shown automatically (it only fires on mistakes, so
  volume is low); every eval cached in `localStorage`.
- **Location:** a mode within the study view, not a separate page.

## Architecture

New/changed units, each with one responsibility and a testable boundary:

```
chess/src/
  practice.ts       # NEW: pure drill state machine (no DOM, no network)
  evalProvider.ts   # NEW: EvalProvider interface + chess-api.com adapter
  board.ts          # CHANGED: add a movable mode alongside the view-only one
  ui.ts             # CHANGED: Practice-mode rendering in the study view
  tree.ts           # REUSED: line enumeration helper added (root-to-leaf paths)
  style.css         # CHANGED: practice-mode styles
chess/tests/
  practice.test.ts      # NEW: drill state machine
  evalProvider.test.ts  # NEW: adapter parses a recorded response shape
  ui-practice.test.ts   # NEW: practice-mode rendering with fakes
```

### `tree.ts` — line enumeration (added)
- `enumerateLines(root: TreeNode): { id: string; label: string; path: Path }[]`
  — every root-to-leaf path. `label` is a human name (e.g. "Mainline",
  "vs Petrov") for **display only**. `id` is a **stable identity** derived from
  the path's canonical SAN sequence; it is what gets persisted for completion, so
  two paths that share a first-divergence label remain distinct, and completion
  survives label-wording changes. (The training side is **not** part of the id —
  `TreeNode` doesn't carry it, completion is already namespaced per study, and a
  study is drilled from a single side in v1; if per-side drilling of
  `side: "both"` studies is added later, the side joins the persistence key then
  and `enumerateLines` takes a side argument.) Editing or extending a line
  changes its SAN sequence and therefore its `id`: the old completion record
  simply no longer matches (a changed line is a new line); no migration in v1.
  Pure; unit-tested — including two paths that collide on label but not on `id`.

### `practice.ts` — drill state machine (pure)
The heart. No DOM, no network — takes a chosen line and the study's `side`, and
drives the drill so the UI is a thin renderer and the logic is fully testable.

**Every advance goes through the controller** — no state is mutated elsewhere.
- Types:
  - `type Grade = { kind: "correct"; expected: string } | { kind: "mismatch"; expected: string /* book SAN */; played: string }`
    — a mismatch names a *repertoire* mismatch, not a "bad move" (see the
    engine-role decision).
  - `interface PracticeState { fen: string; ply: number; toMove: "user" | "opponent" | "done"; mistakes: number; revealed: number; cleanFirstTry: number }`
  - `interface Summary { plies: number; cleanFirstTry: number; mistakes: number; revealed: number }`
- `createDrill(line: Path, userSide: "white" | "black")` returns a controller:
  - `state(): PracticeState` — `toMove` is `"done"` at the leaf.
  - `playOpponent(): { san: string } | null` — when `toMove === "opponent"`,
    **applies** the book reply, advances the ply, and returns it; `null`
    otherwise. The UI only animates the returned SAN — it never advances state.
  - `submit(san: string): Grade` — compares against the book move. `"correct"`
    **advances** the ply (recording `cleanFirstTry` iff no prior mismatch/reveal
    at this ply); `"mismatch"` increments `mistakes` and **holds** the position
    for a retry — it never advances.
  - `reveal(): string` — returns the book SAN, **applies it**, advances, and
    marks the ply `revealed` (so it can never count as clean). The give-up path.
  - `summary(): Summary` — valid once `toMove === "done"`.
  - Positions derive from replaying the line prefix with `chess.js`
    (`positionAt`), reusing existing tree/replay code.
- **Completion** is defined at the leaf: after the final book move — whichever
  side makes it — `toMove` becomes `"done"` and `summary()` is valid. Both a
  final user move and a final opponent move are covered by tests.
- The user's side is the study's `side`; a `side: "both"` study defaults to
  white for v1 (the line selector can offer the choice later).

### `evalProvider.ts` — engine access
- `interface EvalProvider { evaluate(fen: string): Promise<EngineEval> }`
- `interface EngineEval { bestMove: string /* UCI */; cp: number | null; mate: number | null; depth: number }`
  — **`cp`/`mate` are always from White's perspective** (chess-api.com's
  documented convention; the adapter guarantees it so callers never guess the
  sign). Exactly one of `cp`/`mate` is non-null.
- `class ChessApiProvider implements EvalProvider` — POSTs `{ fen, depth }` to
  `https://chess-api.com/v1` and maps the response into a White-perspective
  `EngineEval`. The White-perspective contract is per chess-api.com's docs and is
  **verified by a first-plan-step live probe** (which also pins the exact
  request/response fields). `stockfish.online` is a confirmed drop-in alternate
  (`{ evaluation, mate, bestmove: "bestmove e2e4 ponder ...", continuation }`).
- A `localStorage` cache wraps the provider, keyed by `fen`+`depth`.

### Mismatch analysis (loss relative to the engine's best line)
On a repertoire mismatch the UI computes **how much the played move loses
relative to the engine's best line** — not an absolute score — in the
**trainee's** perspective, from two evaluations:
- **Baseline** = evaluate the *decision position* (the FEN **before** the move) —
  yields the engine's best move and the score under best play.
- **Played** = evaluate the FEN **after** the trainee's move.
- Both `EngineEval`s are White-perspective; convert each to the trainee's
  perspective (negate iff the trainee plays Black), then
  `loss = trainee(baseline) − trainee(played)` (≥ 0 up to search noise).
- **What this can and cannot say:** the baseline is *best play from the decision
  position*, NOT the book move's continuation. So the analysis speaks only to
  loss vs best play — it **cannot** claim the played move beats the book move,
  and a baseline mate is best-play's mate, not the book move's. We make no
  stronger-than-book claim. (A true book-vs-played comparison would need a third
  eval of the book line — deferred; unneeded for v1.)
- **Verdict from the loss:** small (≤ ~50cp, including tiny negatives from search
  noise) → "a playable alternative — loses little vs the best move"; larger →
  "loses ~N pawns; the engine's best move here is `bestMove`." The study's book
  move is always shown alongside (from strict grading), without asserting it is
  the engine's best.
- **Mate handling (relative to best play):** if the *played* position is mate
  against the trainee → "this gets mated in N"; if the *baseline* was a mate the
  played move threw away → "a forced mate was available." Never subtract a mate
  from a centipawn score, and never attribute the mate to the book move.

### `board.ts` — movable mode + teardown (changed)
- Add `createMovableBoard(el, { orientation, onMove })` (or a `movable` option on
  the existing factory) configuring chessground with `movable.free = false`,
  `movable.dests` from `chess.js` legal moves for the side to move, a promotion
  picker, and an `onMove(from, to, promotion)` callback. The trainer sets legal
  dests for the user's turn only.
- **`BoardHandle` gains `destroy(): void`.** Chessground's movable mode installs
  document/window listeners; `destroy()` calls chessground's own `destroy` to
  remove them. Every board (view-only included) implements it, and the caller
  MUST call it before replacing a board or tearing down the view — see the
  teardown contract in `ui.ts`.

### `ui.ts` — Practice mode (changed)
- A "Practice" button in the study view enters practice mode: render a line
  picker (`enumerateLines`), then the drill (movable board + a status/feedback
  panel + Reveal / Restart / Exit controls).
- Injected deps mirror the existing `makeBoard` pattern so the mode is
  jsdom-testable with fakes:
  `interface PracticeDeps { makeBoard: ...; evalProvider: EvalProvider }`.
- **Teardown contract (one owner of listeners at a time):** entering practice
  from the viewer removes the viewer's `keydown` handler and `destroy()`s the
  view-only board before creating the movable one; exiting practice (or routing
  away) `destroy()`s the movable board and removes practice listeners before the
  viewer is re-created. The existing MutationObserver-based teardown is extended
  to cover the practice board.
- **Stale-analysis guard:** each `evaluate` request is tagged with a token
  `(sessionId, ply, attempt)`. A resolved result is applied only if the token
  still matches the current drill state; otherwise it is dropped — so a slow
  response can't overwrite feedback after the user has retried, advanced,
  restarted, or exited. (Same shape as the `generation` guard already in
  `codenames/src/main.ts`.)

## Data flow (one drill)

1. User picks a study → **Practice** → picks a line.
2. `createDrill(line, side)`; render the start position on a movable board.
3. If it's the opponent's move, call `playOpponent()` — it applies the book
   reply and advances — and animate the returned SAN.
4. On the user's move, `board.onMove` → SAN (`chess.js`) → `submit(san)`.
   - **correct** → confirm, advance, then `playOpponent()` for the next reply.
   - **mismatch** → hold the position, increment mistakes, and **auto** run the
     mismatch analysis (§Mismatch analysis): evaluate the decision position and
     the after-move position, tag both with the `(sessionId, ply, attempt)`
     token, and — only if the token still matches on resolve — render the verdict
     ("not your line here; book is `expected`" plus, per the loss, either "a
     playable alternative" or "loses ~N — the engine's best move is Z"). User
     retries or `reveal()`s.
5. At the leaf (`toMove === "done"`) → render `summary()`; mark the line
   completed in `localStorage` by its stable `id`.

## Error handling

- **Engine API failure / timeout / rate-limit:** grading is book-based and does
  not depend on the engine, so a failed `evaluate` degrades gracefully — still
  mark the move wrong and show the book move, with a quiet "couldn't reach the
  engine for the analysis" note instead of the loss figure. Timeout ~6s, no
  hard retry loop (one retry at most). The drill never blocks on the network.
- **Illegal input:** impossible via the movable board (dests are legal-only), but
  `submit` still guards by replaying with `chess.js`.
- **Malformed engine response:** the adapter validates the shape and throws a
  typed error the caller treats as an API failure (above).

## Persistence

`localStorage`, two namespaces, both tolerant of absent/corrupt values:
- eval cache: `chess:eval:<fen>:<depth>` → `EngineEval`.
- completed lines: `chess:practice:<studyId>` → set of line **ids** completed
  (the stable `enumerateLines` id, never the display label).

## Testing

- `tree.test.ts`: `enumerateLines` yields the right paths; **two paths that
  collide on label get distinct `id`s**, and an `id` is stable across a label
  rewording.
- `practice.test.ts`: `playOpponent` applies + returns the book reply; `submit`
  correct advances and records clean-first-try; mismatch holds + counts and does
  **not** advance; `reveal` applies + marks the ply non-clean; **completion at
  the final ply for both a final user move and a final opponent move**;
  `summary()` accounting (clean/mistakes/revealed); black-side drills (user
  plays Black).
- `evalProvider.test.ts`: the adapter maps a **recorded** chess-api.com response
  into a White-perspective `EngineEval`; both a cp and a mate response covered;
  no live network.
- Mismatch analysis: `loss` (baseline−played) in the trainee's perspective for
  both a White and a Black trainee; a near-zero/negative loss reads as "a
  playable alternative" (never "stronger than book"); a mate score is described
  in mate terms, never subtracted from a cp, never attributed to the book move.
- `ui-practice.test.ts`: entering practice removes the viewer `keydown` handler
  and `destroy()`s the view-only board; the line picker renders; a mismatch
  triggers the analysis calls on the fake provider and renders the verdict; a
  correct move advances; exiting `destroy()`s the movable board. Fakes throughout.
- **Async race tests (deferred promises):** resolve analysis requests out of
  order, and resolve one *after* Exit/Restart — assert stale results are dropped
  and never overwrite current feedback.
- Engine failure path: fake provider rejects → UI still shows the book move and a
  graceful note; the drill stays usable.

## Risks & mitigations

- **chess-api.com shape uncertainty.** The eval sign is documented
  (White-perspective), so the normalization contract is written now; the
  remaining unknown is the exact request/response field names. Mitigation: first
  plan step is a live probe to pin them; the `EvalProvider` interface isolates
  the adapter, and stockfish.online is a confirmed drop-in.
- **Async races between analysis and drill state.** Mitigation: the
  `(sessionId, ply, attempt)` token guard drops stale results; covered by
  deferred-promise tests (out-of-order and after-exit).
- **Leaked listeners across mode/route changes.** Mitigation: `BoardHandle.destroy()`
  plus the explicit one-owner teardown contract; asserted in `ui-practice.test.ts`.
- **Free third-party engine longevity/limits.** Mitigation: pluggable provider +
  localStorage cache + engine only on mistakes (low volume) + graceful
  degradation; bundled-WASM fallback documented for later.
- **Movable board is new surface.** Mitigation: thin `board.ts` extension behind
  the same injected-factory pattern; drill logic is pure and tested without it.
- **Scope creep toward SRS.** Mitigation: explicitly deferred; v1 persistence is
  completed-lines only.
