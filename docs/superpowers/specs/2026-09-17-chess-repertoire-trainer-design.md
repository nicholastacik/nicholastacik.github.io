# Engine-Verified Repertoire Trainer — Design

**Date:** 2026-09-17
**Status:** Approved (design), pending implementation plan
**Depends on:** the chess hardening pass (branch `chess-hardening-clean`) — the
movable board extends `board.ts` and the trainer relies on the corrected
variation tree. Hardening should merge before (or together with) this work.

## Purpose

Let the user drill an opening they've studied *from memory*: pick a line, play
their own side's moves, and get told immediately when they stray from the book —
with the engine showing how the wrong move is punished. This is the "keystone"
interaction: the same "evaluate this position" plumbing powers the parked
chess.com blunder trainer, which will reuse it with a different position source.

## Scope

**In scope (v1):**
- A "Practice" mode inside the existing study view.
- Drill **one line at a time** (a root-to-leaf path through the study tree).
- **Strict repertoire grading**: only the exact book move passes.
- On a wrong move, **auto**-show the engine's punishment (refutation + eval
  swing) plus the correct book move; the user retries or reveals.
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
- **Grading:** strict — the exact book move is correct; anything else is wrong.
  The engine is **not** used to grade correctness.
- **Engine's role:** on a wrong move only, evaluate the resulting position and
  show the refutation + eval swing (the "punishment"), demonstrating why the
  book move matters. The study's authored `comment` supplies the positive "why."
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
- `enumerateLines(root: TreeNode): { label: string; path: Path }[]` — every
  root-to-leaf path, each with a human label (e.g. "Mainline", "vs Petrov"),
  derived from the first move that diverges from the mainline. Pure; unit-tested.

### `practice.ts` — drill state machine (pure)
The heart. No DOM, no network — takes a chosen line and the study's `side`, and
drives the drill so the UI is a thin renderer and the logic is fully testable.

- Types:
  - `interface Grade { kind: "correct" | "wrong"; expected: string /* book SAN */ }`
  - `interface PracticeState { fen: string; ply: number; toMove: "user" | "opponent"; done: boolean; mistakes: number }`
- `createDrill(line: Path, userSide: "white" | "black")` returns a controller:
  - `state(): PracticeState`
  - `opponentMove(): { san: string } | null` — when it's the opponent's turn,
    the book move to auto-play (null if it's the user's turn or the line is done).
  - `submit(san: string): Grade` — grade the user's move against the book move;
    on "correct" advance the ply, on "wrong" increment `mistakes` and hold.
  - `reveal(): string` — the book SAN, for the "give up" path.
  - Positions are derived by replaying the line prefix with `chess.js`
    (`positionAt`), reusing the existing tree/replay code.
- The user's side is the study's `side`; a `side: "both"` study defaults to
  white for v1 (the line selector can offer the choice later).

### `evalProvider.ts` — engine access
- `interface EvalProvider { evaluate(fen: string): Promise<EngineEval> }`
- `interface EngineEval { bestMove: string /* UCI */; cp: number | null; mate: number | null; depth: number }`
  — `cp` is centipawns from the side-to-move's perspective (normalized in the
  adapter so the UI never worries about sign convention).
- `class ChessApiProvider implements EvalProvider` — POSTs
  `{ fen, depth }` to `https://chess-api.com/v1` and maps the response into
  `EngineEval`. **Exact request/response shape and the eval sign convention MUST
  be confirmed against chess-api.com during implementation** (a first plan step
  is a live probe of the endpoint; `stockfish.online`'s shape is already
  confirmed: `{ evaluation, mate, bestmove: "bestmove e2e4 ponder ...", continuation }`).
- A `localStorage` cache wraps the provider: key by FEN+depth, so a repeated
  wrong move in the same position costs no network call.

### `board.ts` — movable mode (changed)
- Add `createMovableBoard(el, { orientation, onMove })` (or a `movable` option on
  the existing factory) that configures chessground with `movable.free = false`,
  `movable.dests` from `chess.js` legal moves for the side to move, a promotion
  picker, and an `onMove(from, to, promotion)` callback. The view-only board is
  unchanged. The trainer sets legal dests for the user's turn only.

### `ui.ts` — Practice mode (changed)
- A "Practice" button in the study view enters practice mode: render a line
  picker (`enumerateLines`), then the drill (movable board + a status/feedback
  panel + Reveal / Restart / Exit controls).
- Injected deps, mirroring the existing `makeBoard` pattern, so the whole mode is
  jsdom-testable with fakes:
  `interface PracticeDeps { makeBoard: ...; evalProvider: EvalProvider }`.

## Data flow (one drill)

1. User picks a study → **Practice** → picks a line.
2. `createDrill(line, side)`; render the start position on a movable board.
3. If it's the opponent's move, auto-play `opponentMove()` and advance.
4. On the user's move, `board.onMove` → convert to SAN (`chess.js`) → `submit(san)`.
   - **correct** → confirm, advance, continue (auto-play the next opponent move).
   - **wrong** → keep the position, increment mistakes, and **auto** call
     `evalProvider.evaluate(fenAfterWrongMove)` → render "your move drops to X;
     opponent plays Y; the book move is `expected`." User retries or `reveal()`s.
5. At the leaf → summary; mark the line completed in `localStorage`.

## Error handling

- **Engine API failure / timeout / rate-limit:** grading is book-based and does
  not depend on the engine, so a failed `evaluate` degrades gracefully — still
  mark the move wrong and show the book move, with a quiet "couldn't reach the
  engine for the punishment line" note instead of the eval. Timeout ~6s, no
  hard retry loop (one retry at most). The drill never blocks on the network.
- **Illegal input:** impossible via the movable board (dests are legal-only), but
  `submit` still guards by replaying with `chess.js`.
- **Malformed engine response:** the adapter validates the shape and throws a
  typed error the caller treats as an API failure (above).

## Persistence

`localStorage`, two namespaces, both tolerant of absent/corrupt values:
- eval cache: `chess:eval:<fen>:<depth>` → `EngineEval`.
- completed lines: `chess:practice:<studyId>` → set of line labels completed.

## Testing

- `tree.test.ts`: `enumerateLines` yields the right paths + labels on a
  fixture with variations.
- `practice.test.ts`: opponent auto-move selection; correct advances; wrong
  holds and counts; reveal; end-of-line; black-side drills (user plays Black).
- `evalProvider.test.ts`: the adapter maps a **recorded** chess-api.com response
  into `EngineEval` (sign convention included); no live network in tests.
- `ui-practice.test.ts`: entering practice renders the line picker; a wrong move
  triggers an `evaluate` call on the fake provider and renders the punishment; a
  correct move advances — all with a fake board + fake provider.
- Engine failure path: fake provider that rejects → UI still shows the book move
  and a graceful note.

## Risks & mitigations

- **chess-api.com shape/sign uncertainty.** Mitigation: first plan step is a
  live probe; the `EvalProvider` interface isolates it, and stockfish.online is a
  confirmed drop-in.
- **Free third-party engine longevity/limits.** Mitigation: pluggable provider +
  localStorage cache + engine only on mistakes (low volume) + graceful
  degradation; bundled-WASM fallback documented for later.
- **Movable board is new surface.** Mitigation: thin `board.ts` extension behind
  the same injected-factory pattern; drill logic is pure and tested without it.
- **Scope creep toward SRS.** Mitigation: explicitly deferred; v1 persistence is
  completed-lines only.
