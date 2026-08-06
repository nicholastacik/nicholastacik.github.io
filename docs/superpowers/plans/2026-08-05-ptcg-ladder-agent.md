# PTCG Ladder Agent Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a non-crashing, measurably-strong PTCG agent to the Kaggle Simulation ladder before 2026-08-16 23:59.

**Architecture:** A scoring agent that ranks the engine's pre-validated legal options using an interpretable weighted feature sum with prize tempo as its spine. Measurement comes first — a multiprocess, seed-paired tournament harness with confidence intervals — so every subsequent change is verified rather than assumed. Perfect-Information Monte Carlo search (determinization + `search_step`) layers on last, behind a time bank, with a guaranteed greedy fallback.

**Tech Stack:** Python 3.12+, `cabt` engine via `ctypes` (prebuilt `libcg.dylib`/`libcg.so`), pandas, pytest, `multiprocessing`, `kaggle` CLI.

## Global Constraints

- **Deadlines:** Simulation closes **2026-08-16 23:59**; Strategy closes **2026-09-13 23:59**. Submit a working agent by ~Aug 9 — the cap is 5 submissions/day and iteration needs days.
- **The agent must never crash.** A raised exception is a forfeited game. Every agent entry point wraps its body in `try/except BaseException` and falls back to a legal selection.
- **The agent must never exceed its clock.** 600 s per player per game, cumulative; `obs.remainingOverageTime` reports what's left. Exceeding it is an instant loss.
- **Return contract:** `agent(obs_dict) -> list[int]`. Every element `>= 0` and `< len(obs.select.option)`; length between `obs.select.minCount` and `obs.select.maxCount` inclusive; **no duplicates**. When `obs.select is None`, return exactly 60 card IDs instead.
- **The engine is a process-global singleton.** `cg.sim` calls `lib.GameInitialize()` at import and `Battle.battle_ptr` is a class attribute — **one battle per process at a time**. All parallelism must use `multiprocessing`, never threads.
- **Competition data is never committed.** `ptcg/data/` and `ptcg/engine/` are gitignored; the engine carries a Competition-Use-Only licence.
- **Engine location:** `ptcg/engine/sample_submission/sample_submission/` (contains the `cg` package and `deck.csv`).
- **Terminal state is `obs.current.result != -1`.** `result` is the *winning player index*; `-1` means in progress.
- Card pool is **1,267** unique cards (`all_card_data()`); the CSV at `ptcg/data/EN_Card_Data.csv` has one row *per attack*, so deduplicate on `Card ID`.

---

## File Structure

| File | Responsibility |
|---|---|
| `ptcg/__init__.py` | Package marker. |
| `ptcg/engine.py` | Bootstrap `sys.path` to the SDK, re-export the `cg` API, own the one-battle-per-process guard, and provide `play_game()`. |
| `ptcg/cards.py` | `CardIndex`: load the deduplicated card CSV, look up name/stage/rule/HP by card ID. |
| `ptcg/decks.py` | Load, save and validate 60-card deck lists. |
| `ptcg/episodes.py` | Parse downloaded episode JSON into summaries; build the archetype → decklist census. |
| `ptcg/agents/__init__.py` | The `Agent` protocol and the `safe_agent` crash-proofing wrapper. |
| `ptcg/agents/baseline.py` | `RandomAgent`, `GreedyAttackAgent` — the gauntlet's fixed yardsticks. |
| `ptcg/agents/scorer.py` | `ScoringAgent`: ranks options via `features.py`. |
| `ptcg/features.py` | Feature extraction from an `Observation` + the weight vector + the weighted sum. |
| `ptcg/timebank.py` | Convert `remainingOverageTime` into a per-decision compute allowance. |
| `ptcg/tourney.py` | Multiprocess, seed-paired mirrored tournaments with Wilson confidence intervals. |
| `ptcg/determinize.py` | Sample consistent hidden-information worlds for `search_begin`. |
| `ptcg/search.py` | PIMC driver: determinize → enumerate turn sequences → evaluate → vote. |
| `submission/main.py` | Kaggle entry point; vendors the agent modules alongside `deck.csv`. |
| `ptcg/tests/` | pytest suite. |

---

### Task 1: Engine wrapper and a real game in a test

**Files:**
- Create: `ptcg/__init__.py`, `ptcg/engine.py`, `ptcg/tests/__init__.py`, `ptcg/tests/test_engine.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Consumes: nothing.
- Produces: `ptcg.engine.SDK_PATH: pathlib.Path`; `ptcg.engine.engine_available() -> bool`; `ptcg.engine.load_api()` returning a module-like namespace with `to_observation_class`, `all_card_data`, `search_begin`, `search_step`, `search_end`, `battle_start`, `battle_select`, `battle_finish`; `ptcg.engine.play_game(agent0, agent1, deck0, deck1, seed) -> GameResult`; `ptcg.engine.GameResult` dataclass with fields `winner: int`, `decisions: int`, `seconds: float`, `option_counts: list[int]`.

- [ ] **Step 1: Add the dependency group**

In `pyproject.toml`, add to `[dependency-groups]`:

```toml
ptcg = [
    "pandas",
    "pytest>=9.1.1",
]
```

- [ ] **Step 2: Write the failing test**

Create `ptcg/tests/test_engine.py`:

```python
import pytest

from ptcg import engine

pytestmark = pytest.mark.skipif(
    not engine.engine_available(),
    reason="cabt engine not downloaded; run `kaggle competitions download -c pokemon-tcg-ai-battle`",
)


def _random_agent_factory():
    import random

    rng = random.Random(0)

    def agent(obs):
        sel = obs.select
        k = len(sel.option)
        count = rng.randint(sel.minCount, min(sel.maxCount, k))
        return sorted(rng.sample(range(k), count))

    return agent


def test_all_card_data_has_1267_entries():
    api = engine.load_api()
    assert len(api.all_card_data()) == 1267


def test_play_game_runs_to_completion():
    deck = engine.sample_deck()
    result = engine.play_game(
        _random_agent_factory(), _random_agent_factory(), deck, deck, seed=1
    )
    assert result.winner in (0, 1)
    assert result.decisions > 0
    assert len(result.option_counts) == result.decisions
    assert result.seconds > 0


def test_repeated_games_differ_because_the_engine_shuffle_is_unseedable():
    """`ApiBattleStart(int* cards)` takes no seed: it sets `config.seed` from
    `std::random_device` and then replaces the RNG with a fresh `seed_seq`. The
    shuffle therefore cannot be reproduced from Python. This test pins that fact
    so nobody later builds variance reduction on an assumption of determinism."""
    deck = engine.sample_deck()
    outcomes = {
        (r.winner, r.decisions)
        for r in (
            engine.play_game(
                _random_agent_factory(), _random_agent_factory(), deck, deck, seed=7
            )
            for _ in range(8)
        )
    }
    assert len(outcomes) > 1
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run --group ptcg pytest ptcg/tests/test_engine.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ptcg'` (or `AttributeError` on `engine.engine_available`).

- [ ] **Step 4: Implement the wrapper**

Create `ptcg/__init__.py` as an empty file. Create `ptcg/tests/__init__.py` as an empty file. Create `ptcg/engine.py`:

```python
"""Thin wrapper over the competition's cabt SDK.

The SDK is not a package on PyPI: it ships as a directory containing a `cg`
package plus prebuilt shared libraries. Importing `cg.sim` calls
`lib.GameInitialize()` and `Battle.battle_ptr` is a class attribute, so a
process can only host one battle at a time. Parallelism must be by process.
"""

from __future__ import annotations

import contextlib
import functools
import pathlib
import random
import sys
import time
from dataclasses import dataclass, field

SDK_PATH = (
    pathlib.Path(__file__).resolve().parent
    / "engine"
    / "sample_submission"
    / "sample_submission"
)


def engine_available() -> bool:
    return (SDK_PATH / "cg" / "api.py").is_file()


@dataclass
class GameResult:
    winner: int
    decisions: int
    seconds: float
    option_counts: list[int] = field(default_factory=list)


@functools.lru_cache(maxsize=1)
def load_api():
    """Import the SDK once and return a namespace of the functions we use."""
    if not engine_available():
        raise RuntimeError(f"cabt SDK not found at {SDK_PATH}")
    if str(SDK_PATH) not in sys.path:
        sys.path.insert(0, str(SDK_PATH))

    from cg import api as _api
    from cg import game as _game

    class _Namespace:
        to_observation_class = staticmethod(_api.to_observation_class)
        all_card_data = staticmethod(_api.all_card_data)
        all_attack = staticmethod(_api.all_attack)
        search_begin = staticmethod(_api.search_begin)
        search_step = staticmethod(_api.search_step)
        search_end = staticmethod(_api.search_end)
        search_release = staticmethod(_api.search_release)
        battle_start = staticmethod(_game.battle_start)
        battle_select = staticmethod(_game.battle_select)
        battle_finish = staticmethod(_game.battle_finish)
        visualize_data = staticmethod(_game.visualize_data)
        OptionType = _api.OptionType
        SelectContext = _api.SelectContext
        SelectType = _api.SelectType

    return _Namespace


def sample_deck() -> list[int]:
    """The SDK's bundled deck. Only 9 distinct cards -- a smoke-test deck, not a
    benchmark deck: it runs ~3x faster than a real 20-distinct-card list."""
    text = (SDK_PATH / "deck.csv").read_text()
    return [int(line) for line in text.split("\n")[:60]]


@contextlib.contextmanager
def battle(deck0: list[int], deck1: list[int]):
    """Own one battle for the life of the block, guaranteeing battle_finish."""
    api = load_api()
    obs_dict, start = api.battle_start(list(deck0), list(deck1))
    if start.errorType != 0:
        raise RuntimeError(
            f"battle_start rejected the decks: errorPlayer={start.errorPlayer} "
            f"errorType={start.errorType}"
        )
    try:
        yield obs_dict
    finally:
        api.battle_finish()


def play_game(agent0, agent1, deck0, deck1, seed: int, max_decisions: int = 20_000):
    """Play one full game between two callables taking an Observation.

    Each agent is called with the parsed Observation and returns a list of
    option indices. Deck-submission steps are handled here, not by the agents,
    so agents only ever see real decisions.

    `seed` does NOT seed the engine. `ApiBattleStart` takes only the cards and
    seeds itself from `std::random_device`, so the shuffle is not reproducible
    from Python at all. `seed` only feeds the agents' own RNGs.
    """
    api = load_api()
    decks = (list(deck0), list(deck1))
    agents = (agent0, agent1)
    counts: list[int] = []

    with battle(decks[0], decks[1]) as obs_dict:
        started = time.perf_counter()
        while True:
            obs = api.to_observation_class(obs_dict)
            if obs.select is None:
                who = 0 if obs.current is None else obs.current.yourIndex
                obs_dict = api.battle_select(decks[who])
                continue
            if obs.current is not None and obs.current.result != -1:
                break
            options = obs.select.option
            if not options:
                obs_dict = api.battle_select([])
                continue
            counts.append(len(options))
            if len(counts) > max_decisions:
                raise RuntimeError("exceeded max_decisions; likely a policy loop")
            who = obs.current.yourIndex
            picks = agents[who](obs)
            obs_dict = api.battle_select(sorted(picks))
        elapsed = time.perf_counter() - started
        final = api.to_observation_class(obs_dict)
        winner = final.current.result

    return GameResult(
        winner=winner, decisions=len(counts), seconds=elapsed, option_counts=counts
    )
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `uv run --group ptcg pytest ptcg/tests/test_engine.py -v`
Expected: 3 passed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml ptcg/__init__.py ptcg/engine.py ptcg/tests/
git commit -m "feat(ptcg): engine wrapper with one-battle-per-process guard"
```

