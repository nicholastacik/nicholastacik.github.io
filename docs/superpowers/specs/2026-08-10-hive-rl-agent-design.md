# Hive Deep-RL Agent — Project Design + Phase 1 (Game Engine)

**Date:** 2026-08-10
**Status:** Approved pending user review

## Overview

Build an AlphaZero-style deep reinforcement learning agent that plays **Hive**
(base game + Ladybug + Mosquito expansions), and ship an interactive Quarto post
about how it was made. The framing is a **faithful AlphaZero reproduction as a
learning exercise**: correctness and pedagogy of the pipeline (self-play, MCTS,
replay buffer, temperature schedule, Dirichlet noise) matter more than squeezing
out Elo. Strength is a welcome byproduct.

### Deliverables

- A blog post (`posts/hive/index.qmd`) narrating the build, with a self-play
  performance graph.
- An interactive static page where a visitor plays against a chosen version of
  the agent, running entirely **client-side in the browser**.

### The load-bearing constraint

The site is a **static Quarto build published to GitHub Pages — no server.** The
trained agent must therefore run **entirely in the browser**: no Python backend
to call. This forces the network to stay small enough to export (ONNX Runtime
Web or TF.js) and run MCTS in JS within a ~1s per-move budget. This single fact
shapes model size, search depth, and how the browser gets a game engine.

### Ruleset

Base game + **Ladybug** + **Mosquito**. Neither expansion piece relocates
another piece, so the core invariants (one hive; a piece never moves another)
hold. **13 pieces per side:** 1 Queen, 2 Spider, 2 Beetle, 3 Grasshopper, 3 Ant,
1 Ladybug, 1 Mosquito.

## Project decomposition

Four phases, each its own spec → plan → build cycle. The blog post is the
wrapper, not a separate workstream — its replay viewer is built from artifacts
(game traces, metrics) we need for debugging anyway.

1. **Game engine** *(this spec)* — correct, fast, tested Hive rules in Python.
2. **Model + search** — policy/value network + MCTS (AlphaZero recipe).
3. **Self-play training loop + performance metrics** — the offline improvement
   curve that becomes the post's headline graph.
4. **Browser inference + interactive play** — export the net, run MCTS in JS,
   build the playable page.

Deferred decisions (recorded now, resolved in their phase):

- **Action-space tensor layout** (Phase 2): the exact fixed-size policy head
  encoding. Phase 1 exposes moves as structured relative-notation objects that
  will map cleanly onto it.
- **Browser-engine strategy** (Phase 4): single source of truth via Rust→WASM /
  Pyodide, versus a compact hand-written TS port validated against golden game
  traces exported from the Python engine. Not solved now; the Python engine
  commits us to nothing here.

---

## Phase 1 — Game Engine

### Purpose

A correct, fast, thoroughly-tested Hive engine exposing exactly what the
self-play loop needs: current state, legal-move generation, move application,
terminal/winner detection, and canonical serialization. Written in Python
because it lives inside the training loop.

Success is checkable: **our perft numbers match Mzinga's** (see Validation).

### Representation

- **Axial hex coordinates `(q, r)`.** The board is `dict[(q, r) -> list[Piece]]`
  — a list because Beetles and Mosquitoes climb and stack on top of other pieces.
- `Piece = (color, type, id)`.
- `State` = board + side-to-move + each side's unplaced hand + move number +
  a history of position hashes (for repetition / draw detection).
- The board is **translation-invariant** (no fixed origin) with 6-fold
  rotational + reflection symmetry. We lean into this for symmetry-based data
  augmentation in Phase 2.

### Move encoding

A move is expressed in **relative / UHP notation**: "piece X → direction D of
reference piece Y" (e.g. `wA1 -bQ`), plus placement moves in the same form. The
engine computes internally in absolute `(q, r)` coordinates but **exposes and
serializes moves as relative notation** at the API boundary.

