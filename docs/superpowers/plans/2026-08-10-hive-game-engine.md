# Hive Game Engine (Phase 1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A correct, tested Python implementation of Hive (base + Ladybug + Mosquito) exposing legal-move generation, move application/undo, terminal detection, and UHP serialization — everything the Phase-2 self-play loop needs.

**Architecture:** A `hive/` package split by responsibility: hex geometry (`hexes`), state/pieces (`state`), the shared physical rules (`rules`), per-piece move generators (`movers`), the game wrapper with make/unmake (`game`), and UHP notation + position hashing (`notation`). Correctness is gated by matching **Mzinga** perft counts (Mzinga is a test-only dependency spoken to over the Universal Hive Protocol).

**Tech Stack:** Python ≥3.12, `uv` for env, `pytest` for tests, `ruff` for lint/format. Mzinga (.NET) invoked as a subprocess in tests only.

**Spec:** `docs/superpowers/specs/2026-08-10-hive-rl-agent-design.md`

## Global Constraints

- Ruleset: **base + Ladybug + Mosquito**. No Pillbug. 13 pieces/side: 1 Queen (Q), 2 Spider (S), 2 Beetle (B), 3 Grasshopper (G), 3 Ant (A), 1 Ladybug (L), 1 Mosquito (M).
- Package lives at repo-root `hive/` (mirrors `montreal_events/`, `ptcg/`). Tests in `hive/tests/`.
- Coordinates: **axial `(q, r)`**, `int` tuples. Six directions in ring (clockwise) order: `((1,0),(1,-1),(0,-1),(-1,0),(-1,1),(0,1))`.
- Win = a Queen fully surrounded (all 6 neighbors occupied). Draw = both Queens surrounded on the same move, **or threefold repetition** (pragmatic AI convention, not paper rules — required to terminate self-play).
- White moves first (UHP convention). A player with no legal move **must pass**.
- Queen-may-not-be-placed-on-a-player's-first-move: **configurable flag `queen_first_move_allowed`**, default **False** to match Mzinga's default ("Tournament" is separate; this is the base "no Queen first" rule Mzinga enforces by default). Reconcile against Mzinga in Task 14; flip the default if perft disagrees.
- Correctness oracle: **Mzinga perft** over UHP. Mzinga is invoked in tests only, never at runtime.
- Mutable make/unmake API (`Game.push`/`Game.pop`) — the Phase-2 MCTS needs cheap undo, not state copies.
- Env: `uv run --group hive pytest hive/`. Lint: `uvx ruff check hive/`.
- Commit style: `feat(hive): ...` (code), `test(hive): ...`, `chore(hive): ...`. **Do NOT push** (`main` auto-deploys the site and carries unrelated unpushed commits; pushing is the user's call). End every commit message with:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Per user prefs: no docstrings/type-hints/comments beyond what the code needs to be clear; no speculative error handling on internal code.

## File structure

- `hive/__init__.py` — package marker; re-export `Game`, `State`, `Move`. *Create.*
- `hive/hexes.py` — axial geometry: directions, neighbors, common neighbors, adjacency. Pure, no game concepts. *Create.*
- `hive/state.py` — `Color`, `Bug`, `Piece`, `Board`, `State`, starting hands. *Create.*
- `hive/rules.py` — one-hive connectivity, lift check, ground-slide gate, climb gate, placeable cells. *Create.*
- `hive/movers.py` — one destination generator per bug + `MOVER_BY_BUG`. *Create.*
- `hive/game.py` — `Move`, `Result`, `Game` (legal_moves / push / pop / result). *Create.*
- `hive/notation.py` — UHP move + GameString (de)serialization, translation-normalized position key. *Create.*
- `hive/perft.py` — `perft(game, depth)`. *Create.*
- `hive/tests/__init__.py`, `hive/tests/conftest.py` (Mzinga fixture), `hive/tests/test_*.py`. *Create.*
- `pyproject.toml` — add `hive` dependency group + pytest `pythonpath`. *Modify.*

---

### Task 1: Package scaffold + hex geometry

**Files:**
- Create: `hive/__init__.py`, `hive/hexes.py`, `hive/tests/__init__.py`, `hive/tests/test_hexes.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: nothing.
- Produces: `Hex = tuple[int,int]`; `DIRECTIONS: tuple[Hex,...]` (6, ring order); `add(a,b)->Hex`; `neighbors(h)->list[Hex]` (6, ring order); `is_adjacent(a,b)->bool`; `common_neighbors(a,b)->tuple[Hex,Hex]` (the two cells adjacent to both — a,b must be adjacent).

- [ ] **Step 1: Add the hive dep group + pytest config to `pyproject.toml`**

Add under `[dependency-groups]`:
```toml
hive = ["pytest>=8"]
```
Add (or extend) at the end of the file:
```toml
[tool.pytest.ini_options]
pythonpath = ["."]
```

- [ ] **Step 2: Write the failing test**

`hive/tests/test_hexes.py`:
```python
from hive.hexes import DIRECTIONS, add, neighbors, is_adjacent, common_neighbors


def test_six_directions_all_adjacent_to_origin():
    assert len(DIRECTIONS) == 6
    assert len(set(DIRECTIONS)) == 6
    for d in DIRECTIONS:
        assert is_adjacent((0, 0), add((0, 0), d))


def test_neighbors_are_the_six_directions():
    assert set(neighbors((0, 0))) == set(DIRECTIONS)


def test_common_neighbors_are_the_two_ring_adjacent_cells():
    # East neighbor of origin; its two shared cells are NE and SE of origin.
    a, b = (0, 0), (1, 0)
    common = set(common_neighbors(a, b))
    assert common == {(1, -1), (0, 1)}
    for c in common:
        assert is_adjacent(a, c) and is_adjacent(b, c)


def test_non_adjacent_is_false():
    assert not is_adjacent((0, 0), (2, 0))
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run --group hive pytest hive/tests/test_hexes.py -q`
Expected: FAIL (`ModuleNotFoundError: hive.hexes`).

- [ ] **Step 4: Implement `hive/hexes.py`**

```python
Hex = tuple[int, int]

DIRECTIONS: tuple[Hex, ...] = ((1, 0), (1, -1), (0, -1), (-1, 0), (-1, 1), (0, 1))


def add(a: Hex, b: Hex) -> Hex:
    return (a[0] + b[0], a[1] + b[1])


def neighbors(h: Hex) -> list[Hex]:
    return [add(h, d) for d in DIRECTIONS]


def is_adjacent(a: Hex, b: Hex) -> bool:
    return (b[0] - a[0], b[1] - a[1]) in DIRECTIONS


def common_neighbors(a: Hex, b: Hex) -> tuple[Hex, Hex]:
    i = DIRECTIONS.index((b[0] - a[0], b[1] - a[1]))
    return add(a, DIRECTIONS[(i - 1) % 6]), add(a, DIRECTIONS[(i + 1) % 6])
```
Create empty `hive/__init__.py` and `hive/tests/__init__.py` (leave re-exports for Task 6 when `Game` exists).

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run --group hive pytest hive/tests/test_hexes.py -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add hive/hexes.py hive/__init__.py hive/tests/__init__.py hive/tests/test_hexes.py pyproject.toml
git commit -m "feat(hive): axial hex geometry + package scaffold

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Pieces, board, and state

**Files:**
- Create: `hive/state.py`, `hive/tests/test_state.py`

**Interfaces:**
- Consumes: `hive.hexes` (`Hex`, `neighbors`).
- Produces:
  - `class Color(IntEnum)`: `WHITE=0`, `BLACK=1`; property `other`.
  - `class Bug(Enum)`: `QUEEN,ANT,SPIDER,GRASSHOPPER,BEETLE,LADYBUG,MOSQUITO`; each value is its UHP char `"Q","A","S","G","B","L","M"`.
  - `STARTING_COUNTS: dict[Bug,int]` = Q1 A3 S2 B2 G3 L1 M1.
  - `@dataclass(frozen=True) class Piece`: `color: Color`, `bug: Bug`, `index: int`; `__str__` → e.g. `"wA1"`, `"bQ"` (index omitted only when the bug's starting count is 1, matching UHP: Q/L/M have no numeral).
  - `class Board`: wraps `dict[Hex, list[Piece]]`. Methods: `top(h)->Piece|None`, `height(h)->int`, `is_occupied(h)->bool`, `cells()->list[Hex]` (occupied), `place(h,piece)`, `pop(h)->Piece`, `copy()->Board`, `find(piece)->Hex|None`. Bottom of stack = list[0], top = list[-1].
  - `@dataclass class State`: `board: Board`, `to_move: Color`, `unplaced: dict[Color,list[Piece]]`, `move_number: int` (0-based ply count). Classmethod `initial(queen_first_move_allowed: bool=False)->State`. Method `queen_placed(color)->bool`.
  - `position_key(state)->int` — a **translation-invariant** hash of the position (normalize so `min(q)=min(r)=0` over occupied cells), including every stack bottom→top, side-to-move, and each side's unplaced multiset. Lives here (not in `notation`) because it only needs `State`, so `Game` can import it without a circular dependency on `notation`.

- [ ] **Step 1: Write the failing test**

`hive/tests/test_state.py`:
```python
from hive.state import Color, Bug, Piece, Board, State, STARTING_COUNTS


def test_starting_counts_total_13_per_side():
    assert sum(STARTING_COUNTS.values()) == 13
    assert STARTING_COUNTS[Bug.ANT] == 3 and STARTING_COUNTS[Bug.QUEEN] == 1


def test_piece_str_uhp_style():
    assert str(Piece(Color.WHITE, Bug.ANT, 1)) == "wA1"
    assert str(Piece(Color.BLACK, Bug.QUEEN, 1)) == "bQ"
    assert str(Piece(Color.WHITE, Bug.MOSQUITO, 1)) == "wM"


def test_board_stacking_top_and_height():
    b = Board()
    b.place((0, 0), Piece(Color.WHITE, Bug.ANT, 1))
    b.place((0, 0), Piece(Color.BLACK, Bug.BEETLE, 1))
    assert b.height((0, 0)) == 2
    assert b.top((0, 0)) == Piece(Color.BLACK, Bug.BEETLE, 1)
    assert b.pop((0, 0)) == Piece(Color.BLACK, Bug.BEETLE, 1)
    assert b.height((0, 0)) == 1


def test_initial_state_hands_and_turn():
    s = State.initial()
    assert s.to_move == Color.WHITE
    assert len(s.unplaced[Color.WHITE]) == 13
    assert s.board.cells() == []
    assert not s.queen_placed(Color.WHITE)


def test_color_other():
    assert Color.WHITE.other == Color.BLACK


def test_position_key_translation_invariant():
    from hive.state import position_key
    s1 = State.initial()
    s1.board.place((0, 0), Piece(Color.WHITE, Bug.ANT, 1))
    s1.board.place((1, 0), Piece(Color.BLACK, Bug.ANT, 1))
    s2 = State.initial()
    s2.board.place((5, -2), Piece(Color.WHITE, Bug.ANT, 1))
    s2.board.place((6, -2), Piece(Color.BLACK, Bug.ANT, 1))
    for s in (s1, s2):
        s.unplaced[Color.WHITE].remove(Piece(Color.WHITE, Bug.ANT, 1))
        s.unplaced[Color.BLACK].remove(Piece(Color.BLACK, Bug.ANT, 1))
    assert position_key(s1) == position_key(s2)


def test_position_key_distinguishes_side_to_move():
    from hive.state import position_key
    s = State.initial()
    k1 = position_key(s)
    s.to_move = Color.BLACK
    assert position_key(s) != k1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --group hive pytest hive/tests/test_state.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `hive/state.py`**

```python
from dataclasses import dataclass, field
from enum import Enum, IntEnum

from hive.hexes import Hex


class Color(IntEnum):
    WHITE = 0
    BLACK = 1

    @property
    def other(self) -> "Color":
        return Color.BLACK if self is Color.WHITE else Color.WHITE

    @property
    def prefix(self) -> str:
        return "w" if self is Color.WHITE else "b"


class Bug(Enum):
    QUEEN = "Q"
    ANT = "A"
    SPIDER = "S"
    GRASSHOPPER = "G"
    BEETLE = "B"
    LADYBUG = "L"
    MOSQUITO = "M"


STARTING_COUNTS: dict[Bug, int] = {
    Bug.QUEEN: 1, Bug.ANT: 3, Bug.SPIDER: 2, Bug.BEETLE: 2,
    Bug.GRASSHOPPER: 3, Bug.LADYBUG: 1, Bug.MOSQUITO: 1,
}


@dataclass(frozen=True)
class Piece:
    color: Color
    bug: Bug
    index: int

    def __str__(self) -> str:
        num = "" if STARTING_COUNTS[self.bug] == 1 else str(self.index)
        return f"{self.color.prefix}{self.bug.value}{num}"


class Board:
    def __init__(self) -> None:
        self._stacks: dict[Hex, list[Piece]] = {}

    def top(self, h: Hex) -> Piece | None:
        s = self._stacks.get(h)
        return s[-1] if s else None

    def height(self, h: Hex) -> int:
        return len(self._stacks.get(h, ()))

    def is_occupied(self, h: Hex) -> bool:
        return h in self._stacks

    def cells(self) -> list[Hex]:
        return list(self._stacks)

    def place(self, h: Hex, piece: Piece) -> None:
        self._stacks.setdefault(h, []).append(piece)

    def pop(self, h: Hex) -> Piece:
        s = self._stacks[h]
        piece = s.pop()
        if not s:
            del self._stacks[h]
        return piece

    def find(self, piece: Piece) -> Hex | None:
        for h, s in self._stacks.items():
            if piece in s:
                return h
        return None

    def copy(self) -> "Board":
        b = Board()
        b._stacks = {h: list(s) for h, s in self._stacks.items()}
        return b


def _starting_hand(color: Color) -> list[Piece]:
    return [Piece(color, bug, i + 1)
            for bug, n in STARTING_COUNTS.items() for i in range(n)]


@dataclass
class State:
    board: Board
    to_move: Color
    unplaced: dict[Color, list[Piece]]
    move_number: int
    queen_first_move_allowed: bool = False

    @classmethod
    def initial(cls, queen_first_move_allowed: bool = False) -> "State":
        return cls(
            board=Board(),
            to_move=Color.WHITE,
            unplaced={c: _starting_hand(c) for c in Color},
            move_number=0,
            queen_first_move_allowed=queen_first_move_allowed,
        )

    def queen_placed(self, color: Color) -> bool:
        queen = Piece(color, Bug.QUEEN, 1)
        return all(queen != p for p in self.unplaced[color])


def position_key(state: State) -> int:
    cells = state.board.cells()
    if cells:
        minq = min(q for q, _ in cells)
        minr = min(r for _, r in cells)
    else:
        minq = minr = 0
    stacks = tuple(sorted(
        (q - minq, r - minr, tuple(str(p) for p in state.board._stacks[(q, r)]))
        for (q, r) in cells
    ))
    unplaced = tuple(sorted(
        (int(c), tuple(sorted(str(p) for p in state.unplaced[c])))
        for c in Color
    ))
    return hash((stacks, int(state.to_move), unplaced))
```

- [ ] **Step 4: Run tests**

Run: `uv run --group hive pytest hive/tests/test_state.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hive/state.py hive/tests/test_state.py
git commit -m "feat(hive): pieces, stacking board, and game state

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Physical rules — connectivity, lift, slide & climb gates

**Files:**
- Create: `hive/rules.py`, `hive/tests/test_rules.py`

**Interfaces:**
- Consumes: `hive.hexes` (`neighbors`, `common_neighbors`, `is_adjacent`), `hive.state` (`Board`).
- Produces:
  - `is_connected(board)->bool` — all occupied cells form one component (footprint adjacency).
  - `can_lift(board, src)->bool` — True if `height(src)>1`, else True iff removing `src` leaves the footprint connected.
  - `can_slide(board, src, dst)->bool` — ground-slide gate: `dst` empty, adjacent to `src`, and **exactly one** of `common_neighbors(src,dst)` is occupied. (Caller passes a board with the moving piece already lifted.)
  - `can_climb(board, src, dst)->bool` — height gate: with `s=height(src)-1` (surface left behind), `d=height(dst)` (surface landed on), and gate heights `g1,g2`: not blocked iff `min(g1,g2) <= max(s,d)`. (Caller passes a board with the moving piece still ON at `src`, i.e. do NOT lift first — `height(src)` includes the mover.)
  - `placeable_cells(board, color, free_placement)->set[Hex]` — empty cells adjacent to ≥1 occupied cell such that (if not `free_placement`) no neighbor's top piece is the enemy color. `free_placement=True` for the first ply of each side.

- [ ] **Step 1: Write the failing test**

`hive/tests/test_rules.py`:
```python
from hive.state import Board, Piece, Color, Bug
from hive.rules import is_connected, can_lift, can_slide, can_climb, placeable_cells

W, B = Color.WHITE, Color.BLACK


def _wp(i=1, bug=Bug.ANT):
    return Piece(W, bug, i)


def test_is_connected_true_and_false():
    b = Board()
    b.place((0, 0), _wp(1))
    b.place((1, 0), _wp(2))
    assert is_connected(b)
    b2 = Board()
    b2.place((0, 0), _wp(1))
    b2.place((3, 0), _wp(2))  # gap
    assert not is_connected(b2)


def test_can_lift_articulation_piece_is_pinned():
    # Line of 3: the middle piece is a cut vertex -> cannot lift.
    b = Board()
    b.place((0, 0), _wp(1))
    b.place((1, 0), _wp(2))
    b.place((2, 0), _wp(3))
    assert not can_lift(b, (1, 0))
    assert can_lift(b, (0, 0))  # an end piece


def test_can_lift_stacked_piece_always_free():
    b = Board()
    b.place((0, 0), _wp(1))
    b.place((1, 0), _wp(2))
    b.place((1, 0), Piece(B, Bug.BEETLE, 1))  # beetle on top of a cut vertex
    assert can_lift(b, (1, 0))


def test_can_slide_gate():
    # src=(0,0), dst=(1,0); gate cells (1,-1) and (0,1).
    b = Board()
    b.place((1, -1), _wp(1))          # exactly one gate occupied -> can slide
    assert can_slide(b, (0, 0), (1, 0))
    b.place((0, 1), _wp(2))           # now both gates occupied -> blocked
    assert not can_slide(b, (0, 0), (1, 0))
    b3 = Board()                      # both gates empty -> blocked (would detach)
    assert not can_slide(b3, (0, 0), (1, 0))


def test_can_climb_gate_blocks_between_two_tall_stacks():
    b = Board()
    # A beetle at (0,0) height 1 wants (1,0) height 0; gates each height 2 -> blocked.
    b.place((0, 0), Piece(W, Bug.BEETLE, 1))
    for g in [(1, -1), (0, 1)]:
        b.place(g, _wp())
        b.place(g, _wp())
    assert not can_climb(b, (0, 0), (1, 0))


def test_placeable_cells_exclude_enemy_adjacent():
    b = Board()
    b.place((0, 0), Piece(W, Bug.QUEEN, 1))
    b.place((1, 0), Piece(B, Bug.QUEEN, 1))
    cells = placeable_cells(b, W, free_placement=False)
    assert (2, 0) not in cells          # touches only black -> illegal for white
    assert (-1, 0) in cells             # touches only white -> legal
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --group hive pytest hive/tests/test_rules.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `hive/rules.py`**

```python
from hive.hexes import Hex, neighbors, common_neighbors, is_adjacent
from hive.state import Board, Color


def is_connected(board: Board) -> bool:
    cells = board.cells()
    if len(cells) <= 1:
        return True
    seen = {cells[0]}
    stack = [cells[0]]
    occupied = set(cells)
    while stack:
        cur = stack.pop()
        for nb in neighbors(cur):
            if nb in occupied and nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return len(seen) == len(occupied)


def can_lift(board: Board, src: Hex) -> bool:
    if board.height(src) > 1:
        return True
    b = board.copy()
    b.pop(src)
    return is_connected(b)


def can_slide(board: Board, src: Hex, dst: Hex) -> bool:
    if board.is_occupied(dst) or not is_adjacent(src, dst):
        return False
    g1, g2 = common_neighbors(src, dst)
    return board.is_occupied(g1) != board.is_occupied(g2)


def can_climb(board: Board, src: Hex, dst: Hex) -> bool:
    if not is_adjacent(src, dst):
        return False
    s = board.height(src) - 1
    d = board.height(dst)
    g1, g2 = common_neighbors(src, dst)
    return min(board.height(g1), board.height(g2)) <= max(s, d)


def placeable_cells(board: Board, color: Color, free_placement: bool) -> set[Hex]:
    if not board.cells():
        return {(0, 0)}
    empty_adjacent: set[Hex] = set()
    for cell in board.cells():
        for nb in neighbors(cell):
            if not board.is_occupied(nb):
                empty_adjacent.add(nb)
    if free_placement:
        return empty_adjacent
    result = set()
    for cell in empty_adjacent:
        tops = [board.top(nb) for nb in neighbors(cell) if board.is_occupied(nb)]
        if tops and all(t.color == color for t in tops):
            result.add(cell)
    return result
```

- [ ] **Step 4: Run tests**

Run: `uv run --group hive pytest hive/tests/test_rules.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hive/rules.py hive/tests/test_rules.py
git commit -m "feat(hive): one-hive connectivity, lift, slide and climb gates

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Sliding movers — Queen, Ant, Spider

**Files:**
- Create: `hive/movers.py`, `hive/tests/test_movers_slide.py`

**Interfaces:**
- Consumes: `hive.hexes` (`neighbors`, `is_adjacent`), `hive.state` (`Board`), `hive.rules` (`can_slide`).
- Produces (all take a board where the moving piece has been **lifted** off `src`, and return a `set[Hex]` of destinations):
  - `_slide_steps(board, src)->set[Hex]` — one-step slide neighbors of `src` reachable by the slide gate.
  - `queen_moves(board, src)->set[Hex]` — `_slide_steps`.
  - `ant_moves(board, src)->set[Hex]` — all cells reachable by chained slides (BFS over the perimeter), excluding `src`.
  - `spider_moves(board, src)->set[Hex]` — cells reachable by exactly 3 slide steps with no cell revisited on a path.

- [ ] **Step 1: Write the failing test**

`hive/tests/test_movers_slide.py`:
```python
from hive.state import Board, Piece, Color, Bug
from hive.movers import queen_moves, ant_moves, spider_moves

W = Color.WHITE


def _ant(i):
    return Piece(W, Bug.ANT, i)


def _lifted_line(n):
    # n pieces in a horizontal line at (0,0)..(n-1,0); return board + src=(0,0)
    # with the (0,0) piece already lifted.
    b = Board()
    for i in range(n):
        b.place((i, 0), _ant(i + 1))
    b.pop((0, 0))
    return b


def test_queen_one_step_around_neighbor():
    b = _lifted_line(2)  # pieces at (1,0); moving piece was (0,0)
    # From (0,0), queen can slide to the two cells that keep one-gate contact.
    assert queen_moves(b, (0, 0)) == {(1, -1), (0, 1)}


def test_ant_walks_full_perimeter():
    b = _lifted_line(2)
    # Ant can reach every empty cell around the single remaining piece at (1,0).
    moves = ant_moves(b, (0, 0))
    assert (2, 0) in moves and (1, 1) in moves and (1, -1) in moves
    assert (0, 0) not in moves


def test_spider_exactly_three_steps():
    b = _lifted_line(4)  # remaining pieces at (1,0),(2,0),(3,0)
    moves = spider_moves(b, (0, 0))
    # Three slides along the perimeter of a 3-long wall from the (0,0) side.
    assert all(m != (0, 0) for m in moves)
    assert len(moves) >= 1
    # Every spider destination is reachable by an ant (sanity: subset of slide-reachable).
    assert moves <= ant_moves(b, (0, 0)) | {(0, 0)}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --group hive pytest hive/tests/test_movers_slide.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement the sliding movers in `hive/movers.py`**

```python
from hive.hexes import Hex, neighbors
from hive.state import Board
from hive.rules import can_slide


def _slide_steps(board: Board, src: Hex) -> set[Hex]:
    return {nb for nb in neighbors(src) if can_slide(board, src, nb)}


def queen_moves(board: Board, src: Hex) -> set[Hex]:
    return _slide_steps(board, src)


def ant_moves(board: Board, src: Hex) -> set[Hex]:
    seen: set[Hex] = set()
    frontier = [src]
    while frontier:
        cur = frontier.pop()
        for nxt in _slide_steps(board, cur):
            if nxt not in seen and nxt != src:
                seen.add(nxt)
                frontier.append(nxt)
    seen.discard(src)
    return seen


def spider_moves(board: Board, src: Hex) -> set[Hex]:
    results: set[Hex] = set()

    def walk(cur: Hex, path: tuple[Hex, ...]) -> None:
        if len(path) == 4:  # src + 3 steps
            results.add(cur)
            return
        for nxt in _slide_steps(board, cur):
            if nxt not in path:
                walk(nxt, path + (nxt,))

    walk(src, (src,))
    results.discard(src)
    return results
```
Note: callers (Task 6) must lift the moving piece before calling these. `can_slide` reads occupancy of gate cells, which is correct once the mover is lifted.

- [ ] **Step 4: Run tests**

Run: `uv run --group hive pytest hive/tests/test_movers_slide.py -q`
Expected: PASS. (If `test_spider_exactly_three_steps` counts differ, verify by hand against the wall geometry before adjusting — do not weaken the assertion to fit a bug.)

- [ ] **Step 5: Commit**

```bash
git add hive/movers.py hive/tests/test_movers_slide.py
git commit -m "feat(hive): sliding movers (queen, ant, spider)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Jump/climb movers — Grasshopper, Beetle, Ladybug, Mosquito

**Files:**
- Modify: `hive/movers.py`
- Create: `hive/tests/test_movers_special.py`

**Interfaces:**
- Consumes: additionally `hive.hexes` (`DIRECTIONS`, `add`), `hive.rules` (`can_climb`), `hive.state` (`Bug`, `Board`).
- Produces (added to `movers.py`):
  - `grasshopper_moves(board, src)->set[Hex]` — for each direction with an occupied immediate neighbor, jump in a straight line over contiguous occupied cells to the first empty cell.
  - `beetle_moves(board, src)->set[Hex]` — the 6 neighbors reachable respecting `can_climb`; when moving at ground level to a ground cell, additionally require the destination be adjacent to another occupied cell (stay connected). **Called with the moving piece still ON `src`** (climb gate needs its height).
  - `ladybug_moves(board, src)->set[Hex]` — exactly 3 steps: step 1 and 2 must land on top of pieces (occupied cells), step 3 must land on an empty cell; each step to an adjacent cell, no revisits.
  - `mosquito_moves(board, src, top_is_stacked, adjacent_bugs)->set[Hex]` — if `top_is_stacked` (mosquito is on top of the hive), behaves as beetle only; else the union of the movers of each distinct `Bug` in `adjacent_bugs` (a Mosquito neighbor contributes nothing).
  - `MOVER_BY_BUG: dict[Bug, callable]` mapping each non-mosquito bug to its `*_moves` function.

- [ ] **Step 1: Write the failing test**

`hive/tests/test_movers_special.py`:
```python
from hive.state import Board, Piece, Color, Bug
from hive.movers import (
    grasshopper_moves, beetle_moves, ladybug_moves, mosquito_moves,
)

W = Color.WHITE


def _p(bug, i=1):
    return Piece(W, bug, i)


def test_grasshopper_jumps_over_line_to_first_empty():
    b = Board()
    b.place((0, 0), _p(Bug.GRASSHOPPER))
    b.place((1, 0), _p(Bug.ANT, 1))
    b.place((2, 0), _p(Bug.ANT, 2))
    # jumps east over (1,0),(2,0) landing on (3,0)
    assert (3, 0) in grasshopper_moves(b, (0, 0))
    # no piece in other directions -> no jump there
    assert (0, -1) not in grasshopper_moves(b, (0, 0))


def test_beetle_can_climb_onto_neighbor():
    b = Board()
    b.place((0, 0), _p(Bug.BEETLE))
    b.place((1, 0), _p(Bug.ANT))
    assert (1, 0) in beetle_moves(b, (0, 0))  # climb on top


def test_ladybug_three_steps_two_on_top_one_down():
    b = Board()
    b.place((0, 0), _p(Bug.LADYBUG))
    b.place((1, 0), _p(Bug.ANT, 1))
    b.place((2, 0), _p(Bug.ANT, 2))
    dests = ladybug_moves(b, (0, 0))
    # Lands on an empty cell adjacent to the two-piece wall, reached over the top.
    assert (0, 0) not in dests
    assert dests  # non-empty
    assert all(not b.is_occupied(d) for d in dests)


def test_mosquito_copies_adjacent_bug_movement():
    b = Board()
    b.place((0, 0), _p(Bug.MOSQUITO))
    b.place((1, 0), _p(Bug.GRASSHOPPER))
    b.place((2, 0), _p(Bug.ANT))
    dests = mosquito_moves(b, (0, 0), top_is_stacked=False,
                           adjacent_bugs={Bug.GRASSHOPPER})
    assert (3, 0) in dests  # grasshopper-style jump east


def test_mosquito_next_to_only_mosquito_cannot_move():
    b = Board()
    b.place((0, 0), _p(Bug.MOSQUITO, 1))
    b.place((1, 0), Piece(W, Bug.MOSQUITO, 1))
    assert mosquito_moves(b, (0, 0), top_is_stacked=False,
                          adjacent_bugs=set()) == set()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --group hive pytest hive/tests/test_movers_special.py -q`
Expected: FAIL (`ImportError`/`AttributeError`).

- [ ] **Step 3: Implement the special movers in `hive/movers.py`**

Append:
```python
from hive.hexes import DIRECTIONS, add, is_adjacent
from hive.state import Bug
from hive.rules import can_climb


def grasshopper_moves(board: Board, src: Hex) -> set[Hex]:
    dests: set[Hex] = set()
    for d in DIRECTIONS:
        step = add(src, d)
        if not board.is_occupied(step):
            continue
        while board.is_occupied(step):
            step = add(step, d)
        dests.add(step)
    return dests


def beetle_moves(board: Board, src: Hex) -> set[Hex]:
    dests: set[Hex] = set()
    for nb in neighbors(src):
        if not can_climb(board, src, nb):
            continue
        if board.is_occupied(nb) or board.height(src) > 1:
            dests.add(nb)  # climbing onto/along the hive stays connected
        elif any(board.is_occupied(o) for o in neighbors(nb) if o != src):
            dests.add(nb)  # ground step that stays attached
    return dests


def ladybug_moves(board: Board, src: Hex) -> set[Hex]:
    results: set[Hex] = set()

    def step(cur: Hex, n: int, path: tuple[Hex, ...]) -> None:
        for nb in neighbors(cur):
            if nb in path:
                continue
            on_top = board.is_occupied(nb)
            if n < 2 and on_top:
                step(nb, n + 1, path + (nb,))
            elif n == 2 and not on_top and nb != src:
                results.add(nb)

    step(src, 0, (src,))
    return results


def mosquito_moves(board: Board, src: Hex, top_is_stacked: bool,
                   adjacent_bugs: set[Bug]) -> set[Hex]:
    if top_is_stacked:
        return beetle_moves(board, src)
    dests: set[Hex] = set()
    for bug in adjacent_bugs:
        if bug is Bug.MOSQUITO:
            continue
        dests |= MOVER_BY_BUG[bug](board, src)
    return dests


MOVER_BY_BUG = {
    Bug.QUEEN: queen_moves,
    Bug.ANT: ant_moves,
    Bug.SPIDER: spider_moves,
    Bug.GRASSHOPPER: grasshopper_moves,
    Bug.BEETLE: beetle_moves,
    Bug.LADYBUG: ladybug_moves,
}
```
Note the split calling convention (documented in Task 6): sliders/ladybug/grasshopper are called on a board with the mover **lifted**; beetle/mosquito(non-stacked) are called with the mover **still on** `src` (they read its height for the climb gate).

- [ ] **Step 4: Run tests**

Run: `uv run --group hive pytest hive/tests/test_movers_special.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hive/movers.py hive/tests/test_movers_special.py
git commit -m "feat(hive): grasshopper, beetle, ladybug, mosquito movers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Game wrapper — legal moves, make/unmake, terminal

**Files:**
- Create: `hive/game.py`, `hive/tests/test_game.py`
- Modify: `hive/__init__.py` (re-export `Game`, `Move`, `Result`, `State`)

**Interfaces:**
- Consumes: everything above.
- Produces:
  - `@dataclass(frozen=True) class Move`: `piece: Piece`, `dest: Hex | None`, `src: Hex | None`. Placement: `src is None`. Pass: `piece is None and dest is None` — expose singleton `PASS = Move(None, None, None)`.
  - `class Result(Enum)`: `WHITE_WINS`, `BLACK_WINS`, `DRAW`.
  - `class Game`: holds a `State`; `legal_moves()->list[Move]`; `push(move)->None`; `pop()->None`; `result()->Result|None` (None if ongoing); `is_terminal()->bool`. Keeps an internal undo stack + a position-count `Counter` for repetition.
  - Rules enforced in `legal_moves()`: before a side's Queen is placed no movement moves are legal; each side must place its Queen by its **4th** move (ply where that side has made 3 placements already → only Queen placements offered); `queen_first_move_allowed` gates Queen on ply 0/1; forced `PASS` only when no other move exists.

- [ ] **Step 1: Write the failing test**

`hive/tests/test_game.py`:
```python
from hive.game import Game, Move, Result, PASS
from hive.state import State, Piece, Color, Bug

W, B = Color.WHITE, Color.BLACK


def test_first_moves_are_placements_only_at_origin_then_adjacent():
    g = Game(State.initial())
    first = g.legal_moves()
    assert all(m.src is None for m in first)
    assert {m.dest for m in first} == {(0, 0)}
    # no Queen on the very first move (default rule)
    assert all(m.piece.bug is not Bug.QUEEN for m in first)


def test_queen_forced_by_fourth_move():
    # White places 3 non-queens; on its 4th move only Queen placements are legal.
    g = Game(State.initial())
    seq = [
        Move(Piece(W, Bug.ANT, 1), (0, 0), None),
        Move(Piece(B, Bug.ANT, 1), (1, 0), None),
        Move(Piece(W, Bug.SPIDER, 1), (-1, 0), None),
        Move(Piece(B, Bug.SPIDER, 1), (2, 0), None),
        Move(Piece(W, Bug.GRASSHOPPER, 1), (-2, 0), None),
        Move(Piece(B, Bug.GRASSHOPPER, 1), (3, 0), None),
    ]
    for m in seq:
        g.push(m)
    white_fourth = g.legal_moves()
    assert white_fourth and all(m.piece.bug is Bug.QUEEN for m in white_fourth)


def test_push_pop_round_trips_state():
    g = Game(State.initial())
    m = Move(Piece(W, Bug.ANT, 1), (0, 0), None)
    g.push(m)
    assert g.state.board.is_occupied((0, 0))
    g.pop()
    assert not g.state.board.is_occupied((0, 0))
    assert g.state.to_move == W and g.state.move_number == 0


def test_surrounded_queen_is_a_loss():
    # Build a position with white queen at origin surrounded by 6 black pieces.
    s = State.initial()
    s.board.place((0, 0), Piece(W, Bug.QUEEN, 1))
    from hive.hexes import neighbors
    for i, h in enumerate(neighbors((0, 0))):
        s.board.place(h, Piece(B, Bug.ANT, i + 1) if i < 3 else Piece(B, Bug.GRASSHOPPER, i - 2))
    g = Game(s)
    assert g.result() == Result.BLACK_WINS
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --group hive pytest hive/tests/test_game.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `hive/game.py`**

```python
from collections import Counter
from dataclasses import dataclass
from enum import Enum

from hive.hexes import Hex, neighbors
from hive.state import State, Piece, Color, Bug, position_key
from hive.rules import can_lift, placeable_cells
from hive.movers import MOVER_BY_BUG, beetle_moves, mosquito_moves


@dataclass(frozen=True)
class Move:
    piece: Piece | None
    dest: Hex | None
    src: Hex | None


PASS = Move(None, None, None)


class Result(Enum):
    WHITE_WINS = "w"
    BLACK_WINS = "b"
    DRAW = "draw"


def _placements_made(state: State, color: Color) -> int:
    from hive.state import STARTING_COUNTS
    total = sum(STARTING_COUNTS.values())
    return total - len(state.unplaced[color])


class Game:
    def __init__(self, state: State) -> None:
        self.state = state
        self._undo: list[tuple] = []
        self._history: Counter[int] = Counter()

    # --- move generation -------------------------------------------------
    def _placement_moves(self) -> list[Move]:
        s = self.state
        color = s.to_move
        made = _placements_made(s, color)
        cells = placeable_cells(s.board, color, free_placement=(made == 0))
        must_place_queen = (made == 3 and not s.queen_placed(color))
        moves = []
        for piece in _unique_placeable(s.unplaced[color]):
            if must_place_queen and piece.bug is not Bug.QUEEN:
                continue
            if piece.bug is Bug.QUEEN and made == 0 and not s.queen_first_move_allowed:
                continue
            for cell in cells:
                moves.append(Move(piece, cell, None))
        return moves

    def _movement_moves(self) -> list[Move]:
        s = self.state
        color = s.to_move
        if not s.queen_placed(color):
            return []
        moves = []
        for src in s.board.cells():
            top = s.board.top(src)
            if top.color != color:
                continue
            if not can_lift(s.board, src):
                continue
            moves.extend(self._moves_for_piece(top, src))
        return moves

    def _moves_for_piece(self, piece: Piece, src: Hex) -> list[Move]:
        board = self.state.board
        if piece.bug is Bug.BEETLE:
            dests = beetle_moves(board, src)
        elif piece.bug is Bug.MOSQUITO:
            stacked = board.height(src) > 1
            adj = {board.top(nb).bug for nb in neighbors(src) if board.is_occupied(nb)}
            dests = mosquito_moves(board, src, top_is_stacked=stacked, adjacent_bugs=adj)
        else:
            lifted = board.copy()
            lifted.pop(src)
            dests = MOVER_BY_BUG[piece.bug](lifted, src)
        return [Move(piece, d, src) for d in dests]

    def legal_moves(self) -> list[Move]:
        moves = self._placement_moves() + self._movement_moves()
        return moves or [PASS]

    # --- make / unmake ---------------------------------------------------
    def push(self, move: Move) -> None:
        s = self.state
        self._undo.append((move, s.to_move, s.move_number))
        if move is not PASS:
            if move.src is None:
                s.unplaced[move.piece.color].remove(move.piece)
                s.board.place(move.dest, move.piece)
            else:
                s.board.pop(move.src)
                s.board.place(move.dest, move.piece)
        s.to_move = s.to_move.other
        s.move_number += 1
        self._history[self._position_key()] += 1

    def pop(self) -> None:
        move, to_move, move_number = self._undo.pop()
        s = self.state
        self._history[self._position_key()] -= 1
        if move is not PASS:
            if move.src is None:
                s.board.pop(move.dest)
                s.unplaced[move.piece.color].append(move.piece)
            else:
                s.board.pop(move.dest)
                s.board.place(move.src, move.piece)
        s.to_move = to_move
        s.move_number = move_number

    def _position_key(self) -> int:
        return position_key(self.state)

    # --- terminal --------------------------------------------------------
    def _surrounded(self, color: Color) -> bool:
        q = Piece(color, Bug.QUEEN, 1)
        h = self.state.board.find(q)
        if h is None:
            return False
        return all(self.state.board.is_occupied(nb) for nb in neighbors(h))

    def result(self) -> Result | None:
        w = self._surrounded(Color.WHITE)
        b = self._surrounded(Color.BLACK)
        if w and b:
            return Result.DRAW
        if w:
            return Result.BLACK_WINS
        if b:
            return Result.WHITE_WINS
        if self._history[self._position_key()] >= 3:
            return Result.DRAW
        return None

    def is_terminal(self) -> bool:
        return self.result() is not None


def _unique_placeable(hand: list[Piece]) -> list[Piece]:
    seen: set[Bug] = set()
    out = []
    for p in hand:
        if p.bug not in seen:
            seen.add(p.bug)
            out.append(p)
    return out
```
Update `hive/__init__.py`:
```python
from hive.game import Game, Move, Result, PASS
from hive.state import State
```

- [ ] **Step 4: Run tests**

Run: `uv run --group hive pytest hive/tests/test_game.py -q`
Expected: PASS. (`position_key` comes from `hive.state`, already built in Task 2 — no dependency on Task 7 here.)

- [ ] **Step 5: Commit**

```bash
git add hive/game.py hive/__init__.py hive/tests/test_game.py
git commit -m "feat(hive): game wrapper — legal moves, make/unmake, terminal

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Notation — UHP move/GameString

**Files:**
- Create: `hive/notation.py`, `hive/tests/test_notation.py`

**Interfaces:**
- Consumes: `hive.state`, `hive.game` (`Move`, `PASS`), `hive.hexes`.
- Produces:
  - `move_to_uhp(game, move)->str` and `uhp_to_move(game, s)->Move` — UHP MoveString: `"<moving> <symbol><ref>"` / `"<moving> <ref><symbol>"`, `"<moving>"` alone for the first piece, `"pass"` for `PASS`. Direction symbols per UHP: prefix `-,/,\` and suffix `-,/,\` around the reference-piece string.
  - `game_string(game)->str` — `"Base+MLP;<state>;<turn>;<moves...>"` header compatible with UHP `newgame`/`play` round-tripping (exact form finalized against Mzinga in Task 8).

(`position_key` lives in `hive.state`, built in Task 2 — not here.)

- [ ] **Step 1: Write the failing test**

`hive/tests/test_notation.py`:
```python
from hive.state import State, Piece, Color, Bug
from hive.game import Game, Move, PASS
from hive.notation import move_to_uhp, uhp_to_move

W, B = Color.WHITE, Color.BLACK


def test_uhp_first_move_is_bare_piece():
    g = Game(State.initial())
    m = Move(Piece(W, Bug.SPIDER, 1), (0, 0), None)
    assert move_to_uhp(g, m) == "wS1"


def test_uhp_pass_roundtrip():
    g = Game(State.initial())
    assert move_to_uhp(g, PASS) == "pass"
    assert uhp_to_move(g, "pass") is PASS


def test_uhp_relative_placement_roundtrip():
    g = Game(State.initial())
    g.push(Move(Piece(W, Bug.SPIDER, 1), (0, 0), None))
    m = Move(Piece(B, Bug.ANT, 1), (1, 0), None)  # east of wS1
    s = move_to_uhp(g, m)
    assert "wS1" in s and s.split()[0] == "bA1"
    assert uhp_to_move(g, s) == m
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --group hive pytest hive/tests/test_notation.py -q`
Expected: FAIL (`ModuleNotFoundError`).

- [ ] **Step 3: Implement `hive/notation.py`**

```python
from hive.hexes import DIRECTIONS, add
from hive.state import Piece, Color, Bug
from hive.game import Move, PASS

# Map each axial direction index to (prefix_symbol, suffix_symbol). Exactly one
# is non-empty per direction. Reconciled against Mzinga in Task 8.
_DIR_TO_UHP = {
    (1, 0): ("", "-"),    # east: ref on the left, moving piece to its right
    (1, -1): ("", "/"),   # NE
    (0, -1): ("", "\\"),  # NW  -> actually ref-below; see reconciliation note
    (-1, 0): ("-", ""),   # west
    (-1, 1): ("/", ""),   # SW
    (0, 1): ("\\", ""),   # SE
}


def _piece_at_move_ref(game, move: Move) -> tuple[Piece, tuple[int, int]] | None:
    board = game.state.board
    if not board.cells():
        return None
    # a placement/move target: find an occupied neighbor of dest to reference.
    for d in DIRECTIONS:
        nb = add(move.dest, d)
        if board.is_occupied(nb) and nb != move.src:
            return board.top(nb), (d[0], d[1])
    # dest is under/onto a stack (beetle climbing onto an occupied cell)
    if board.is_occupied(move.dest):
        return board.top(move.dest), (0, 0)
    return None


def move_to_uhp(game, move: Move) -> str:
    if move is PASS:
        return "pass"
    moving = str(move.piece)
    ref = _piece_at_move_ref(game, move)
    if ref is None:
        return moving
    ref_piece, d = ref
    if d == (0, 0):
        return f"{moving} {ref_piece}"  # climbing onto the ref's cell
    inv = (-d[0], -d[1])  # direction from ref back to dest
    pre, suf = _DIR_TO_UHP[inv]
    return f"{moving} {pre}{ref_piece}{suf}"


def uhp_to_move(game, s: str) -> Move:
    if s.strip() == "pass":
        return PASS
    parts = s.split()
    moving = _parse_piece(parts[0])
    src = game.state.board.find(moving)
    if len(parts) == 1:
        return Move(moving, (0, 0), src)
    token = parts[1]
    pre = token[0] if token[0] in "-/\\" else ""
    suf = token[-1] if token[-1] in "-/\\" else ""
    ref_str = token.strip("-/\\")
    ref = _parse_piece(ref_str)
    ref_cell = game.state.board.find(ref)
    if not pre and not suf:
        dest = ref_cell  # climb onto ref
    else:
        inv = next(k for k, v in _DIR_TO_UHP.items() if v == (pre, suf))
        d = (-inv[0], -inv[1])
        dest = add(ref_cell, d)
    return Move(moving, dest, src)


def _parse_piece(tok: str) -> Piece:
    color = Color.WHITE if tok[0] == "w" else Color.BLACK
    bug = Bug(tok[1])
    idx = int(tok[2:]) if len(tok) > 2 else 1
    return Piece(color, bug, idx)
```
Note: the exact prefix/suffix→direction assignment is finalized in Task 8 by round-tripping through Mzinga; the round-trip tests above only require internal consistency, which holds for any bijection.

- [ ] **Step 4: Run tests**

Run: `uv run --group hive pytest hive/tests/test_notation.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add hive/notation.py hive/tests/test_notation.py
git commit -m "feat(hive): translation-invariant position key + UHP notation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Perft + Mzinga validation (correctness gate)

**Files:**
- Create: `hive/perft.py`, `hive/tests/conftest.py`, `hive/tests/test_perft.py`
- Possibly modify: `hive/rules.py`, `hive/movers.py`, `hive/notation.py` (fix any gate/off-by-one/direction bugs perft surfaces)

**Interfaces:**
- Consumes: `hive.game.Game`, `hive.notation` (UHP), `hive.state.State`.
- Produces: `perft(game, depth)->int` — number of distinct legal move *sequences* of length `depth` from the current position (standard perft: sum over legal moves of `perft(child, depth-1)`, `perft(_,0)=1`; a forced `PASS` counts as one move).

- [ ] **Step 1: Implement `hive/perft.py`**

```python
from hive.game import Game


def perft(game: Game, depth: int) -> int:
    if depth == 0:
        return 1
    if game.is_terminal():
        return 0
    total = 0
    for move in game.legal_moves():
        game.push(move)
        total += perft(game, depth - 1)
        game.pop()
    return total
```

- [ ] **Step 2: Write the Mzinga fixture + a self-consistency test first**

`hive/tests/conftest.py` — a `mzinga` fixture that locates `MzingaEngine` (env var `MZINGA_ENGINE` → path) and speaks UHP over stdin/stdout (`newgame Base+MLP`, `play <move>`, `validmoves`, `bestmove`), skipping the test with a clear message if the binary is absent:
```python
import os, shutil, subprocess
import pytest


class Mzinga:
    def __init__(self, path):
        self.p = subprocess.Popen([path], stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, text=True, bufsize=1)
        self._read_until_ok()

    def _read_until_ok(self):
        lines = []
        for line in self.p.stdout:
            if line.strip() == "ok":
                return lines
            lines.append(line.rstrip("\n"))
        raise RuntimeError("Mzinga closed unexpectedly")

    def cmd(self, text):
        self.p.stdin.write(text + "\n")
        self.p.stdin.flush()
        return self._read_until_ok()

    def close(self):
        try:
            self.cmd("exit")
        except Exception:
            self.p.kill()


@pytest.fixture(scope="session")
def mzinga():
    path = os.environ.get("MZINGA_ENGINE") or shutil.which("MzingaEngine")
    if not path:
        pytest.skip("MzingaEngine not found (set MZINGA_ENGINE=/path/to/MzingaEngine)")
    engine = Mzinga(path)
    yield engine
    engine.close()
```
`hive/tests/test_perft.py` (self-consistency, always runs):
```python
from hive.game import Game
from hive.state import State
from hive.perft import perft


def test_perft_depth_1_is_first_move_count():
    g = Game(State.initial())
    assert perft(g, 1) == len(g.legal_moves())


def test_perft_small_depths_are_stable():
    g = Game(State.initial())
    # Regression anchors: fill in the exact numbers observed once, then freeze.
    # These guard against accidental move-gen changes between commits.
    d1 = perft(g, 1)
    d2 = perft(g, 2)
    assert d1 > 0 and d2 > d1
```

- [ ] **Step 3: Write the Mzinga cross-check test**

Add to `hive/tests/test_perft.py`:
```python
import pytest
from hive.notation import move_to_uhp


def _mzinga_valid_count(mz, moves_uhp):
    mz.cmd("newgame Base+MLP")
    for m in moves_uhp:
        mz.cmd(f"play {m}")
    out = mz.cmd("validmoves")
    line = out[-1] if out else ""
    return 0 if not line.strip() else len(line.strip().split(";"))


@pytest.mark.parametrize("depth", [1, 2, 3])
def test_our_move_counts_match_mzinga_along_a_line(mzinga, depth):
    # Walk a fixed opening line; at each ply our legal-move count must equal
    # Mzinga's validmoves count for the same UHP position.
    g = Game(State.initial())
    played = []
    for _ in range(depth):
        ours = g.legal_moves()
        assert len(ours) == _mzinga_valid_count(mzinga, played)
        move = ours[0]
        played.append(move_to_uhp(g, move))
        g.push(move)
```

- [ ] **Step 4: Run and reconcile**

Run (self-consistency only): `uv run --group hive pytest hive/tests/test_perft.py -q -k "not mzinga and not match"`
Then with Mzinga installed: `MZINGA_ENGINE=/path/to/MzingaEngine uv run --group hive pytest hive/tests/test_perft.py -q`
Expected: counts match. **If they diverge, the bug is in our engine, not Mzinga.** Debug order: (1) UHP direction mapping in `notation._DIR_TO_UHP` (fix the bijection so `move_to_uhp` matches Mzinga's `validmoves` strings for a known position), (2) `queen_first_move_allowed` default, (3) climb gate in `rules.can_climb`, (4) spider/ladybug path rules. Fix, re-run, repeat until all depths match. Freeze the observed depth-1/2/3 numbers into `test_perft_small_depths_are_stable`.

- [ ] **Step 5: Commit**

```bash
git add hive/perft.py hive/tests/conftest.py hive/tests/test_perft.py hive/rules.py hive/movers.py hive/notation.py
git commit -m "test(hive): perft harness + Mzinga cross-validation

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 9: Property tests + full-game replay + lint

**Files:**
- Create: `hive/tests/test_properties.py`
- Possibly modify: any engine file for bugs surfaced.

**Interfaces:**
- Consumes: the whole engine.
- Produces: no new API — a regression net.

- [ ] **Step 1: Write the property + replay tests**

`hive/tests/test_properties.py`:
```python
import random
from hive.game import Game
from hive.state import State
from hive.rules import is_connected


def test_hive_stays_connected_over_random_playouts():
    rng = random.Random(0)
    for _ in range(50):
        g = Game(State.initial())
        for _ in range(40):
            if g.is_terminal():
                break
            moves = g.legal_moves()
            g.push(moves[rng.randrange(len(moves))])
            assert is_connected(g.state.board) or not g.state.board.cells()


def test_push_pop_restores_position_key_over_random_line():
    rng = random.Random(1)
    from hive.notation import position_key
    g = Game(State.initial())
    keys = []
    played = []
    for _ in range(30):
        if g.is_terminal():
            break
        keys.append(position_key(g.state))
        moves = g.legal_moves()
        m = moves[rng.randrange(len(moves))]
        played.append(m)
        g.push(m)
    for _ in range(len(played)):
        g.pop()
    assert position_key(g.state) == keys[0]


def test_a_full_game_reaches_terminal_or_move_cap():
    rng = random.Random(2)
    g = Game(State.initial())
    for _ in range(400):
        if g.is_terminal():
            assert g.result() is not None
            return
        moves = g.legal_moves()
        g.push(moves[rng.randrange(len(moves))])
    # If uncapped games are common, that's a signal to revisit draw handling.
```

- [ ] **Step 2: Run tests**

Run: `uv run --group hive pytest hive/tests/test_properties.py -q`
Expected: PASS.

- [ ] **Step 3: Run the whole suite + lint**

Run: `uv run --group hive pytest hive/ -q && uvx ruff check hive/`
Expected: all green; ruff clean (fix lint inline).

- [ ] **Step 4: Commit**

```bash
git add hive/tests/test_properties.py
git commit -m "test(hive): connectivity/undo property tests + random playouts

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-review

**Spec coverage** — every spec element maps to a task:
- Axial coords + stacking board → Tasks 1–2. Translation-invariance → `position_key` (Task 7).
- One-hive / slide / climb / placement rules → Task 3. Movers (all 7 bugs incl. Mosquito/Ladybug) → Tasks 4–5.
- `legal_moves`/`apply`(push)/`result` + queen-by-4, no-move-before-queen, forced pass, win/draw/repetition → Task 6.
- UHP notation + GameString + hashing → Task 7. Mzinga perft anchor + recorded-line replay → Task 8. Property tests (connectivity, apply/undo, determinism) → Tasks 8–9.
- Success criteria (perft matches Mzinga; property tests pass; stable API) → Tasks 8–9.

**Placeholder scan** — the only deferred specifics are the exact UHP direction bijection and the frozen perft numbers, both resolved *within* Task 8 against a concrete oracle (Mzinga), not left open. No "TBD/handle edge cases" steps.

**Type consistency** — `Board._stacks` accessed by `position_key` (Task 2) matches Task 2's own definition. `Move(piece, dest, src)` field order consistent across Tasks 6–8. `MOVER_BY_BUG` excludes Mosquito (handled specially in Task 6's `_moves_for_piece`), consistent with Task 5. **Dependency ordering is a clean DAG**: `hexes` ← `state` (+`position_key`) ← `rules`/`movers` ← `game` ← `notation`/`perft`. `Game` imports `position_key` from `hive.state` (Task 2), so no circular dependency with `notation` (Task 7).

**Scope** — Phase 1 only; no net/MCTS/training/browser code. Focused enough for one plan.