---

### Task 2: Card index

**Files:**
- Create: `ptcg/cards.py`, `ptcg/tests/test_cards.py`

**Interfaces:**
- Consumes: `ptcg.engine.load_api`.
- Produces: `ptcg.cards.CardIndex` with `from_csv(path=None) -> CardIndex`, `name(card_id) -> str`, `stage(card_id) -> str`, `rule(card_id) -> str | None`, `hp(card_id) -> int | None`, `is_basic_energy(card_id) -> bool`, `is_pokemon(card_id) -> bool`, `is_ace_spec(card_id) -> bool`, and `__len__`. Module constant `ptcg.cards.DEFAULT_CSV: pathlib.Path`.

- [ ] **Step 1: Write the failing test**

Create `ptcg/tests/test_cards.py`:

```python
import pytest

from ptcg import cards

pytestmark = pytest.mark.skipif(
    not cards.DEFAULT_CSV.is_file(), reason="card CSV not downloaded"
)


@pytest.fixture(scope="module")
def index():
    return cards.CardIndex.from_csv()


def test_index_has_1267_unique_cards(index):
    assert len(index) == 1267


def test_basic_energy_is_detected(index):
    # Card ID 1 is "Basic {G} Energy" in EN_Card_Data.csv.
    assert index.name(1) == "Basic {G} Energy"
    assert index.is_basic_energy(1)
    assert not index.is_pokemon(1)


def test_unknown_card_id_does_not_raise(index):
    assert index.name(999999) == "Unknown(999999)"
    assert index.hp(999999) is None


def test_ace_spec_and_pokemon_flags_are_consistent(index):
    ace = [cid for cid in index.card_ids if index.is_ace_spec(cid)]
    assert len(ace) == 29
    pokemon = [cid for cid in index.card_ids if index.is_pokemon(cid)]
    assert len(pokemon) == 595 + 345 + 116
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --group ptcg pytest ptcg/tests/test_cards.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ptcg.cards'`.

- [ ] **Step 3: Implement the index**

Create `ptcg/cards.py`:

```python
"""Card metadata, loaded from the competition's EN_Card_Data.csv.

The CSV holds one row *per attack*, so multi-attack Pokemon appear two or three
times. Deduplicating on `Card ID` yields the real pool of 1,267 cards -- not the
~2,000 figure quoted in press coverage, which is the raw row count.
"""

from __future__ import annotations

import pathlib
from dataclasses import dataclass

import pandas as pd

DEFAULT_CSV = pathlib.Path(__file__).resolve().parent / "data" / "EN_Card_Data.csv"

_STAGE_COLUMN = "Stage (Pokémon)/Type (Energy and Trainer)"
_POKEMON_STAGES = frozenset(
    {"Basic Pokémon", "Stage 1 Pokémon", "Stage 2 Pokémon"}
)


@dataclass
class CardIndex:
    names: dict[int, str]
    stages: dict[int, str]
    rules: dict[int, str | None]
    hps: dict[int, int | None]

    @classmethod
    def from_csv(cls, path: pathlib.Path | None = None) -> "CardIndex":
        frame = pd.read_csv(path or DEFAULT_CSV).drop_duplicates("Card ID")
        ids = frame["Card ID"].tolist()
        hp_numeric = pd.to_numeric(frame["HP"], errors="coerce")
        rules = [None if pd.isna(r) else str(r) for r in frame["Rule"]]
        return cls(
            names=dict(zip(ids, frame["Card Name"].astype(str))),
            stages=dict(zip(ids, frame[_STAGE_COLUMN].astype(str))),
            rules=dict(zip(ids, rules)),
            hps=dict(zip(ids, [None if pd.isna(h) else int(h) for h in hp_numeric])),
        )

    @property
    def card_ids(self) -> list[int]:
        return list(self.names)

    def __len__(self) -> int:
        return len(self.names)

    def name(self, card_id: int) -> str:
        return self.names.get(card_id, f"Unknown({card_id})")

    def stage(self, card_id: int) -> str:
        return self.stages.get(card_id, "Unknown")

    def rule(self, card_id: int) -> str | None:
        return self.rules.get(card_id)

    def hp(self, card_id: int) -> int | None:
        return self.hps.get(card_id)

    def is_basic_energy(self, card_id: int) -> bool:
        return self.stage(card_id) == "Basic Energy"

    def is_pokemon(self, card_id: int) -> bool:
        return self.stage(card_id) in _POKEMON_STAGES

    def is_ace_spec(self, card_id: int) -> bool:
        return self.rule(card_id) == "ACE SPEC"
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --group ptcg pytest ptcg/tests/test_cards.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add ptcg/cards.py ptcg/tests/test_cards.py
git commit -m "feat(ptcg): card index over the deduplicated card CSV"
```

---

### Task 3: Deck loading and legality validation

**Files:**
- Create: `ptcg/decks.py`, `ptcg/tests/test_decks.py`

**Interfaces:**
- Consumes: `ptcg.cards.CardIndex`.
- Produces: `ptcg.decks.load_deck(path) -> list[int]`, `ptcg.decks.save_deck(path, deck)`, `ptcg.decks.validate(deck, index) -> list[str]` (returns human-readable violations; empty list means legal), `ptcg.decks.DECK_SIZE = 60`.

- [ ] **Step 1: Write the failing test**

Create `ptcg/tests/test_decks.py`:

```python
import pytest

from ptcg import cards, decks


class FakeIndex:
    """Minimal stand-in so deck rules can be tested without the CSV."""

    def __init__(self):
        self._basic_energy = {1, 2}
        self._ace = {900}
        self._pokemon = {100, 101}

    def name(self, cid):
        return f"card-{cid}"

    def is_basic_energy(self, cid):
        return cid in self._basic_energy

    def is_ace_spec(self, cid):
        return cid in self._ace

    def is_pokemon(self, cid):
        return cid in self._pokemon


def _deck(**counts):
    out = []
    for cid, n in counts.items():
        out.extend([int(cid)] * n)
    return out


def test_legal_deck_reports_no_violations():
    deck = _deck(**{"100": 4, "101": 4, "1": 40, "900": 1, "500": 4, "501": 4, "502": 3})
    assert len(deck) == 60
    assert decks.validate(deck, FakeIndex()) == []


def test_wrong_size_is_reported():
    violations = decks.validate([100] * 59, FakeIndex())
    assert any("60" in v for v in violations)


def test_five_copies_of_a_non_energy_card_is_reported():
    deck = _deck(**{"100": 5, "101": 4, "1": 50, "900": 1})
    violations = decks.validate(deck, FakeIndex())
    assert any("card-100" in v and "4" in v for v in violations)


def test_copy_limit_is_enforced_across_card_ids_sharing_a_name():
    """The engine counts by name, so 3+3 of two printings of one card is 6."""

    class SharedNameIndex(FakeIndex):
        def name(self, cid):
            return "Ultra Ball" if cid in (700, 701) else f"card-{cid}"

    deck = _deck(**{"700": 3, "701": 3, "100": 4, "1": 49, "900": 1})
    violations = decks.validate(deck, SharedNameIndex())
    assert any("Ultra Ball" in v and "6" in v for v in violations)


def test_engine_error_codes_are_documented():
    assert decks.ENGINE_ERROR_TYPES[2].startswith("more than 4")


def test_basic_energy_may_exceed_four_copies():
    deck = _deck(**{"100": 4, "1": 55, "900": 1})
    assert not any("card-1" in v for v in decks.validate(deck, FakeIndex()))


def test_two_ace_specs_is_reported():
    deck = _deck(**{"100": 4, "900": 1, "901": 1, "1": 54})
    fake = FakeIndex()
    fake._ace = {900, 901}
    assert any("ACE SPEC" in v for v in decks.validate(deck, fake))


def test_deck_without_basic_pokemon_is_reported():
    deck = _deck(**{"1": 60})
    assert any("Basic" in v for v in decks.validate(deck, FakeIndex()))


def test_round_trip_through_csv(tmp_path):
    deck = list(range(60))
    path = tmp_path / "deck.csv"
    decks.save_deck(path, deck)
    assert decks.load_deck(path) == deck
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --group ptcg pytest ptcg/tests/test_decks.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ptcg.decks'`.

- [ ] **Step 3: Implement deck IO and validation**

Create `ptcg/decks.py`:

```python
"""Deck lists: 60 card IDs, one per line.

`validate` is a fast pre-check that mirrors the engine's own rules so an illegal
list is caught in milliseconds rather than by a rejected `battle_start`.
"""

from __future__ import annotations

import collections
import pathlib

DECK_SIZE = 60
MAX_COPIES = 4

# `ApiBattleStart` returns these in StartData.errorType. Read off Api.h so a
# rejected deck can be diagnosed without guessing.
ENGINE_ERROR_TYPES = {
    1: "unknown card ID (not in the engine's CardTable)",
    2: "more than 4 copies of a card name (Basic Energy is exempt)",
    3: "no Basic Pokemon in the deck",
    4: "more than one ACE SPEC card",
}


def load_deck(path: pathlib.Path | str) -> list[int]:
    lines = pathlib.Path(path).read_text().split("\n")
    return [int(line) for line in lines if line.strip()][:DECK_SIZE]


def save_deck(path: pathlib.Path | str, deck: list[int]) -> None:
    pathlib.Path(path).write_text("\n".join(str(c) for c in deck) + "\n")


def validate(deck: list[int], index) -> list[str]:
    """Return a list of rule violations. Empty means the deck looks legal."""
    problems: list[str] = []

    if len(deck) != DECK_SIZE:
        problems.append(f"deck has {len(deck)} cards, must have exactly {DECK_SIZE}")

    counts = collections.Counter(deck)

    # The engine enforces the 4-copy limit by card NAME, not card ID
    # (`nameCount[master.name]` in ApiBattleStart). Distinct printings that share
    # a name count together, so grouping by ID would wave through an illegal deck.
    by_name: collections.Counter = collections.Counter()
    name_is_basic_energy: dict[str, bool] = {}
    for card_id, n in counts.items():
        name = index.name(card_id)
        by_name[name] += n
        name_is_basic_energy[name] = name_is_basic_energy.get(
            name, True
        ) and index.is_basic_energy(card_id)

    for name, n in sorted(by_name.items()):
        if n > MAX_COPIES and not name_is_basic_energy[name]:
            problems.append(f"{name} appears {n} times, limit is {MAX_COPIES}")

    ace_total = sum(n for cid, n in counts.items() if index.is_ace_spec(cid))
    if ace_total > 1:
        names = sorted(index.name(cid) for cid in counts if index.is_ace_spec(cid))
        problems.append(f"deck has {ace_total} ACE SPEC cards ({', '.join(names)}), limit is 1")

    if not any(index.is_pokemon(cid) for cid in counts):
        problems.append("deck contains no Basic Pokemon; it cannot start a game")

    return problems
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --group ptcg pytest ptcg/tests/test_decks.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add ptcg/decks.py ptcg/tests/test_decks.py
git commit -m "feat(ptcg): deck IO and legality pre-check"
```

---