Rationale: relative notation is bounded and translation-invariant, so it maps
cleanly onto a fixed-size policy head in Phase 2; it is human-readable; and it
matches the Universal Hive Protocol used by Mzinga, our validation anchor.

### Modules

Each is small and independently testable.

- **`rules.py`** — shared invariants:
  - **One-hive connectivity**: no move may disconnect the hive. Enforced via an
    articulation-point (cut-vertex) check on the placed-pieces graph.
  - **Freedom to move / sliding**: a piece sliding at ground level cannot squeeze
    through a gap narrower than itself (physical-gap constraint between the two
    common neighbors of source and target).
  - **Placement legality**: a newly placed piece touches only its own color
    (except the first move of each side); the Queen must be placed by each side's
    fourth move; no non-placement moves are legal until that side's Queen is down.
- **`movers.py`** — one generator per piece type:
  - **Queen** — one slide step.
  - **Ant** — any number of slide steps around the hive perimeter.
  - **Spider** — exactly three slide steps, no backtracking / revisiting.
  - **Grasshopper** — jump in a straight line over ≥1 contiguous piece to the
    first empty hex.
  - **Beetle** — one step; may climb onto and move across the top of the hive.
  - **Ladybug** — exactly three steps: two on top of the hive, then one down.
  - **Mosquito** — copies the movement of each piece it is currently adjacent to;
    while stacked on top it moves as a Beetle; adjacent only to a Mosquito, it
    cannot move.
- **`game.py`** — the `Game` wrapper: `legal_moves()`, `apply(move)`, and
  `result()`. Win = a Queen is fully surrounded (all six neighbors occupied);
  draw = both Queens surrounded on the same turn, or **threefold repetition**.
  (Repetition draws are not in the paper rules — Hive's only official draw is
  simultaneous surround — but they are the standard AI/competitive convention,
  matching BoardSpace/Mzinga, and are necessary to terminate otherwise-infinite
  self-play games.)
- **`notation.py`** — parse/format UHP-style move notation **and full-state UHP
  GameStrings** (the engine's canonical state serialization, reused for golden
  trace fixtures); **Zobrist hashing** of positions for repetition detection and
  symmetry canonicalization.

### Validation

**Anchor: [Mzinga](https://github.com/jonthysell/Mzinga)** — the canonical
open-source Hive engine, which defines the Universal Hive Protocol (UHP) and
supports the Ladybug + Mosquito expansions.

- Adopt **UHP notation** as our move format.
- **Perft tests**: count legal move sequences to depth N from fixed positions and
  match Mzinga's numbers. A matching perft is strong evidence of correctness.
- **Recorded-game replays**: feed known games through the engine, asserting every
  move is legal and the terminal result matches.

Mzinga is a **test-time dependency only** — we shell out to it in tests, never at
runtime. (A .NET engine; test setup documents installing it.)

### Testing tiers

1. **Per-mover unit tests** on hand-built positions (each piece's movement in
   isolation, plus edge cases: pinned pieces, gates, stacks).
2. **Perft** match vs. Mzinga.
3. **Recorded-game replays** vs. Mzinga / BoardSpace traces.
4. **Property tests**: the hive stays connected after every legal move;
   `apply` → `undo` round-trips to an identical state; move generation is
   deterministic.

### Performance stance

Correctness first, then profile. The hot path is the connectivity +
sliding checks inside move generation. Optimize those (and only those) if
self-play throughput demands it — no premature Cython/numba.

## Out of scope (Phase 1)

- The neural network, MCTS, and any training (Phase 2–3).
- The action-space tensor layout (Phase 2).
- Any browser / JS code (Phase 4).
- The Pillbug and other expansion pieces.

## Success criteria

- Perft matches Mzinga to the tested depth for base + Ladybug + Mosquito.
- A recorded game replays with every move legal and the correct terminal result.
- Property tests pass (connectivity, apply/undo, determinism).
- The public API (`legal_moves` / `apply` / `result` / serialize) is stable
  enough for the Phase-2 self-play loop to consume without changes.