### Task 4: Episode parsing and the archetype census

This is what picks our deck *and* powers opponent fingerprinting later — the highest-value non-agent task in the plan.

**Files:**
- Create: `ptcg/episodes.py`, `ptcg/tests/test_episodes.py`

**Interfaces:**
- Consumes: `ptcg.cards.CardIndex`.
- Produces: `ptcg.episodes.EpisodeSummary` dataclass with fields `episode_id: int`, `teams: tuple[str, str]`, `decks: tuple[list[int], list[int]]`, `winner: int`, `seconds_used: tuple[float, float]`, `decisions: tuple[int, int]`; `ptcg.episodes.parse_episode(path) -> EpisodeSummary`; `ptcg.episodes.load_directory(path) -> list[EpisodeSummary]`; `ptcg.episodes.census(summaries, index) -> pandas.DataFrame` with columns `deck_key`, `headline`, `games`, `wins`, `win_rate`; `ptcg.episodes.deck_key(deck) -> str`; `ptcg.episodes.headline_cards(deck, index) -> str`.

- [ ] **Step 1: Write the failing test**

Create `ptcg/tests/test_episodes.py`:

```python
import json

import pytest

from ptcg import episodes


def _fake_episode(episode_id, teams, decks, winner, remaining):
    """Build a minimal episode JSON matching the real dump's shape.

    Deck submission lives at steps[1][player].action -- step 0 is empty.
    """
    steps = [
        [
            {"action": [], "observation": {"remainingOverageTime": 600, "select": None}},
            {"action": [], "observation": {"remainingOverageTime": 600, "select": None}},
        ],
        [
            {"action": decks[0], "observation": {"remainingOverageTime": 600}},
            {"action": decks[1], "observation": {"remainingOverageTime": 600}},
        ],
    ]
    for p in (0, 1):
        steps.append(
            [
                {
                    "action": [0] if q == p else [],
                    "observation": {"remainingOverageTime": remaining[q]},
                }
                for q in (0, 1)
            ]
        )
    return {
        "info": {"EpisodeId": episode_id, "TeamNames": list(teams)},
        "rewards": [1 if winner == 0 else -1, 1 if winner == 1 else -1],
        "steps": steps,
    }


@pytest.fixture
def episode_dir(tmp_path):
    deck_a = [100] * 4 + [1] * 56
    deck_b = [200] * 4 + [2] * 56
    payloads = [
        _fake_episode(1, ("alice", "bob"), (deck_a, deck_b), 0, (595.0, 590.0)),
        _fake_episode(2, ("carol", "dave"), (deck_a, deck_b), 1, (598.0, 300.0)),
        _fake_episode(3, ("erin", "frank"), (deck_b, deck_a), 0, (599.0, 599.0)),
    ]
    for payload in payloads:
        (tmp_path / f"{payload['info']['EpisodeId']}.json").write_text(json.dumps(payload))
    return tmp_path


def test_parse_episode_extracts_decks_and_winner(episode_dir):
    summary = episodes.parse_episode(episode_dir / "1.json")
    assert summary.episode_id == 1
    assert summary.teams == ("alice", "bob")
    assert len(summary.decks[0]) == 60
    assert summary.winner == 0
    assert summary.seconds_used[0] == pytest.approx(5.0)
    assert summary.seconds_used[1] == pytest.approx(10.0)


def test_load_directory_reads_every_episode(episode_dir):
    summaries = episodes.load_directory(episode_dir)
    assert len(summaries) == 3
    assert {s.episode_id for s in summaries} == {1, 2, 3}


def test_deck_key_is_order_insensitive():
    assert episodes.deck_key([3, 1, 2]) == episodes.deck_key([2, 3, 1])
    assert episodes.deck_key([1, 1, 2]) != episodes.deck_key([1, 2, 2])


def test_census_aggregates_by_deck(episode_dir):
    class FakeIndex:
        def name(self, cid):
            return f"card-{cid}"

        def rule(self, cid):
            return "Pokémon ex" if cid in (100, 200) else None

    frame = episodes.census(episodes.load_directory(episode_dir), FakeIndex())
    # deck_a appears 3 times (eps 1, 2, 3) and wins in 1 and 3.
    row = frame[frame["headline"].str.contains("card-100")].iloc[0]
    assert row["games"] == 3
    assert row["wins"] == 2
    assert row["win_rate"] == pytest.approx(2 / 3)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --group ptcg pytest ptcg/tests/test_episodes.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ptcg.episodes'`.

- [ ] **Step 3: Implement episode parsing and census**

Create `ptcg/episodes.py`:

```python
"""Read Kaggle's public PTCG episode dumps.

Kaggle publishes one dataset per day of ladder play. Each episode is a JSON file
in kaggle_environments format. Two fields matter to us:

  steps[1][player]["action"]                     -- the submitted 60-card deck
  steps[i][player]["observation"]["remainingOverageTime"]  -- the clock

Submitted decks are therefore public, which is what makes opponent
fingerprinting possible -- and also means our own deck is public within a day.
"""

from __future__ import annotations

import collections
import json
import pathlib
from dataclasses import dataclass

import pandas as pd

DECK_SIZE = 60
FULL_BUDGET = 600.0


@dataclass
class EpisodeSummary:
    episode_id: int
    teams: tuple[str, str]
    decks: tuple[list[int], list[int]]
    winner: int
    seconds_used: tuple[float, float]
    decisions: tuple[int, int]


def parse_episode(path: pathlib.Path | str) -> EpisodeSummary:
    payload = json.loads(pathlib.Path(path).read_text())
    steps = payload["steps"]

    decks: list[list[int]] = [[], []]
    decisions = [0, 0]
    last_remaining = [FULL_BUDGET, FULL_BUDGET]

    for step in steps:
        for player in (0, 1):
            entry = step[player]
            action = entry.get("action") or []
            observation = entry.get("observation") or {}
            remaining = observation.get("remainingOverageTime")
            if remaining is not None:
                last_remaining[player] = float(remaining)
            if len(action) == DECK_SIZE and not decks[player]:
                decks[player] = list(action)
            elif action:
                decisions[player] += 1

    rewards = payload.get("rewards") or [0, 0]
    winner = 0 if rewards[0] == 1 else (1 if rewards[1] == 1 else -1)

    return EpisodeSummary(
        episode_id=int(payload["info"]["EpisodeId"]),
        teams=tuple(payload["info"]["TeamNames"]),
        decks=(decks[0], decks[1]),
        winner=winner,
        seconds_used=(
            FULL_BUDGET - last_remaining[0],
            FULL_BUDGET - last_remaining[1],
        ),
        decisions=(decisions[0], decisions[1]),
    )


def load_directory(path: pathlib.Path | str) -> list[EpisodeSummary]:
    out = []
    for file in sorted(pathlib.Path(path).glob("*.json")):
        try:
            out.append(parse_episode(file))
        except (KeyError, ValueError, json.JSONDecodeError):
            continue
    return out


def deck_key(deck: list[int]) -> str:
    """Stable identity for a decklist, insensitive to card order."""
    counts = sorted(collections.Counter(deck).items())
    return ",".join(f"{cid}x{n}" for cid, n in counts)


def headline_cards(deck: list[int], index, limit: int = 3) -> str:
    """Name a deck by its ex / Mega ex cards -- how players describe archetypes."""
    names = sorted(
        {
            index.name(cid)
            for cid in set(deck)
            if index.rule(cid) in ("Pokémon ex", "Mega Pokémon ex")
        }
    )
    if not names:
        counts = collections.Counter(deck)
        names = [index.name(cid) for cid, _ in counts.most_common(limit)]
    return ", ".join(names[:limit])


def census(summaries: list[EpisodeSummary], index) -> pd.DataFrame:
    """Aggregate games and wins per distinct decklist, most-played first."""
    games: collections.Counter = collections.Counter()
    wins: collections.Counter = collections.Counter()
    example: dict[str, list[int]] = {}

    for summary in summaries:
        for player in (0, 1):
            deck = summary.decks[player]
            if len(deck) != DECK_SIZE:
                continue
            key = deck_key(deck)
            example.setdefault(key, deck)
            games[key] += 1
            if summary.winner == player:
                wins[key] += 1

    rows = [
        {
            "deck_key": key,
            "headline": headline_cards(example[key], index),
            "games": games[key],
            "wins": wins[key],
            "win_rate": wins[key] / games[key],
        }
        for key in games
    ]
    frame = pd.DataFrame(rows)
    if frame.empty:
        return frame
    return frame.sort_values(["games", "win_rate"], ascending=False).reset_index(drop=True)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --group ptcg pytest ptcg/tests/test_episodes.py -v`
Expected: 4 passed.

- [ ] **Step 5: Run the census over real data and record the chosen deck**

```bash
uv run --group ptcg python -c "
from ptcg import cards, episodes, decks
idx = cards.CardIndex.from_csv()
s = episodes.load_directory('ptcg/data/episode-sample')
print(episodes.census(s, idx).head(20).to_string())
"
```

Pick the deck with the best win rate among those with the most games, write it to `ptcg/decks/ladder.csv` via `decks.save_deck`, and confirm `decks.validate` returns `[]`. Append a dated entry to `posts/ptcg/notes/build-log.md` naming the deck and the win rate that justified it.

- [ ] **Step 6: Commit**

```bash
git add ptcg/episodes.py ptcg/tests/test_episodes.py ptcg/decks/ladder.csv posts/ptcg/notes/build-log.md
git commit -m "feat(ptcg): episode parsing, archetype census, and ladder deck choice"
```

---

### Task 5: Agent protocol, crash-proofing, and baseline agents

**Files:**
- Create: `ptcg/agents/__init__.py`, `ptcg/agents/baseline.py`, `ptcg/tests/test_agents.py`

**Interfaces:**
- Consumes: `ptcg.engine.load_api`.
- Produces: `ptcg.agents.legal_fallback(select) -> list[int]`; `ptcg.agents.safe_agent(fn) -> callable` (never raises); `ptcg.agents.baseline.RandomAgent(seed)`; `ptcg.agents.baseline.GreedyAttackAgent(seed)`. Both baselines are callables taking an `Observation` and returning `list[int]`.

- [ ] **Step 1: Write the failing test**

Create `ptcg/tests/test_agents.py`:

```python
import pytest

from ptcg import agents
from ptcg.agents import baseline


class FakeOption:
    def __init__(self, type_, attackId=None):
        self.type = type_
        self.attackId = attackId


class FakeSelect:
    def __init__(self, options, minCount=1, maxCount=1):
        self.option = options
        self.minCount = minCount
        self.maxCount = maxCount


class FakeObs:
    def __init__(self, select):
        self.select = select
        self.current = None


def test_legal_fallback_respects_min_count():
    select = FakeSelect([FakeOption(7)] * 5, minCount=2, maxCount=4)
    picks = agents.legal_fallback(select)
    assert len(picks) == 2
    assert picks == sorted(set(picks))
    assert all(0 <= p < 5 for p in picks)


def test_legal_fallback_handles_zero_min_count():
    select = FakeSelect([FakeOption(7)] * 3, minCount=0, maxCount=2)
    assert agents.legal_fallback(select) == []


def test_safe_agent_swallows_exceptions_and_returns_legal():
    @agents.safe_agent
    def exploding(obs):
        raise ValueError("boom")

    select = FakeSelect([FakeOption(7)] * 4, minCount=1, maxCount=1)
    picks = exploding(FakeObs(select))
    assert len(picks) == 1
    assert 0 <= picks[0] < 4


def test_safe_agent_repairs_out_of_range_output():
    @agents.safe_agent
    def cheating(obs):
        return [99]

    select = FakeSelect([FakeOption(7)] * 3, minCount=1, maxCount=1)
    picks = cheating(FakeObs(select))
    assert picks == [0] or (len(picks) == 1 and 0 <= picks[0] < 3)


def test_safe_agent_repairs_duplicates():
    @agents.safe_agent
    def dupes(obs):
        return [1, 1]

    select = FakeSelect([FakeOption(7)] * 4, minCount=2, maxCount=2)
    picks = dupes(FakeObs(select))
    assert len(picks) == len(set(picks)) == 2


def test_greedy_attack_agent_prefers_an_attack_option():
    options = [FakeOption(7), FakeOption(13, attackId=42), FakeOption(14)]
    picks = baseline.GreedyAttackAgent(seed=0)(FakeObs(FakeSelect(options)))
    assert picks == [1]


def test_greedy_attack_agent_avoids_ending_the_turn_when_it_can():
    options = [FakeOption(14), FakeOption(7)]
    picks = baseline.GreedyAttackAgent(seed=0)(FakeObs(FakeSelect(options)))
    assert picks == [1]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --group ptcg pytest ptcg/tests/test_agents.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ptcg.agents'`.

- [ ] **Step 3: Implement the protocol and baselines**

Create `ptcg/agents/__init__.py`:

```python
"""Agent plumbing.

A raised exception forfeits the game, so `safe_agent` is not defensive
programming for its own sake -- it is the difference between a bug costing one
bad move and costing the match. It also repairs outputs that violate the return
contract (out of range, duplicated, wrong length) rather than letting the engine
reject them.
"""

from __future__ import annotations

from typing import Callable


def legal_fallback(select) -> list[int]:
    """The cheapest always-legal selection: the first `minCount` options."""
    count = max(0, int(getattr(select, "minCount", 0)))
    available = len(select.option)
    return list(range(min(count, available)))


def _repair(picks, select) -> list[int]:
    available = len(select.option)
    lo = max(0, int(select.minCount))
    hi = min(int(select.maxCount), available)

    cleaned: list[int] = []
    for p in picks or []:
        try:
            value = int(p)
        except (TypeError, ValueError):
            continue
        if 0 <= value < available and value not in cleaned:
            cleaned.append(value)

    if len(cleaned) > hi:
        cleaned = cleaned[:hi]
    for candidate in range(available):
        if len(cleaned) >= lo:
            break
        if candidate not in cleaned:
            cleaned.append(candidate)

    return sorted(cleaned)


def safe_agent(fn: Callable) -> Callable:
    """Wrap an agent so it can never raise and never returns an illegal list."""

    def wrapper(obs):
        select = obs.select
        try:
            picks = fn(obs)
        except BaseException:
            return legal_fallback(select)
        try:
            return _repair(picks, select)
        except BaseException:
            return legal_fallback(select)

    wrapper.__name__ = getattr(fn, "__name__", "agent")
    return wrapper
```

Create `ptcg/agents/baseline.py`:

```python
"""Fixed yardsticks for the gauntlet.

These never change once committed. Progress is measured against a stable
baseline, not against whatever the agent looked like last week.
"""

from __future__ import annotations

import random

from . import safe_agent

ATTACK = 13
END = 14


class RandomAgent:
    """Uniform choice among legal options. The floor."""

    name = "random"

    def __init__(self, seed: int = 0):
        self._rng = random.Random(seed)
        self._call = safe_agent(self._choose)

    def __call__(self, obs):
        return self._call(obs)

    def _choose(self, obs):
        select = obs.select
        available = len(select.option)
        count = self._rng.randint(select.minCount, min(select.maxCount, available))
        return sorted(self._rng.sample(range(available), count))


class GreedyAttackAgent:
    """Attack whenever possible; otherwise do anything except end the turn.

    Crude, but a real opponent: it applies pressure, so beating it means the
    scoring agent is doing something beyond avoiding blunders.
    """

    name = "greedy-attack"

    def __init__(self, seed: int = 0):
        self._rng = random.Random(seed)
        self._call = safe_agent(self._choose)

    def __call__(self, obs):
        return self._call(obs)

    def _choose(self, obs):
        select = obs.select
        options = select.option

        attacks = [i for i, o in enumerate(options) if o.type == ATTACK]
        if attacks and select.maxCount >= 1:
            return [attacks[0]]

        non_end = [i for i, o in enumerate(options) if o.type != END]
        pool = non_end or list(range(len(options)))
        count = max(select.minCount, 1) if select.maxCount >= 1 else 0
        count = min(count, len(pool), select.maxCount)
        if count == 0:
            return []
        return sorted(self._rng.sample(pool, count))
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --group ptcg pytest ptcg/tests/test_agents.py -v`
Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add ptcg/agents/ ptcg/tests/test_agents.py
git commit -m "feat(ptcg): agent protocol, crash-proof wrapper, baseline agents"
```

---

### Task 6: Seat-balanced tournament harness with confidence intervals

Built before the scoring agent on purpose: without this, every later change is a guess.

**Note on a technique that is unavailable here.** The spec called for seed-paired
mirrored matches — common random numbers, the standard variance-reduction trick
from chess-engine testing. It cannot be done: `ApiBattleStart(int* cards)` accepts
only cards, seeds `config.seed` from `std::random_device`, and then overwrites the
RNG with a fresh `seed_seq`. There is no seed parameter anywhere in the exported
API, so two games can never share a shuffle. Verified empirically — eight runs of
an identical deterministic policy produced different winners and decision counts.

What survives is the half of pairing that *is* reachable: **seat balancing.**
Going first is a real, systematic edge in Pokémon TCG, so every matchup is played
an equal number of times from each seat. That removes the largest bias. Shuffle
luck has to be beaten by volume instead — which is affordable, because a game
costs 39 ms, so 400 games is about 16 core-seconds.

**Files:**
- Create: `ptcg/tourney.py`, `ptcg/tests/test_tourney.py`

**Interfaces:**
- Consumes: `ptcg.engine.play_game`, `ptcg.agents.baseline`.
- Produces: `ptcg.tourney.wilson_interval(wins, n, z=1.96) -> tuple[float, float]`; `ptcg.tourney.MatchResult` dataclass with `wins: int`, `losses: int`, `games: int`, `win_rate: float`, `low: float`, `high: float`, `seconds: float`, `seat_wins: tuple[int, int]`, `seat_games: tuple[int, int]`; `ptcg.tourney.balanced_seats(n_pairs, base_seed) -> list[tuple[int, int]]` yielding `(seed, seat)` with each seed appearing once per seat; `ptcg.tourney.run_match(spec_a, spec_b, deck_a, deck_b, n_pairs, processes, base_seed) -> MatchResult`; `ptcg.tourney.games_for_margin(margin, p=0.5) -> int`. An agent *spec* is a `(module_path, class_name, kwargs)` tuple so it can cross a process boundary.

- [ ] **Step 1: Write the failing test**

Create `ptcg/tests/test_tourney.py`:

```python
import pytest

from ptcg import engine, tourney


def test_wilson_interval_brackets_the_point_estimate():
    low, high = tourney.wilson_interval(50, 100)
    assert low < 0.5 < high


def test_wilson_interval_narrows_as_games_increase():
    narrow = tourney.wilson_interval(200, 400)
    wide = tourney.wilson_interval(25, 50)
    assert (narrow[1] - narrow[0]) < (wide[1] - wide[0])


def test_wilson_interval_handles_zero_games():
    assert tourney.wilson_interval(0, 0) == (0.0, 1.0)


def test_balanced_seats_plays_each_seed_from_both_seats():
    pairs = tourney.balanced_seats(3, base_seed=100)
    assert len(pairs) == 6
    assert sorted(s for s, _ in pairs) == [100, 100, 101, 101, 102, 102]
    for seed in (100, 101, 102):
        assert sorted(seat for s, seat in pairs if s == seed) == [0, 1]


def test_seat_counts_are_exactly_balanced():
    pairs = tourney.balanced_seats(50)
    assert sum(1 for _, seat in pairs if seat == 0) == 50
    assert sum(1 for _, seat in pairs if seat == 1) == 50


def test_games_for_margin_grows_as_the_margin_tightens():
    assert tourney.games_for_margin(0.05) > tourney.games_for_margin(0.10)
    # +-5 points at 95% needs roughly 400 games.
    assert 300 <= tourney.games_for_margin(0.05) <= 500


@pytest.mark.skipif(not engine.engine_available(), reason="cabt engine not downloaded")
def test_run_match_between_baselines_returns_consistent_totals():
    deck = engine.sample_deck()
    spec_a = ("ptcg.agents.baseline", "RandomAgent", {"seed": 1})
    spec_b = ("ptcg.agents.baseline", "GreedyAttackAgent", {"seed": 2})
    result = tourney.run_match(spec_a, spec_b, deck, deck, n_pairs=4, processes=2, base_seed=0)
    assert result.games == 8
    assert result.wins + result.losses == result.games
    assert 0.0 <= result.win_rate <= 1.0
    assert result.low <= result.win_rate <= result.high
    # Seat balance is the one bias we can actually control; assert it holds.
    assert result.seat_games == (4, 4)
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --group ptcg pytest ptcg/tests/test_tourney.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ptcg.tourney'`.

- [ ] **Step 3: Implement the harness**

Create `ptcg/tourney.py`:

```python
"""Measure whether one agent actually beats another.

Two things make this trustworthy:

*Seat balancing.* Going first is a systematic edge, so each matchup is played an
equal number of times from each seat and the advantage cancels exactly.

Common random numbers -- replaying the same shuffle for both agents, the usual
variance-reduction trick -- is NOT available: `ApiBattleStart` takes only cards
and seeds itself from `std::random_device`, so no two games share a shuffle. Card
games are variance-dominated (a 50-game A/B at 56% has a 95% interval of about
+-14 points, i.e. nothing), so the only remaining lever is volume. That is fine:
a game costs ~39 ms, so the ~400 games needed for +-5 points is ~16 core-seconds.

*Wilson intervals.* Reported as a range, never a bare percentage, so an
under-powered comparison is visible rather than persuasive.

The engine is a process-global singleton, so parallelism is by process. Agents
therefore cross a process boundary as `(module, class, kwargs)` specs rather
than as pickled instances.
"""

from __future__ import annotations

import importlib
import math
import multiprocessing as mp
import time
from dataclasses import dataclass

from . import engine


@dataclass
class MatchResult:
    wins: int
    losses: int
    games: int
    win_rate: float
    low: float
    high: float
    seconds: float
    seat_wins: tuple[int, int] = (0, 0)
    seat_games: tuple[int, int] = (0, 0)

    @property
    def beats_even(self) -> bool:
        """True only when the whole interval clears 50% -- the bar for shipping."""
        return self.low > 0.5

    def summary(self, name_a: str = "A", name_b: str = "B") -> str:
        margin = (self.high - self.low) / 2 * 100
        seats = " ".join(
            f"seat{i}:{self.seat_wins[i]}/{self.seat_games[i]}"
            for i in (0, 1)
            if self.seat_games[i]
        )
        verdict = "CLEAR" if self.beats_even else "not significant"
        return (
            f"{name_a} vs {name_b}: {self.wins}-{self.losses} "
            f"({self.win_rate * 100:.1f}% +-{margin:.1f}, "
            f"95% CI [{self.low * 100:.1f}, {self.high * 100:.1f}]) "
            f"over {self.games} games in {self.seconds:.1f}s "
            f"[{seats}] -- {verdict}"
        )


def wilson_interval(wins: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval -- well behaved near 0 and 1, unlike the normal
    approximation, which matters when an agent is dominating or being crushed."""
    if n <= 0:
        return (0.0, 1.0)
    p = wins / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    spread = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (max(0.0, centre - spread), min(1.0, centre + spread))


def games_for_margin(margin: float, p: float = 0.5, z: float = 1.96) -> int:
    """Games needed for a +-margin interval at the given win rate.

    Use this before running a comparison, not after being disappointed by one.
    """
    if margin <= 0:
        raise ValueError("margin must be positive")
    return int(math.ceil(z * z * p * (1 - p) / (margin * margin)))


def balanced_seats(n_pairs: int, base_seed: int = 0) -> list[tuple[int, int]]:
    """Each seed once per seat, so the first-player advantage cancels exactly.

    The seed does not reproduce the shuffle (the engine reseeds itself); it only
    varies the agents' own RNGs. Seat balance is the real guarantee here.
    """
    return [(base_seed + i, seat) for i in range(n_pairs) for seat in (0, 1)]


def _build(spec):
    module_path, class_name, kwargs = spec
    module = importlib.import_module(module_path)
    return getattr(module, class_name)(**(kwargs or {}))


def _play_one(job):
    spec_a, spec_b, deck_a, deck_b, seed, seat = job
    agent_a, agent_b = _build(spec_a), _build(spec_b)
    if seat == 0:
        result = engine.play_game(agent_a, agent_b, deck_a, deck_b, seed=seed)
        a_won = result.winner == 0
    else:
        result = engine.play_game(agent_b, agent_a, deck_b, deck_a, seed=seed)
        a_won = result.winner == 1
    return bool(a_won)


def run_match(
    spec_a,
    spec_b,
    deck_a: list[int],
    deck_b: list[int],
    n_pairs: int = 200,
    processes: int | None = None,
    base_seed: int = 0,
) -> MatchResult:
    """Play `2 * n_pairs` games and report A's win rate with a Wilson interval."""
    seat_plan = balanced_seats(n_pairs, base_seed)
    jobs = [(spec_a, spec_b, deck_a, deck_b, seed, seat) for seed, seat in seat_plan]
    started = time.perf_counter()
    if processes == 1:
        outcomes = [_play_one(job) for job in jobs]
    else:
        ctx = mp.get_context("spawn")
        with ctx.Pool(processes=processes) as pool:
            outcomes = pool.map(_play_one, jobs)
    elapsed = time.perf_counter() - started

    wins = sum(outcomes)
    games = len(outcomes)
    seat_wins = [0, 0]
    seat_games = [0, 0]
    for (_, seat), won in zip(seat_plan, outcomes):
        seat_games[seat] += 1
        seat_wins[seat] += int(won)

    low, high = wilson_interval(wins, games)
    return MatchResult(
        wins=wins,
        losses=games - wins,
        games=games,
        win_rate=wins / games if games else 0.0,
        low=low,
        high=high,
        seconds=elapsed,
        seat_wins=(seat_wins[0], seat_wins[1]),
        seat_games=(seat_games[0], seat_games[1]),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --group ptcg pytest ptcg/tests/test_tourney.py -v`
Expected: 5 passed.

- [ ] **Step 5: Record the measured throughput**

```bash
uv run --group ptcg python -c "
from ptcg import engine, tourney
deck = engine.sample_deck()
r = tourney.run_match(('ptcg.agents.baseline','RandomAgent',{'seed':1}),
                      ('ptcg.agents.baseline','GreedyAttackAgent',{'seed':2}),
                      deck, deck, n_pairs=200)
print(r.summary('random','greedy-attack'))
"
```

Append the result to `posts/ptcg/notes/build-log.md`. `GreedyAttackAgent` should beat `RandomAgent` decisively; if it doesn't, the harness or the baseline is wrong and must be fixed before proceeding.

- [ ] **Step 6: Commit**

```bash
git add ptcg/tourney.py ptcg/tests/test_tourney.py posts/ptcg/notes/build-log.md
git commit -m "feat(ptcg): seed-paired tournament harness with Wilson intervals"
```

---

### Task 7: Feature extraction and the scoring agent

**Files:**
- Create: `ptcg/features.py`, `ptcg/agents/scorer.py`, `ptcg/tests/test_features.py`

**Interfaces:**
- Consumes: `ptcg.agents.safe_agent`, `ptcg.engine.load_api`.
- Produces: `ptcg.features.DEFAULT_WEIGHTS: dict[str, float]`; `ptcg.features.option_features(obs, option) -> dict[str, float]`; `ptcg.features.score(obs, option, weights=None) -> float`; `ptcg.features.rank(obs, weights=None) -> list[tuple[int, float, dict[str, float]]]` sorted best-first; `ptcg.agents.scorer.ScoringAgent(weights=None, seed=0)`.

- [ ] **Step 1: Write the failing test**

Create `ptcg/tests/test_features.py`:

```python
import pytest

from ptcg import features
from ptcg.agents import scorer


class FakeOption:
    def __init__(self, type_, **kw):
        self.type = type_
        self.attackId = kw.get("attackId")
        self.area = kw.get("area")
        self.index = kw.get("index")


class FakePokemon:
    def __init__(self, hp, maxHp):
        self.hp = hp
        self.maxHp = maxHp
        self.energies = []
        self.energyCards = []
        self.tools = []
        self.preEvolution = []


class FakePlayer:
    def __init__(self, prize_left, bench=0, hand=5):
        self.prize = [None] * prize_left
        self.bench = [FakePokemon(100, 100) for _ in range(bench)]
        self.active = [FakePokemon(100, 100)]
        self.handCount = hand
        self.deckCount = 30
        self.discard = []
        self.benchMax = 5


class FakeState:
    def __init__(self, my_prizes, their_prizes, my_index=0):
        self.yourIndex = my_index
        me = FakePlayer(my_prizes, bench=2)
        them = FakePlayer(their_prizes, bench=1)
        self.players = [me, them] if my_index == 0 else [them, me]
        self.turn = 5
        self.result = -1
        self.supporterPlayed = False
        self.energyAttached = False
        self.stadium = []


class FakeSelect:
    def __init__(self, options, minCount=1, maxCount=1, context=0):
        self.option = options
        self.minCount = minCount
        self.maxCount = maxCount
        self.context = context


class FakeObs:
    def __init__(self, select, state):
        self.select = select
        self.current = state
        self.remainingOverageTime = 600.0


def test_prize_lead_is_positive_when_ahead():
    ahead = FakeObs(FakeSelect([FakeOption(14)]), FakeState(my_prizes=2, their_prizes=5))
    behind = FakeObs(FakeSelect([FakeOption(14)]), FakeState(my_prizes=5, their_prizes=2))
    assert features.option_features(ahead, ahead.select.option[0])["prize_lead"] > 0
    assert features.option_features(behind, behind.select.option[0])["prize_lead"] < 0


def test_attacking_scores_above_ending_the_turn():
    state = FakeState(my_prizes=4, their_prizes=4)
    attack = FakeOption(13, attackId=1)
    end = FakeOption(14)
    obs = FakeObs(FakeSelect([attack, end]), state)
    assert features.score(obs, attack) > features.score(obs, end)


def test_rank_returns_options_best_first_with_breakdowns():
    state = FakeState(my_prizes=4, their_prizes=4)
    obs = FakeObs(FakeSelect([FakeOption(14), FakeOption(13, attackId=1)]), state)
    ranked = features.rank(obs)
    assert [i for i, _, _ in ranked][0] == 1
    scores = [s for _, s, _ in ranked]
    assert scores == sorted(scores, reverse=True)
    assert "prize_lead" in ranked[0][2]


def test_unknown_weight_key_does_not_break_scoring():
    state = FakeState(my_prizes=3, their_prizes=3)
    obs = FakeObs(FakeSelect([FakeOption(14)]), state)
    assert isinstance(features.score(obs, obs.select.option[0], {"nonexistent": 5.0}), float)


def test_scoring_agent_picks_the_top_ranked_option():
    state = FakeState(my_prizes=4, their_prizes=4)
    obs = FakeObs(FakeSelect([FakeOption(14), FakeOption(13, attackId=1)]), state)
    assert scorer.ScoringAgent()(obs) == [1]


def test_scoring_agent_returns_min_count_when_min_is_zero():
    state = FakeState(my_prizes=4, their_prizes=4)
    obs = FakeObs(FakeSelect([FakeOption(7)], minCount=0, maxCount=0), state)
    assert scorer.ScoringAgent()(obs) == []
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --group ptcg pytest ptcg/tests/test_features.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ptcg.features'`.

- [ ] **Step 3: Implement features and the scoring agent**

Create `ptcg/features.py`:

```python
"""An interpretable evaluator for legal options.

Prize count is the spine. Pokemon TCG is a race to six prizes, so nearly every
sound heuristic is a proxy for "am I taking prizes faster than they are."
Anchoring every feature to that keeps the weight vector meaningful instead of a
bag of unrelated tricks -- which matters twice over here, because the Strategy
track is judged on explicability and the blog post has to show the reasoning.

Weights are hand-set starting points. Task 6's harness is what turns them into
tuned values; nothing in this file should be trusted until it has been measured.
"""

from __future__ import annotations

PRIZE_TOTAL = 6

# Option type ids from cg.api.OptionType, inlined so this module stays
# importable without the SDK (the tests exercise it with fakes).
PLAY = 7
ATTACH = 8
EVOLVE = 9
ABILITY = 10
RETREAT = 12
ATTACK = 13
END = 14

DEFAULT_WEIGHTS: dict[str, float] = {
    "prize_lead": 3.0,
    "is_attack": 4.0,
    "is_evolve": 1.5,
    "is_attach": 1.2,
    "is_ability": 1.0,
    "is_play": 0.8,
    "is_retreat": -0.3,
    "is_end": -2.0,
    "board_development": 0.6,
    "active_health": 0.5,
    "hand_size": 0.15,
}


def _me_and_them(state):
    mine = state.players[state.yourIndex]
    theirs = state.players[1 - state.yourIndex]
    return mine, theirs


def option_features(obs, option) -> dict[str, float]:
    """Extract the feature vector for one candidate option."""
    state = obs.current
    kind = int(getattr(option, "type", -1))

    out = {
        "is_attack": 1.0 if kind == ATTACK else 0.0,
        "is_evolve": 1.0 if kind == EVOLVE else 0.0,
        "is_attach": 1.0 if kind == ATTACH else 0.0,
        "is_ability": 1.0 if kind == ABILITY else 0.0,
        "is_play": 1.0 if kind == PLAY else 0.0,
        "is_retreat": 1.0 if kind == RETREAT else 0.0,
        "is_end": 1.0 if kind == END else 0.0,
        "prize_lead": 0.0,
        "board_development": 0.0,
        "active_health": 0.0,
        "hand_size": 0.0,
    }
    if state is None:
        return out

    mine, theirs = _me_and_them(state)

    # Prizes remaining counts down from 6, so *their* remaining minus *mine* is
    # our lead. Normalised to roughly [-1, 1].
    out["prize_lead"] = (len(theirs.prize) - len(mine.prize)) / PRIZE_TOTAL

    bench_room = max(1, mine.benchMax)
    out["board_development"] = len(mine.bench) / bench_room

    active = mine.active[0] if mine.active and mine.active[0] is not None else None
    if active is not None and active.maxHp:
        out["active_health"] = active.hp / active.maxHp

    out["hand_size"] = min(mine.handCount, 10) / 10.0
    return out


def score(obs, option, weights: dict[str, float] | None = None) -> float:
    vector = option_features(obs, option)
    active_weights = DEFAULT_WEIGHTS if weights is None else weights
    return float(sum(vector.get(k, 0.0) * w for k, w in active_weights.items()))


def rank(obs, weights: dict[str, float] | None = None):
    """Return `(index, score, features)` for every option, best first."""
    scored = [
        (i, score(obs, option, weights), option_features(obs, option))
        for i, option in enumerate(obs.select.option)
    ]
    scored.sort(key=lambda row: row[1], reverse=True)
    return scored
```

Create `ptcg/agents/scorer.py`:

```python
"""Greedy evaluator-driven agent: rank the legal options, take the best ones."""

from __future__ import annotations

from .. import features
from . import safe_agent


class ScoringAgent:
    name = "scorer"

    def __init__(self, weights: dict[str, float] | None = None, seed: int = 0):
        self.weights = weights or dict(features.DEFAULT_WEIGHTS)
        self._call = safe_agent(self._choose)

    def __call__(self, obs):
        return self._call(obs)

    def _choose(self, obs):
        select = obs.select
        available = len(select.option)
        hi = min(int(select.maxCount), available)
        lo = max(0, int(select.minCount))
        if hi <= 0:
            return []
        ranked = features.rank(obs, self.weights)
        return sorted(index for index, _, _ in ranked[: max(lo, 1)])
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --group ptcg pytest ptcg/tests/test_features.py -v`
Expected: 6 passed.

- [ ] **Step 5: Measure the scoring agent against both baselines**

```bash
uv run --group ptcg python -c "
from ptcg import decks, tourney
deck = decks.load_deck('ptcg/decks/ladder.csv')
me = ('ptcg.agents.scorer','ScoringAgent',{})
for mod, cls, label in [('ptcg.agents.baseline','RandomAgent','random'),
                        ('ptcg.agents.baseline','GreedyAttackAgent','greedy-attack')]:
    r = tourney.run_match(me, (mod, cls, {'seed':3}), deck, deck, n_pairs=200)
    print(r.summary('scorer', label))
"
```

The scoring agent must beat both with a confidence interval clear of 50%. If it doesn't, tune `DEFAULT_WEIGHTS` and re-measure — do not proceed on an unproven evaluator, since search only amplifies it. Record every measurement in the build log, including the failures.

- [ ] **Step 6: Commit**

```bash
git add ptcg/features.py ptcg/agents/scorer.py ptcg/tests/test_features.py posts/ptcg/notes/build-log.md
git commit -m "feat(ptcg): prize-tempo evaluator and greedy scoring agent"
```

---

### Task 8: Time bank

**Files:**
- Create: `ptcg/timebank.py`, `ptcg/tests/test_timebank.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `ptcg.timebank.TimeBank(total=600.0, reserve=60.0, expected_decisions=80)` with `allowance(obs) -> float` (seconds this decision may use) and `should_search(obs) -> bool`.

- [ ] **Step 1: Write the failing test**

Create `ptcg/tests/test_timebank.py`:

```python
from ptcg import timebank


class FakeSelect:
    def __init__(self, n):
        self.option = list(range(n))
        self.minCount = 1
        self.maxCount = 1


class FakeObs:
    def __init__(self, remaining, n_options=5):
        self.remainingOverageTime = remaining
        self.select = FakeSelect(n_options)
        self.current = None


def test_full_bank_grants_a_generous_allowance():
    bank = timebank.TimeBank(total=600.0, reserve=60.0, expected_decisions=80)
    assert bank.allowance(FakeObs(600.0)) > 5.0


def test_allowance_shrinks_as_the_bank_depletes():
    bank = timebank.TimeBank()
    assert bank.allowance(FakeObs(600.0)) > bank.allowance(FakeObs(120.0))


def test_reserve_is_never_spent():
    bank = timebank.TimeBank(total=600.0, reserve=60.0)
    assert bank.allowance(FakeObs(60.0)) == 0.0
    assert bank.allowance(FakeObs(30.0)) == 0.0


def test_forced_decisions_get_no_time():
    bank = timebank.TimeBank()
    assert bank.allowance(FakeObs(600.0, n_options=1)) == 0.0
    assert not bank.should_search(FakeObs(600.0, n_options=1))


def test_should_search_is_false_once_inside_the_reserve():
    bank = timebank.TimeBank(total=600.0, reserve=60.0)
    assert bank.should_search(FakeObs(600.0))
    assert not bank.should_search(FakeObs(45.0))


def test_missing_remaining_time_is_treated_as_empty():
    bank = timebank.TimeBank()

    class NoClock:
        select = FakeSelect(5)
        current = None

    assert bank.allowance(NoClock()) == 0.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --group ptcg pytest ptcg/tests/test_timebank.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ptcg.timebank'`.

- [ ] **Step 3: Implement the bank**

Create `ptcg/timebank.py`:

```python
"""Allocate the 600-second per-game budget across a game's decisions.

The clock is cumulative for the whole game and busting it is an instant loss, so
time is a resource to spend rather than a limit to stay under -- a chess clock.
Measured ladder behaviour: the field spends a median of 13.5 s of 600 (2.2%),
about 182 ms per decision, while roughly 8 s per decision is affordable. The
headroom is enormous, so the bank is deliberately generous, with two guards:

* a hard reserve that is never spent, so a slow endgame cannot forfeit; and
* zero time for forced decisions, which are ~10.8% of all decisions and where
  there is by definition nothing to think about.
"""

from __future__ import annotations


class TimeBank:
    def __init__(
        self,
        total: float = 600.0,
        reserve: float = 60.0,
        expected_decisions: int = 80,
    ):
        self.total = total
        self.reserve = reserve
        self.expected_decisions = max(1, expected_decisions)

    def _remaining(self, obs) -> float:
        value = getattr(obs, "remainingOverageTime", None)
        if value is None:
            return 0.0
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0

    def allowance(self, obs) -> float:
        """Seconds this decision may spend. Zero means answer immediately."""
        if len(obs.select.option) <= 1:
            return 0.0
        spendable = self._remaining(obs) - self.reserve
        if spendable <= 0:
            return 0.0
        # Spread what is left over a pessimistic count of decisions still to
        # come, so the allowance tapers instead of falling off a cliff.
        return spendable / self.expected_decisions

    def should_search(self, obs) -> bool:
        return self.allowance(obs) > 0.0
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --group ptcg pytest ptcg/tests/test_timebank.py -v`
Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add ptcg/timebank.py ptcg/tests/test_timebank.py
git commit -m "feat(ptcg): time bank allocating the 600s game clock"
```

---

### Task 9: Submission packaging, fuzz robustness, and first ladder upload

**This is the milestone that must land by ~Aug 9.** Everything after it is improvement; this is the entry.

**Files:**
- Create: `submission/main.py`, `ptcg/package.py`, `ptcg/tests/test_package.py`
- Modify: `ptcg/tests/test_agents.py`

**Interfaces:**
- Consumes: `ptcg.features`, `ptcg.agents`, `ptcg.decks`.
- Produces: `ptcg.package.build(dest='dist/submission', deck_path='ptcg/decks/ladder.csv') -> pathlib.Path` — copies the agent modules and deck next to `main.py` so the bundle has no dependency on the `ptcg` package or the SDK; `submission/main.py` exposing `agent(obs_dict) -> list[int]`.

- [ ] **Step 1: Write the failing fuzz test**

Append to `ptcg/tests/test_agents.py`:

```python
import random


def _fuzz_selects(n=400, seed=0):
    """Generate adversarial select payloads: empty options, min>len, huge
    counts, unknown option types, missing attributes."""
    rng = random.Random(seed)
    out = []
    for _ in range(n):
        count = rng.choice([0, 1, 1, 2, 5, 17])
        options = [FakeOption(rng.choice([0, 3, 7, 8, 13, 14, 99])) for _ in range(count)]
        lo = rng.choice([0, 1, 2, 9])
        hi = rng.choice([0, 1, 2, 9])
        select = FakeSelect(options, minCount=lo, maxCount=max(lo, hi))
        out.append(select)
    return out


@pytest.mark.parametrize("agent_factory", [
    lambda: baseline.RandomAgent(seed=0),
    lambda: baseline.GreedyAttackAgent(seed=0),
])
def test_agents_never_raise_on_adversarial_selects(agent_factory):
    agent = agent_factory()
    for select in _fuzz_selects():
        picks = agent(FakeObs(select))
        assert isinstance(picks, list)
        assert len(picks) == len(set(picks))
        assert all(0 <= p < len(select.option) for p in picks)
        assert len(picks) <= max(0, min(select.maxCount, len(select.option)))
```

Create `ptcg/tests/test_package.py`:

```python
import json
import subprocess
import sys

from ptcg import package


def test_build_produces_a_self_contained_bundle(tmp_path):
    dest = package.build(dest=tmp_path / "submission")
    assert (dest / "main.py").is_file()
    assert (dest / "deck.csv").is_file()
    deck = (dest / "deck.csv").read_text().strip().split("\n")
    assert len(deck) == 60


def test_bundle_imports_without_the_ptcg_package(tmp_path):
    """The bundle must not import `ptcg` -- Kaggle only uploads this directory."""
    dest = package.build(dest=tmp_path / "submission")
    probe = (
        "import json,sys; sys.path.insert(0, %r); import main; "
        "print(main.agent({'select': None}))" % str(dest)
    )
    out = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True, cwd=dest
    )
    assert out.returncode == 0, out.stderr
    assert len(json.loads(out.stdout.replace("'", '"'))) == 60
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `uv run --group ptcg pytest ptcg/tests/test_package.py ptcg/tests/test_agents.py -v`
Expected: `test_package.py` FAILs with `ModuleNotFoundError: No module named 'ptcg.package'`; the fuzz test may already pass thanks to `safe_agent` — if it fails, fix `_repair` before continuing.

- [ ] **Step 3: Implement the submission entry point and packager**

Create `submission/main.py`:

```python
"""Kaggle entry point.

Kaggle uploads this directory and imports `main.agent`. The bundle is
self-contained: `features.py` and `agent_impl.py` are copied in beside this
file by `ptcg.package.build`, so nothing here imports the `ptcg` package.
"""

import os

_DECK_CACHE = None


def _read_deck():
    global _DECK_CACHE
    if _DECK_CACHE is not None:
        return _DECK_CACHE
    path = "deck.csv"
    if not os.path.exists(path):
        path = "/kaggle_simulations/agent/deck.csv"
    with open(path) as handle:
        lines = handle.read().split("\n")
    _DECK_CACHE = [int(line) for line in lines if line.strip()][:60]
    return _DECK_CACHE


def agent(obs_dict: dict) -> list[int]:
    """Never raise: an exception forfeits the game."""
    try:
        from cg.api import to_observation_class

        obs = to_observation_class(obs_dict)
        if obs.select is None:
            return _read_deck()

        import agent_impl

        return agent_impl.choose(obs)
    except BaseException:
        try:
            select = obs_dict.get("select")
            if select is None:
                return _read_deck()
            return list(range(max(0, int(select.get("minCount", 0)))))
        except BaseException:
            return [0]
```

Create `ptcg/package.py`:

```python
"""Assemble the Kaggle submission bundle.

Kaggle uploads one directory and imports `main.agent` from it, so the bundle
cannot import the `ptcg` package. Rather than maintaining a divergent copy of
the agent, this copies the small pure-Python modules it needs and generates a
thin `agent_impl.py` shim.
"""

from __future__ import annotations

import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEFAULT_DECK = ROOT / "ptcg" / "decks" / "ladder.csv"

_AGENT_IMPL = '''"""Generated by ptcg.package.build -- do not edit."""

import features

_WEIGHTS = features.DEFAULT_WEIGHTS


def choose(obs):
    select = obs.select
    available = len(select.option)
    hi = min(int(select.maxCount), available)
    lo = max(0, int(select.minCount))
    if hi <= 0:
        return []
    ranked = features.rank(obs, _WEIGHTS)
    return sorted(index for index, _, _ in ranked[: max(lo, 1)])
'''


def build(
    dest: pathlib.Path | str = ROOT / "dist" / "submission",
    deck_path: pathlib.Path | str = DEFAULT_DECK,
) -> pathlib.Path:
    dest = pathlib.Path(dest)
    dest.mkdir(parents=True, exist_ok=True)

    shutil.copy(ROOT / "submission" / "main.py", dest / "main.py")
    shutil.copy(ROOT / "ptcg" / "features.py", dest / "features.py")
    (dest / "agent_impl.py").write_text(_AGENT_IMPL)

    deck = pathlib.Path(deck_path)
    if not deck.is_file():
        deck = ROOT / "ptcg" / "engine" / "sample_submission" / "sample_submission" / "deck.csv"
    shutil.copy(deck, dest / "deck.csv")

    return dest
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `uv run --group ptcg pytest ptcg/tests/ -v`
Expected: all tests pass.

- [ ] **Step 5: Verify the bundle plays a real game before uploading**

```bash
uv run --group ptcg python -c "
import sys
from ptcg import engine, package, decks

dest = package.build()
sys.path.insert(0, str(dest)); sys.path.insert(0, str(engine.SDK_PATH))
import agent_impl

deck = decks.load_deck('ptcg/decks/ladder.csv')
bundled = lambda obs: agent_impl.choose(obs)
result = engine.play_game(bundled, bundled, deck, deck, seed=0)
print('bundle at', dest)
print('bundled agent played a full game:', result.winner in (0, 1),
      '| decisions', result.decisions, '|', round(result.seconds * 1000), 'ms')
"
```

This exercises the *bundled* copy of the agent, not the `ptcg` package version —
the point is to catch a packaging mistake (a missing module, a stale
`features.py`) before it costs a day of the 5-per-day submission budget.

Then upload and confirm it appears on the leaderboard:

```bash
cd dist/submission && zip -r ../submission.zip . && cd -
kaggle competitions submit -c pokemon-tcg-ai-battle -f dist/submission.zip -m "scorer v1: prize-tempo evaluator"
kaggle competitions submissions -c pokemon-tcg-ai-battle | head -5
```

- [ ] **Step 6: Commit**

```bash
git add submission/ ptcg/package.py ptcg/tests/test_package.py ptcg/tests/test_agents.py posts/ptcg/notes/build-log.md
git commit -m "feat(ptcg): self-contained Kaggle submission bundle and fuzz hardening"
```

---

### Task 10: Determinization — sampling hidden-information worlds

**Files:**
- Create: `ptcg/determinize.py`, `ptcg/tests/test_determinize.py`

**Interfaces:**
- Consumes: `ptcg.engine.load_api`, `ptcg.decks`.
- Produces: `ptcg.determinize.KnownCards` frozen dataclass with `my_deck: tuple[int, ...]`, `my_prize: tuple[int, ...]`, `opponent_deck: tuple[int, ...]`, `opponent_prize: tuple[int, ...]`, `opponent_hand: tuple[int, ...]`, `opponent_active: tuple[int, ...]` (frozen tuples so worlds are hashable and comparable, which the reproducibility test relies on); `ptcg.determinize.seen_cards(obs) -> collections.Counter`; `ptcg.determinize.sample_world(obs, my_full_deck, opponent_prior, rng) -> KnownCards`; `ptcg.determinize.search_kwargs(world) -> dict` mapping to `search_begin`'s keyword arguments.

- [ ] **Step 1: Write the failing test**

Create `ptcg/tests/test_determinize.py`:

```python
import collections
import random

import pytest

from ptcg import determinize


class FakeCard:
    def __init__(self, cid):
        self.id = cid


class FakePokemon:
    def __init__(self, cid):
        self.id = cid
        self.hp = 100
        self.maxHp = 100
        self.energyCards = []
        self.tools = []
        self.preEvolution = []


class FakePlayer:
    def __init__(self, deck_count, prize_n, hand=None, hand_count=0, discard=(), bench=(), active=None):
        self.deckCount = deck_count
        self.prize = [None] * prize_n
        self.hand = hand
        self.handCount = hand_count if hand is None else len(hand)
        self.discard = [FakeCard(c) for c in discard]
        self.bench = [FakePokemon(c) for c in bench]
        self.active = [FakePokemon(active)] if active is not None else []
        self.benchMax = 5


class FakeState:
    def __init__(self, mine, theirs):
        self.yourIndex = 0
        self.players = [mine, theirs]
        self.turn = 5
        self.result = -1


class FakeObs:
    def __init__(self, state):
        self.current = state
        self.select = type("S", (), {"option": [1, 2], "minCount": 1, "maxCount": 1, "deck": None})()
        self.search_begin_input = "fake-state-blob"


def _obs():
    mine = FakePlayer(
        deck_count=30, prize_n=5, hand=[FakeCard(10), FakeCard(11)],
        discard=(12,), bench=(13,), active=14,
    )
    theirs = FakePlayer(
        deck_count=28, prize_n=4, hand=None, hand_count=6,
        discard=(20,), bench=(21,), active=22,
    )
    return FakeObs(FakeState(mine, theirs))


def test_seen_cards_counts_everything_visible():
    seen = determinize.seen_cards(_obs())
    assert seen[10] == 1 and seen[12] == 1 and seen[14] == 1
    assert seen[22] == 1


def test_sampled_world_matches_the_required_counts():
    obs = _obs()
    my_full = [10, 11, 12, 13, 14] + [99] * 55
    prior = [50] * 60
    world = determinize.sample_world(obs, my_full, prior, random.Random(0))
    state = obs.current
    assert len(world.my_deck) == state.players[0].deckCount
    assert len(world.my_prize) == len(state.players[0].prize)
    assert len(world.opponent_deck) == state.players[1].deckCount
    assert len(world.opponent_prize) == len(state.players[1].prize)
    assert len(world.opponent_hand) == state.players[1].handCount


def test_my_unseen_cards_are_drawn_from_my_own_deck_list():
    obs = _obs()
    my_full = [10, 11, 12, 13, 14] + [99] * 55
    world = determinize.sample_world(obs, my_full, [50] * 60, random.Random(1))
    # Everything unaccounted for in my list is card 99.
    assert set(world.my_deck + world.my_prize) <= {99}


def test_sampling_is_reproducible_for_a_seed():
    obs = _obs()
    args = (obs, [10, 11, 12, 13, 14] + [99] * 55, [50] * 60)
    a = determinize.sample_world(*args, random.Random(5))
    b = determinize.sample_world(*args, random.Random(5))
    assert a == b


def test_search_kwargs_uses_the_api_parameter_names():
    obs = _obs()
    world = determinize.sample_world(obs, [99] * 60, [50] * 60, random.Random(0))
    kwargs = determinize.search_kwargs(world)
    assert set(kwargs) == {
        "your_deck", "your_prize", "opponent_deck",
        "opponent_prize", "opponent_hand", "opponent_active",
    }
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --group ptcg pytest ptcg/tests/test_determinize.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ptcg.determinize'`.

- [ ] **Step 3: Implement determinization**

Create `ptcg/determinize.py`:

```python
"""Sample consistent hidden-information worlds for `search_begin`.

`search_begin` will not fork the current state on its own -- it demands a full
hypothesis for every hidden card: both decks, both prize sets, the opponent's
hand, and their Active if it is face down. So the agent is a
Perfect-Information Monte Carlo player: sample worlds, search each as if fully
observable, and combine the verdicts.

The two sides are asymmetric, and that asymmetry is the edge:

* Our own deck we know exactly -- we submitted it. Subtracting every card we
  have seen leaves the precise multiset still hidden; only the order is unknown.
* The opponent's list we must guess. A generic prior is weak, but submitted decks
  are public in the next day's episode dumps and lists get copied verbatim, so a
  fingerprint of their opening plays can often identify their actual 60.
"""

from __future__ import annotations

import collections
import random
from dataclasses import dataclass


@dataclass(frozen=True)
class KnownCards:
    my_deck: tuple[int, ...]
    my_prize: tuple[int, ...]
    opponent_deck: tuple[int, ...]
    opponent_prize: tuple[int, ...]
    opponent_hand: tuple[int, ...]
    opponent_active: tuple[int, ...]


def _pokemon_ids(pokemon_list) -> list[int]:
    out = []
    for mon in pokemon_list or []:
        if mon is None:
            continue
        out.append(mon.id)
        for attached in list(getattr(mon, "energyCards", []) or []) + list(
            getattr(mon, "tools", []) or []
        ) + list(getattr(mon, "preEvolution", []) or []):
            out.append(attached.id)
    return out


def seen_cards(obs) -> collections.Counter:
    """Every card either player can currently observe."""
    counter: collections.Counter = collections.Counter()
    state = obs.current
    for player in state.players:
        for card in player.discard or []:
            counter[card.id] += 1
        counter.update(_pokemon_ids(player.active))
        counter.update(_pokemon_ids(player.bench))
        if player.hand:
            for card in player.hand:
                counter[card.id] += 1
        for card in player.prize or []:
            if card is not None:
                counter[card.id] += 1
    return counter


def _draw(pool: list[int], n: int, rng: random.Random) -> list[int]:
    """Take n cards from pool (mutating it), padding by reuse if it runs short."""
    out: list[int] = []
    for _ in range(n):
        if pool:
            out.append(pool.pop(rng.randrange(len(pool))))
        elif out:
            out.append(out[0])
        else:
            out.append(0)
    return out


def sample_world(obs, my_full_deck, opponent_prior, rng: random.Random) -> KnownCards:
    """Draw one consistent assignment of the hidden cards."""
    state = obs.current
    mine = state.players[state.yourIndex]
    theirs = state.players[1 - state.yourIndex]

    seen = seen_cards(obs)

    # Our side: exact multiset, unknown order.
    my_hidden = list(my_full_deck)
    for card_id, count in seen.items():
        for _ in range(count):
            if card_id in my_hidden:
                my_hidden.remove(card_id)
    rng.shuffle(my_hidden)
    my_prize = _draw(my_hidden, len(mine.prize), rng)
    my_deck = _draw(my_hidden, mine.deckCount, rng)

    # Their side: guessed from the prior, minus what we have watched them use.
    their_hidden = list(opponent_prior)
    for card in theirs.discard or []:
        if card.id in their_hidden:
            their_hidden.remove(card.id)
    for card_id in _pokemon_ids(theirs.active) + _pokemon_ids(theirs.bench):
        if card_id in their_hidden:
            their_hidden.remove(card_id)
    rng.shuffle(their_hidden)
    opponent_hand = _draw(their_hidden, theirs.handCount, rng)
    opponent_prize = _draw(their_hidden, len(theirs.prize), rng)
    opponent_deck = _draw(their_hidden, theirs.deckCount, rng)

    # Only required when their Active is face down.
    needs_active = bool(theirs.active) and theirs.active[0] is None
    opponent_active = [opponent_prior[0]] if needs_active and opponent_prior else []

    return KnownCards(
        my_deck=tuple(my_deck),
        my_prize=tuple(my_prize),
        opponent_deck=tuple(opponent_deck),
        opponent_prize=tuple(opponent_prize),
        opponent_hand=tuple(opponent_hand),
        opponent_active=tuple(opponent_active),
    )


def search_kwargs(world: KnownCards) -> dict:
    """Map a sampled world onto `search_begin`'s keyword arguments."""
    return {
        "your_deck": list(world.my_deck),
        "your_prize": list(world.my_prize),
        "opponent_deck": list(world.opponent_deck),
        "opponent_prize": list(world.opponent_prize),
        "opponent_hand": list(world.opponent_hand),
        "opponent_active": list(world.opponent_active),
    }
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --group ptcg pytest ptcg/tests/test_determinize.py -v`
Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add ptcg/determinize.py ptcg/tests/test_determinize.py
git commit -m "feat(ptcg): hidden-information determinization for PIMC search"
```

---

### Task 11: PIMC search agent, measured against the greedy scorer

**Files:**
- Create: `ptcg/search.py`, `ptcg/agents/pimc.py`, `ptcg/tests/test_search.py`

**Interfaces:**
- Consumes: `ptcg.determinize`, `ptcg.features`, `ptcg.timebank`, `ptcg.engine.load_api`.
- Produces: `ptcg.search.evaluate_options(obs, my_full_deck, opponent_prior, allowance, n_worlds, rng, weights=None) -> dict[int, float]` mapping option index to averaged value; `ptcg.agents.pimc.PIMCAgent(my_deck, opponent_prior, weights=None, n_worlds=8, seed=0, bank=None)`.

- [ ] **Step 1: Write the failing test**

Create `ptcg/tests/test_search.py`:

```python
import random

import pytest

from ptcg import engine, search, timebank
from ptcg.agents import pimc


class FakeSelect:
    def __init__(self, n):
        self.option = [type("O", (), {"type": 13, "attackId": 1})() for _ in range(n)]
        self.minCount = 1
        self.maxCount = 1
        self.deck = None


class FakeObs:
    def __init__(self, remaining=600.0, n=3):
        self.select = FakeSelect(n)
        self.current = None
        self.remainingOverageTime = remaining
        self.search_begin_input = None


def test_evaluate_options_returns_empty_without_a_state():
    values = search.evaluate_options(
        FakeObs(), [1] * 60, [2] * 60, allowance=1.0, n_worlds=2, rng=random.Random(0)
    )
    assert values == {}


def test_pimc_agent_falls_back_to_greedy_with_no_time():
    agent = pimc.PIMCAgent(
        my_deck=[1] * 60, opponent_prior=[2] * 60,
        bank=timebank.TimeBank(total=600.0, reserve=600.0),
    )
    picks = agent(FakeObs(remaining=600.0, n=4))
    assert len(picks) == 1 and 0 <= picks[0] < 4


def test_pimc_agent_never_raises_on_a_forced_decision():
    agent = pimc.PIMCAgent(my_deck=[1] * 60, opponent_prior=[2] * 60)
    assert agent(FakeObs(n=1)) == [0]


@pytest.mark.skipif(not engine.engine_available(), reason="cabt engine not downloaded")
def test_pimc_agent_completes_a_real_game_within_budget():
    from ptcg import decks

    deck = engine.sample_deck()
    agent = pimc.PIMCAgent(my_deck=deck, opponent_prior=deck, n_worlds=2)
    opponent = pimc.PIMCAgent(my_deck=deck, opponent_prior=deck, n_worlds=2)
    result = engine.play_game(agent, opponent, deck, deck, seed=3)
    assert result.winner in (0, 1)
    # Both sides must stay inside the 600 s clock with room to spare.
    assert result.seconds < 600.0
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `uv run --group ptcg pytest ptcg/tests/test_search.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'ptcg.search'`.

- [ ] **Step 3: Implement the search driver and agent**

Create `ptcg/search.py`:

```python
"""Perfect-Information Monte Carlo evaluation of the current decision.

For each sampled world: fork the engine state with `search_begin`, try every
legal option one `search_step` deep, and score the resulting position with the
same interpretable evaluator the greedy agent uses. Average each option's value
across worlds, so a move that is only good in one lucky assignment of the hidden
cards does not win.

Depth is deliberately shallow to start. Measured throughput is ~13,000
`search_step` calls per second with ~104,000 affordable per decision, so there is
room to go much deeper -- but depth over a weak evaluator only buys
confidently-wrong moves, so the evaluator earns depth by first beating the
baselines outright.
"""

from __future__ import annotations

import random
import time

from . import determinize, features


def evaluate_options(
    obs,
    my_full_deck,
    opponent_prior,
    allowance: float,
    n_worlds: int,
    rng: random.Random,
    weights: dict[str, float] | None = None,
) -> dict[int, float]:
    """Average value per option index across sampled worlds. Empty if unusable."""
    if obs.current is None or getattr(obs, "search_begin_input", None) is None:
        return {}
    if allowance <= 0 or n_worlds <= 0:
        return {}

    from . import engine

    api = engine.load_api()
    n_options = len(obs.select.option)
    if n_options <= 1:
        return {}

    totals: dict[int, float] = {i: 0.0 for i in range(n_options)}
    counts: dict[int, int] = {i: 0 for i in range(n_options)}
    deadline = time.perf_counter() + allowance

    for _ in range(n_worlds):
        if time.perf_counter() >= deadline:
            break
        world = determinize.sample_world(obs, my_full_deck, opponent_prior, rng)
        try:
            root = api.search_begin(obs, **determinize.search_kwargs(world))
        except (ValueError, RuntimeError):
            continue

        for index in range(n_options):
            if time.perf_counter() >= deadline:
                break
            try:
                state = api.search_step(root.searchId, [index])
            except (ValueError, IndexError, RuntimeError):
                continue
            child = state.observation
            if child.current is None:
                continue
            if child.current.result != -1:
                value = 100.0 if child.current.result == obs.current.yourIndex else -100.0
            else:
                value = features.score(child, obs.select.option[index], weights)
            totals[index] += value
            counts[index] += 1

        try:
            api.search_end()
        except (ValueError, RuntimeError):
            pass

    return {i: totals[i] / counts[i] for i in range(n_options) if counts[i]}
```

Create `ptcg/agents/pimc.py`:

```python
"""Search agent with a guaranteed greedy fallback.

Whenever the bank says there is no time, the search API refuses, or nothing
comes back, this degrades to exactly the greedy scorer's choice. The fallback is
the reason the agent is safe to submit at all.
"""

from __future__ import annotations

import random

from .. import features, search, timebank
from . import safe_agent


class PIMCAgent:
    name = "pimc"

    def __init__(
        self,
        my_deck,
        opponent_prior,
        weights: dict[str, float] | None = None,
        n_worlds: int = 8,
        seed: int = 0,
        bank: timebank.TimeBank | None = None,
    ):
        self.my_deck = list(my_deck)
        self.opponent_prior = list(opponent_prior)
        self.weights = weights or dict(features.DEFAULT_WEIGHTS)
        self.n_worlds = n_worlds
        self.bank = bank or timebank.TimeBank()
        self._rng = random.Random(seed)
        self._call = safe_agent(self._choose)

    def __call__(self, obs):
        return self._call(obs)

    def _greedy(self, obs):
        select = obs.select
        lo = max(0, int(select.minCount))
        if min(int(select.maxCount), len(select.option)) <= 0:
            return []
        ranked = features.rank(obs, self.weights)
        return sorted(index for index, _, _ in ranked[: max(lo, 1)])

    def _choose(self, obs):
        select = obs.select
        if min(int(select.maxCount), len(select.option)) <= 0:
            return []
        allowance = self.bank.allowance(obs)
        if allowance <= 0:
            return self._greedy(obs)

        values = search.evaluate_options(
            obs,
            self.my_deck,
            self.opponent_prior,
            allowance=allowance,
            n_worlds=self.n_worlds,
            rng=self._rng,
            weights=self.weights,
        )
        if not values:
            return self._greedy(obs)

        lo = max(1, int(select.minCount))
        best = sorted(values, key=lambda i: values[i], reverse=True)[:lo]
        return sorted(best)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `uv run --group ptcg pytest ptcg/tests/test_search.py -v`
Expected: 4 passed.

- [ ] **Step 5: Measure search against greedy — the decisive experiment**

```bash
uv run --group ptcg python -c "
from ptcg import decks, tourney
deck = decks.load_deck('ptcg/decks/ladder.csv')
r = tourney.run_match(
    ('ptcg.agents.pimc','PIMCAgent',{'my_deck':deck,'opponent_prior':deck,'n_worlds':8}),
    ('ptcg.agents.scorer','ScoringAgent',{}),
    deck, deck, n_pairs=200)
print(r.summary('pimc','scorer'))
"
```

Record the result in the build log **whatever it says.** If PIMC does not beat greedy with an interval clear of 50%, that is a finding — the one ladder agent observed spending real time also lost — and the honest move is to submit the greedy scorer and report the negative result in the Strategy write-up. Do not ship a slower agent that isn't measurably better.

- [ ] **Step 6: Commit**

```bash
git add ptcg/search.py ptcg/agents/pimc.py ptcg/tests/test_search.py posts/ptcg/notes/build-log.md
git commit -m "feat(ptcg): PIMC search agent with greedy fallback"
```

---

## Deferred to a follow-up plan (Aug 17 – Sep 13)

Out of scope here, to keep this plan focused on a ladder entry:

- **Decision-trace emission** (`ptcg/trace.py`) and the **annotated replay viewer** (`posts/ptcg/replay/`). Needs its own plan — the trace schema should mirror the episode dumps' `steps[i][player]` shape, which is already what the ladder emits.
- **Opponent fingerprinting**: match observed plays against the archetype→decklist table from `episodes.census` to determinize against the opponent's *actual* 60 rather than a generic prior. The highest-value strengthening available, and the likely spine of the Strategy report — but it needs a working PIMC agent first.
- **Full turn-sequence search.** Task 11 evaluates one `search_step` deep, which
  is enough to prove the determinization plumbing works but does *not* yet capture
  the spec's core point that a turn is a sequence (playing a Supporter first
  constrains everything after it). Deepening to full within-turn sequence
  enumeration is the first upgrade once 1-ply PIMC is measured — the budget allows
  roughly 104,000 `search_step` calls per decision, so depth is affordable; it is
  gated on the evaluator earning it.
- **Weight tuning sweeps** on the remote box, and the **Strategy report** itself.
- The blog post (`posts/ptcg/index.qmd`) and adding `posts/ptcg/replay/**` to `_quarto.yml`'s `resources:`.
