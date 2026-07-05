# Jeopardy Scraper + Storage (Sub-project A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an offline, resumable j-archive crawler that produces a committed, analysis-ready `clues.parquet` of all Jeopardy clues.

**Architecture:** Three-stage offline pipeline behind a single `click` CLI. `fetch` does polite, cached HTTP; `parse` turns cached HTML into faithful per-game records; `crawl` orchestrates resumably into an append-only JSONL archive; `build` curates that archive into a compact zstd Parquet. The JSONL is the faithful raw layer (gitignored); the Parquet is the curated committed artifact.

**Tech Stack:** Python 3.12+, `httpx` (HTTP), `beautifulsoup4` + `lxml` (parsing), `click` (CLI), `pandas` + `pyarrow` (Parquet), `pytest` (tests). All managed by `uv`.

## Global Constraints

- Python `>=3.12` (matches `pyproject.toml`).
- Runtime scraper deps (`httpx`, `beautifulsoup4`, `lxml`, `click`, `pytest`) live in a **`scraper` uv dependency group**, kept out of CI's `uv sync --frozen`. `pyarrow` goes in **main deps** (the future post reads the Parquet during CI render).
- Base URL: `https://www.j-archive.com`.
- User-Agent for all requests: `jeopardy-ds-research (personal research; contact nick@gray-os.com)`.
- Politeness: sequential requests only; sleep `1.0 + random.uniform(0, 0.5)` seconds **between network fetches** (never on cache hits).
- Heavy raw data (`jeopardy/data/`) is **gitignored**; only `posts/jeopardy_ds/clues.parquet` is committed.
- Parquet compression: `zstd`.
- `clue_value` for daily doubles is the **board position value** (derived), not the wager; the wager goes in `dd_wager`.
- Dollar-value doubling boundary: air dates `>= 2001-11-26` use the doubled ladder.
- `season` is stored as a **string** (numeric ids like `"36"` and named ids like `"goattournament"` coexist).
- Run commands from the **repo root** with `uv run` (e.g. `uv run --group scraper python -m jeopardy crawl`, `uv run --group scraper pytest jeopardy/tests -v`).

---

## Data contracts

**Per-game JSONL record** (one line per game in `jeopardy/data/games.jsonl`):

```json
{
  "game_id": 6699,
  "season": "36",
  "show_number": 8235,
  "air_date": "2020-06-12",
  "game_comments": "Zach Newkirk game 4. Last game of Season 36. ...",
  "clues": [
    {"round": "J", "row": 1, "col": 1, "category": "CLASSIC AUTOMOBILES",
     "value": 200, "is_daily_double": false, "dd_wager": null,
     "clue": "In 1913 this model from Ford became the first mass-produced car...",
     "answer": "the Model T", "order_number": 17},
    {"round": "Final", "row": null, "col": null, "category": "AUTHORS",
     "value": null, "is_daily_double": false, "dd_wager": null,
     "clue": "On this woman's passing in 2019, Oprah...", "answer": "...",
     "order_number": null}
  ]
}
```

- `game_id` and `season` are injected by `crawl` (they come from the URL context, not the page).
- Everything else comes from `parse_game(html)`.
- For non-DD board clues, `value` is the parsed displayed dollar amount. For DD clues, `value` is `null` and `dd_wager` holds the parsed wager. Final Jeopardy has `value=null`, `row=null`, `col=null`.

**Parquet columns** (one row per clue in `posts/jeopardy_ds/clues.parquet`):
`game_id, air_date, season, game_type, round, category, clue_value, row, column, is_daily_double, dd_wager, clue, answer`
— where `round` is the full name (`Jeopardy`/`Double Jeopardy`/`Final`), `game_type` is derived, and `clue_value` is the board value (parsed for non-DD, ladder-derived for DD).

## File structure

```
jeopardy/
  __init__.py            # marks package (empty)
  __main__.py            # `python -m jeopardy` → cli()
  config.py              # paths + constants (URLs, UA, delays, ladder boundary)
  fetch.py               # fetch(url, cache_key) with on-disk HTML cache
  parse.py               # parse_game(html) -> dict | None
  crawl.py               # season/game enumeration + resumable orchestration
  build_parquet.py       # games.jsonl -> clues.parquet (curation + derivation)
  main.py                # click CLI group: crawl / build / all
  data/                  # gitignored: html_cache/, games.jsonl
  tests/
    fixtures/            # committed sample HTML pages
      game_modern.html   # game_id 6699 (post-2001 regular game)
      listseasons.html
      season36.html
    test_parse.py
    test_crawl.py
    test_build.py
    test_cli.py
```

---

## Task 1: Package scaffold, dependencies, gitignore, fixtures

**Files:**
- Create: `jeopardy/__init__.py`, `jeopardy/__main__.py`, `jeopardy/config.py`, `jeopardy/main.py`
- Create: `jeopardy/tests/__init__.py`, `jeopardy/tests/fixtures/` (with saved HTML)
- Modify: `pyproject.toml` (via uv), `.gitignore`
- Test: `jeopardy/tests/test_cli.py`

**Interfaces:**
- Produces: `jeopardy.config` constants (`BASE_URL`, `USER_AGENT`, `MIN_DELAY`, `MAX_DELAY`, `VALUE_DOUBLING_DATE`, `HTML_CACHE`, `JSONL_PATH`, `PARQUET_PATH`, `DATA_DIR`); `jeopardy.main.cli` (a `click.Group` with commands `crawl`, `build`, `all`).

- [ ] **Step 1: Add dependencies via uv**

Run (from repo root):
```bash
uv add pyarrow
uv add --group scraper httpx beautifulsoup4 lxml click pytest
```
Expected: `pyproject.toml` gains `pyarrow` under `[project].dependencies` and a `[dependency-groups] scraper = [...]`; `uv.lock` updates.

- [ ] **Step 2: Update `.gitignore`**

Append these lines to `.gitignore`:
```
# Jeopardy scraper raw data (regenerated by `python -m jeopardy crawl`)
jeopardy/data/
```

- [ ] **Step 3: Create `jeopardy/__init__.py` (empty) and `jeopardy/tests/__init__.py` (empty)**

Both files are empty.

- [ ] **Step 4: Create `jeopardy/config.py`**

```python
"""Shared paths and constants for the jeopardy offline pipeline."""
from pathlib import Path

BASE_URL = "https://www.j-archive.com"
USER_AGENT = "jeopardy-ds-research (personal research; contact nick@gray-os.com)"

# Politeness: seconds to sleep between *network* fetches (not cache hits).
MIN_DELAY = 1.0
MAX_DELAY = 1.5

# Clue dollar values doubled on this air date; used to derive board values.
VALUE_DOUBLING_DATE = "2001-11-26"

PKG_DIR = Path(__file__).resolve().parent          # .../jeopardy
REPO_ROOT = PKG_DIR.parent                          # repo root
DATA_DIR = PKG_DIR / "data"
HTML_CACHE = DATA_DIR / "html_cache"
JSONL_PATH = DATA_DIR / "games.jsonl"
PARQUET_PATH = REPO_ROOT / "posts" / "jeopardy_ds" / "clues.parquet"
```

- [ ] **Step 5: Create `jeopardy/main.py` with the click skeleton**

```python
"""Single CLI entry point for the jeopardy offline pipeline."""
import click


@click.group()
def cli():
    """Scrape j-archive and build the committed clues dataset."""


@cli.command()
def crawl():
    """Resumably fetch all games into data/games.jsonl (+ html_cache/)."""
    from jeopardy.crawl import run_crawl
    run_crawl()


@cli.command()
def build():
    """Build posts/jeopardy_ds/clues.parquet from data/games.jsonl."""
    from jeopardy.build_parquet import run_build
    run_build()


@cli.command(name="all")
def all_():
    """Run crawl, then build."""
    from jeopardy.crawl import run_crawl
    from jeopardy.build_parquet import run_build
    run_crawl()
    run_build()
```

(Imports are deferred inside commands so `--help` works before later modules exist.)

- [ ] **Step 6: Create `jeopardy/__main__.py`**

```python
from jeopardy.main import cli

if __name__ == "__main__":
    cli()
```

- [ ] **Step 7: Save fixture HTML pages**

Run (from repo root) to capture the fixtures the parser tests read:
```bash
mkdir -p jeopardy/tests/fixtures
UA="jeopardy-ds-research (personal research; contact nick@gray-os.com)"
curl -s -A "$UA" "https://www.j-archive.com/listseasons.php" -o jeopardy/tests/fixtures/listseasons.html
sleep 1
curl -s -A "$UA" "https://www.j-archive.com/showseason.php?season=36" -o jeopardy/tests/fixtures/season36.html
sleep 1
curl -s -A "$UA" "https://www.j-archive.com/showgame.php?game_id=6699" -o jeopardy/tests/fixtures/game_modern.html
```
Expected: three non-empty HTML files (~13 KB, ~71 KB, ~75 KB).

- [ ] **Step 8: Write the CLI test**

Create `jeopardy/tests/test_cli.py`:
```python
from click.testing import CliRunner
from jeopardy.main import cli


def test_cli_exposes_commands():
    result = CliRunner().invoke(cli, ["--help"])
    assert result.exit_code == 0
    for cmd in ("crawl", "build", "all"):
        assert cmd in result.output
```

- [ ] **Step 9: Run the test**

Run: `uv run --group scraper pytest jeopardy/tests/test_cli.py -v`
Expected: PASS.

- [ ] **Step 10: Commit**

```bash
git add jeopardy/ pyproject.toml uv.lock .gitignore
git commit -m "feat(jeopardy): scaffold scraper package, deps, CLI skeleton"
```

---

## Task 2: Parse game metadata

**Files:**
- Create: `jeopardy/parse.py`
- Test: `jeopardy/tests/test_parse.py`

**Interfaces:**
- Produces: `parse_game(page_html: str) -> dict | None`. Returns `None` for a missing/unaired game (no `game_title`). Otherwise a dict with keys `show_number: int|None`, `air_date: str|None` (ISO), `game_comments: str`, and `clues: list[dict]` (filled in later tasks; empty for now).

- [ ] **Step 1: Write the failing test**

Create `jeopardy/tests/test_parse.py`:
```python
from pathlib import Path
from jeopardy.parse import parse_game

FIXTURES = Path(__file__).parent / "fixtures"


def _modern():
    return (FIXTURES / "game_modern.html").read_text()


def test_parse_game_metadata():
    game = parse_game(_modern())
    assert game is not None
    assert game["show_number"] == 8235
    assert game["air_date"] == "2020-06-12"
    assert "Zach Newkirk" in game["game_comments"]


def test_parse_game_missing_returns_none():
    assert parse_game("<html><body>nothing here</body></html>") is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --group scraper pytest jeopardy/tests/test_parse.py -v`
Expected: FAIL (`ModuleNotFoundError: jeopardy.parse`).

- [ ] **Step 3: Implement metadata parsing**

Create `jeopardy/parse.py`:
```python
"""Turn a cached j-archive game page into a faithful per-game record."""
import re
from bs4 import BeautifulSoup

_TITLE_RE = re.compile(r"Show #(\d+),\s*aired\s*(\d{4}-\d{2}-\d{2})")


def parse_game(page_html):
    """Parse a game page. Returns None if the page has no game (unaired/missing)."""
    soup = BeautifulSoup(page_html, "lxml")
    if soup.find("div", id="game_title") is None:
        return None

    show_number = None
    air_date = None
    title = soup.find("title")
    if title:
        m = _TITLE_RE.search(title.get_text())
        if m:
            show_number = int(m.group(1))
            air_date = m.group(2)

    comments_div = soup.find("div", id="game_comments")
    game_comments = comments_div.get_text(" ", strip=True) if comments_div else ""

    clues = []
    clues += _parse_board_clues(soup)
    clues += _parse_final_clue(soup)

    return {
        "show_number": show_number,
        "air_date": air_date,
        "game_comments": game_comments,
        "clues": clues,
    }


def _parse_board_clues(soup):
    return []  # implemented in Task 3


def _parse_final_clue(soup):
    return []  # implemented in Task 4
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run --group scraper pytest jeopardy/tests/test_parse.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jeopardy/parse.py jeopardy/tests/test_parse.py
git commit -m "feat(jeopardy): parse game metadata"
```

---

## Task 3: Parse Jeopardy / Double Jeopardy board clues

**Files:**
- Modify: `jeopardy/parse.py` (implement `_parse_board_clues`)
- Test: `jeopardy/tests/test_parse.py`

**Interfaces:**
- Produces: each board clue dict has keys `round` (`"J"` or `"DJ"`), `row` (int 1–5), `col` (int 1–6), `category` (str), `value` (int|None — None for DD), `is_daily_double` (bool), `dd_wager` (int|None), `clue` (str), `answer` (str|None), `order_number` (int|None).

- [ ] **Step 1: Write the failing tests**

Append to `jeopardy/tests/test_parse.py`:
```python
def _clue_at(game, round_, col, row):
    for c in game["clues"]:
        if c["round"] == round_ and c["col"] == col and c["row"] == row:
            return c
    raise AssertionError(f"no clue at {round_} col={col} row={row}")


def test_board_clue_counts():
    game = parse_game(_modern())
    board = [c for c in game["clues"] if c["round"] in ("J", "DJ")]
    assert len(board) == 60  # 30 per round, fully revealed game
    assert sum(c["is_daily_double"] for c in board) == 3


def test_first_jeopardy_clue():
    c = _clue_at(parse_game(_modern()), "J", 1, 1)
    assert c["category"] == "CLASSIC AUTOMOBILES"
    assert c["value"] == 200
    assert c["is_daily_double"] is False
    assert c["dd_wager"] is None
    assert c["clue"].startswith("In 1913 this model from Ford")
    assert c["answer"] == "the Model T"
    assert c["order_number"] == 17


def test_category_entities_unescaped():
    game = parse_game(_modern())
    cats = {c["category"] for c in game["clues"] if c["round"] == "J"}
    assert "WORDS & PHRASES" in cats  # was "WORDS &amp; PHRASES"


def test_daily_double_has_wager_not_value():
    game = parse_game(_modern())
    dds = [c for c in game["clues"] if c["is_daily_double"]]
    assert dds  # at least one
    for c in dds:
        assert c["value"] is None
        assert isinstance(c["dd_wager"], int) and c["dd_wager"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --group scraper pytest jeopardy/tests/test_parse.py -v`
Expected: FAIL (board list empty → count/`_clue_at` assertions fail).

- [ ] **Step 3: Implement `_parse_board_clues`**

Replace the stub in `jeopardy/parse.py`:
```python
import html as _html

_CID_RE = re.compile(r"clue_(J|DJ)_(\d+)_(\d+)$")
_ROUND_DIVS = [("J", "jeopardy_round"), ("DJ", "double_jeopardy_round")]


def _parse_board_clues(soup):
    clues = []
    for round_, div_id in _ROUND_DIVS:
        round_div = soup.find("div", id=div_id)
        if round_div is None:
            continue
        categories = [
            _html.unescape(td.get_text(" ", strip=True))
            for td in round_div.find_all("td", class_="category_name")
        ]
        for cell in round_div.find_all("td", class_="clue"):
            ctd = cell.find("td", class_="clue_text", id=_CID_RE)
            if ctd is None:
                continue  # unrevealed / empty cell
            clue_text = ctd.get_text(" ", strip=True)
            if not clue_text:
                continue
            m = _CID_RE.search(ctd["id"])
            col, row = int(m.group(2)), int(m.group(3))

            rtd = cell.find("td", id=ctd["id"] + "_r")
            answer = None
            if rtd is not None:
                em = rtd.find("em", class_="correct_response")
                if em is not None:
                    answer = em.get_text(" ", strip=True)

            value, is_dd, dd_wager = _parse_value_cell(cell)
            order_number = _parse_order(cell)
            category = categories[col - 1] if col - 1 < len(categories) else None

            clues.append({
                "round": round_, "row": row, "col": col, "category": category,
                "value": value, "is_daily_double": is_dd, "dd_wager": dd_wager,
                "clue": clue_text, "answer": answer, "order_number": order_number,
            })
    return clues


def _parse_value_cell(cell):
    """Return (value:int|None, is_daily_double:bool, dd_wager:int|None)."""
    val_td = cell.find("td", class_="clue_value")
    if val_td is not None:
        digits = re.sub(r"[^\d]", "", val_td.get_text())
        return (int(digits) if digits else None), False, None
    dd_td = cell.find("td", class_="clue_value_daily_double")
    if dd_td is not None:
        digits = re.sub(r"[^\d]", "", dd_td.get_text())
        return None, True, (int(digits) if digits else None)
    return None, False, None


def _parse_order(cell):
    order_td = cell.find("td", class_="clue_order_number")
    if order_td is None:
        return None
    text = order_td.get_text(strip=True)
    return int(text) if text.isdigit() else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --group scraper pytest jeopardy/tests/test_parse.py -v`
Expected: PASS (all parse tests).

- [ ] **Step 5: Commit**

```bash
git add jeopardy/parse.py jeopardy/tests/test_parse.py
git commit -m "feat(jeopardy): parse J/DJ board clues with position, value, daily doubles"
```

---

## Task 4: Parse Final Jeopardy clue

**Files:**
- Modify: `jeopardy/parse.py` (implement `_parse_final_clue`)
- Test: `jeopardy/tests/test_parse.py`

**Interfaces:**
- Produces: the Final clue dict has `round="Final"`, `row=None`, `col=None`, `value=None`, `is_daily_double=False`, `dd_wager=None`, plus `category`, `clue`, `answer`, `order_number=None`.

- [ ] **Step 1: Write the failing test**

Append to `jeopardy/tests/test_parse.py`:
```python
def test_final_jeopardy_clue():
    game = parse_game(_modern())
    finals = [c for c in game["clues"] if c["round"] == "Final"]
    assert len(finals) == 1
    fj = finals[0]
    assert fj["category"] == "AUTHORS"
    assert fj["row"] is None and fj["col"] is None and fj["value"] is None
    assert fj["clue"]  # non-empty
    assert fj["answer"]  # non-empty
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run --group scraper pytest jeopardy/tests/test_parse.py::test_final_jeopardy_clue -v`
Expected: FAIL (`len(finals) == 0`).

- [ ] **Step 3: Implement `_parse_final_clue`**

Replace the stub in `jeopardy/parse.py`:
```python
def _parse_final_clue(soup):
    fj_div = soup.find("div", id="final_jeopardy_round")
    if fj_div is None:
        return []
    cat_td = fj_div.find("td", class_="category_name")
    category = _html.unescape(cat_td.get_text(" ", strip=True)) if cat_td else None

    clue_td = fj_div.find("td", id="clue_FJ")
    clue_text = clue_td.get_text(" ", strip=True) if clue_td else None
    if not clue_text:
        return []

    rtd = fj_div.find("td", id="clue_FJ_r")
    answer = None
    if rtd is not None:
        em = rtd.find("em", class_="correct_response")
        if em is not None:
            answer = em.get_text(" ", strip=True)

    return [{
        "round": "Final", "row": None, "col": None, "category": category,
        "value": None, "is_daily_double": False, "dd_wager": None,
        "clue": clue_text, "answer": answer, "order_number": None,
    }]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --group scraper pytest jeopardy/tests/test_parse.py -v`
Expected: PASS (all parse tests).

- [ ] **Step 5: Commit**

```bash
git add jeopardy/parse.py jeopardy/tests/test_parse.py
git commit -m "feat(jeopardy): parse Final Jeopardy clue"
```

---

## Task 5: Fetch with on-disk HTML cache

**Files:**
- Create: `jeopardy/fetch.py`
- Test: `jeopardy/tests/test_fetch.py`

**Interfaces:**
- Consumes: `jeopardy.config` (`HTML_CACHE`, `USER_AGENT`, `MIN_DELAY`, `MAX_DELAY`).
- Produces: `fetch(url: str, cache_key: str) -> str`. Returns cached text if `HTML_CACHE/<cache_key>.html` exists (no network, no sleep). Otherwise performs a GET, sleeps a polite delay, writes the cache file, and returns the text.

- [ ] **Step 1: Write the failing test**

Create `jeopardy/tests/test_fetch.py`:
```python
from jeopardy import fetch as fetch_mod
from jeopardy.fetch import fetch


def test_cache_hit_avoids_network(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_mod.config, "HTML_CACHE", tmp_path)
    (tmp_path / "abc.html").write_text("<html>cached</html>")

    def boom(*a, **k):
        raise AssertionError("network was hit on a cache hit")

    monkeypatch.setattr(fetch_mod.httpx, "get", boom)
    assert fetch("https://example.com/x", "abc") == "<html>cached</html>"


def test_cache_miss_fetches_and_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(fetch_mod.config, "HTML_CACHE", tmp_path)
    monkeypatch.setattr(fetch_mod.time, "sleep", lambda *_: None)

    class FakeResp:
        text = "<html>live</html>"
        def raise_for_status(self): pass

    calls = {}
    def fake_get(url, headers, timeout):
        calls["url"] = url
        calls["ua"] = headers["User-Agent"]
        return FakeResp()

    monkeypatch.setattr(fetch_mod.httpx, "get", fake_get)
    out = fetch("https://example.com/y", "def")
    assert out == "<html>live</html>"
    assert (tmp_path / "def.html").read_text() == "<html>live</html>"
    assert calls["url"] == "https://example.com/y"
    assert "jeopardy-ds-research" in calls["ua"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --group scraper pytest jeopardy/tests/test_fetch.py -v`
Expected: FAIL (`ModuleNotFoundError: jeopardy.fetch`).

- [ ] **Step 3: Implement `jeopardy/fetch.py`**

```python
"""Polite, cached HTTP fetching. Network cost is paid once per URL."""
import random
import time

import httpx

from jeopardy import config


def fetch(url, cache_key):
    """Return page text for `url`, using an on-disk cache keyed by `cache_key`."""
    config.HTML_CACHE.mkdir(parents=True, exist_ok=True)
    cache_file = config.HTML_CACHE / f"{cache_key}.html"
    if cache_file.exists():
        return cache_file.read_text()

    resp = httpx.get(
        url,
        headers={"User-Agent": config.USER_AGENT},
        timeout=30.0,
    )
    resp.raise_for_status()
    text = resp.text
    cache_file.write_text(text)
    time.sleep(config.MIN_DELAY + random.uniform(0, config.MAX_DELAY - config.MIN_DELAY))
    return text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --group scraper pytest jeopardy/tests/test_fetch.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jeopardy/fetch.py jeopardy/tests/test_fetch.py
git commit -m "feat(jeopardy): cached polite HTTP fetch"
```

---

## Task 6: Crawl — enumeration + resumable orchestration

**Files:**
- Create: `jeopardy/crawl.py`
- Test: `jeopardy/tests/test_crawl.py`

**Interfaces:**
- Consumes: `fetch(url, cache_key)`; `parse_game(html)`; `jeopardy.config` (`BASE_URL`, `JSONL_PATH`).
- Produces:
  - `parse_season_ids(listseasons_html: str) -> list[str]` — season ids in page order, deduped (e.g. `["42","41","cwcpi",...]`).
  - `parse_game_ids(season_html: str) -> list[int]` — unique game ids on a season page.
  - `existing_game_ids(jsonl_path) -> set[int]` — ids already in the JSONL.
  - `run_crawl()` — full orchestration writing `config.JSONL_PATH`.

- [ ] **Step 1: Write the failing tests**

Create `jeopardy/tests/test_crawl.py`:
```python
import json
from pathlib import Path
from jeopardy.crawl import parse_season_ids, parse_game_ids, existing_game_ids

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_season_ids():
    ids = parse_season_ids((FIXTURES / "listseasons.html").read_text())
    assert "36" in ids
    assert "goattournament" in ids
    assert len(ids) == len(set(ids))  # deduped
    assert len(ids) >= 45


def test_parse_game_ids():
    ids = parse_game_ids((FIXTURES / "season36.html").read_text())
    assert 6699 in ids
    assert all(isinstance(i, int) for i in ids)
    assert len(ids) == len(set(ids))


def test_existing_game_ids(tmp_path):
    p = tmp_path / "games.jsonl"
    p.write_text(json.dumps({"game_id": 1}) + "\n" + json.dumps({"game_id": 2}) + "\n")
    assert existing_game_ids(p) == {1, 2}


def test_existing_game_ids_missing_file(tmp_path):
    assert existing_game_ids(tmp_path / "nope.jsonl") == set()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --group scraper pytest jeopardy/tests/test_crawl.py -v`
Expected: FAIL (`ModuleNotFoundError: jeopardy.crawl`).

- [ ] **Step 3: Implement `jeopardy/crawl.py`**

```python
"""Resumable orchestration: seasons -> games -> games.jsonl."""
import json
import re

from jeopardy import config
from jeopardy.fetch import fetch
from jeopardy.parse import parse_game

_SEASON_RE = re.compile(r"showseason\.php\?season=([0-9a-z]+)")
_GAME_RE = re.compile(r"showgame\.php\?game_id=(\d+)")


def parse_season_ids(listseasons_html):
    seen, out = set(), []
    for m in _SEASON_RE.finditer(listseasons_html):
        sid = m.group(1)
        if sid not in seen:
            seen.add(sid)
            out.append(sid)
    return out


def parse_game_ids(season_html):
    seen, out = set(), []
    for m in _GAME_RE.finditer(season_html):
        gid = int(m.group(1))
        if gid not in seen:
            seen.add(gid)
            out.append(gid)
    return out


def existing_game_ids(jsonl_path):
    if not jsonl_path.exists():
        return set()
    ids = set()
    with jsonl_path.open() as f:
        for line in f:
            line = line.strip()
            if line:
                ids.add(json.loads(line)["game_id"])
    return ids


def run_crawl():
    config.JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
    done = existing_game_ids(config.JSONL_PATH)
    print(f"Resuming: {len(done)} games already scraped.")

    seasons_html = fetch(f"{config.BASE_URL}/listseasons.php", "listseasons")
    season_ids = parse_season_ids(seasons_html)
    print(f"Found {len(season_ids)} seasons.")

    with config.JSONL_PATH.open("a") as out:
        for sid in season_ids:
            season_html = fetch(
                f"{config.BASE_URL}/showseason.php?season={sid}", f"season_{sid}"
            )
            game_ids = parse_game_ids(season_html)
            print(f"Season {sid}: {len(game_ids)} games.")
            for gid in game_ids:
                if gid in done:
                    continue
                html = fetch(
                    f"{config.BASE_URL}/showgame.php?game_id={gid}", f"game_{gid}"
                )
                record = parse_game(html)
                if record is None:
                    done.add(gid)
                    continue
                record["game_id"] = gid
                record["season"] = sid
                out.write(json.dumps(record, ensure_ascii=False) + "\n")
                out.flush()
                done.add(gid)
    print(f"Done. {len(done)} games total.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --group scraper pytest jeopardy/tests/test_crawl.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jeopardy/crawl.py jeopardy/tests/test_crawl.py
git commit -m "feat(jeopardy): resumable crawl orchestration"
```

---

## Task 7: Build Parquet — curation + derivation

**Files:**
- Create: `jeopardy/build_parquet.py`
- Test: `jeopardy/tests/test_build.py`

**Interfaces:**
- Consumes: `jeopardy.config` (`JSONL_PATH`, `PARQUET_PATH`, `VALUE_DOUBLING_DATE`); the per-game JSONL contract.
- Produces:
  - `board_value(round_: str, row: int|None, air_date: str|None) -> int|None` — ladder-derived board value.
  - `classify_game_type(season: str, comments: str) -> str`.
  - `game_rows(record: dict) -> list[dict]` — explode one game into Parquet-schema row dicts.
  - `run_build()` — read JSONL, write `config.PARQUET_PATH` (zstd).

- [ ] **Step 1: Write the failing tests**

Create `jeopardy/tests/test_build.py`:
```python
from jeopardy.build_parquet import board_value, classify_game_type, game_rows


def test_board_value_modern():
    assert board_value("J", 1, "2020-06-12") == 200
    assert board_value("J", 5, "2020-06-12") == 1000
    assert board_value("DJ", 1, "2020-06-12") == 400
    assert board_value("DJ", 5, "2020-06-12") == 2000


def test_board_value_pre_2001_halved():
    assert board_value("J", 5, "2000-01-01") == 500
    assert board_value("DJ", 5, "2000-01-01") == 1000


def test_board_value_final_is_none():
    assert board_value("Final", None, "2020-06-12") is None


def test_classify_named_season():
    assert classify_game_type("goattournament", "") == "goat"
    assert classify_game_type("jm", "") == "jeopardy_masters"


def test_classify_from_comments():
    assert classify_game_type("35", "Tournament of Champions final game 2.") == "toc"
    assert classify_game_type("30", "Teen Tournament quarterfinal.") == "teen"
    assert classify_game_type("36", "Zach Newkirk game 4.") == "regular"


def test_game_rows_shape_and_derivation():
    record = {
        "game_id": 6699, "season": "36", "show_number": 8235,
        "air_date": "2020-06-12", "game_comments": "Zach Newkirk game 4.",
        "clues": [
            {"round": "J", "row": 3, "col": 2, "category": "X", "value": 600,
             "is_daily_double": False, "dd_wager": None, "clue": "c", "answer": "a",
             "order_number": 5},
            {"round": "DJ", "row": 1, "col": 1, "category": "Y", "value": None,
             "is_daily_double": True, "dd_wager": 1600, "clue": "d", "answer": "b",
             "order_number": 9},
        ],
    }
    rows = game_rows(record)
    assert len(rows) == 2
    r0, r1 = rows
    assert r0["round"] == "Jeopardy" and r0["column"] == 2 and r0["clue_value"] == 600
    assert r0["game_type"] == "regular" and r0["season"] == "36"
    # DD: clue_value is the derived board value, wager preserved separately
    assert r1["round"] == "Double Jeopardy"
    assert r1["clue_value"] == 400 and r1["dd_wager"] == 1600
    assert set(r0.keys()) == {
        "game_id", "air_date", "season", "game_type", "round", "category",
        "clue_value", "row", "column", "is_daily_double", "dd_wager", "clue", "answer",
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --group scraper pytest jeopardy/tests/test_build.py -v`
Expected: FAIL (`ModuleNotFoundError: jeopardy.build_parquet`).

- [ ] **Step 3: Implement `jeopardy/build_parquet.py`**

```python
"""Curate data/games.jsonl into the committed clues.parquet."""
import json

import pandas as pd

from jeopardy import config

_ROUND_FULL = {"J": "Jeopardy", "DJ": "Double Jeopardy", "Final": "Final"}

_NAMED_SEASONS = {
    "cwcpi": "audio_only",
    "jm": "jeopardy_masters",
    "pcj": "primetime_celebrity",
    "ncc": "national_college_championship",
    "goattournament": "goat",
    "bbab": "battle_bay_area_brains",
    "superjeopardy": "super_jeopardy",
    "trebekpilots": "trebek_pilots",
}

# Ordered: first matching keyword (lowercased comments) wins.
_COMMENT_RULES = [
    ("tournament of champions", "toc"),
    ("teen tournament", "teen"),
    ("teachers tournament", "teachers"),
    ("college champ", "college"),
    ("college tournament", "college"),
    ("celebrity", "celebrity"),
    ("kids week", "kids"),
    ("all-star games", "all_star"),
    ("power players", "celebrity"),
]


def board_value(round_, row, air_date):
    """Standard board dollar value for a cell (None for Final / rowless)."""
    if round_ == "Final" or row is None:
        return None
    doubled = air_date is not None and air_date >= config.VALUE_DOUBLING_DATE
    base = (200 if doubled else 100) if round_ == "J" else (400 if doubled else 200)
    return base * row


def classify_game_type(season, comments):
    if season in _NAMED_SEASONS:
        return _NAMED_SEASONS[season]
    text = (comments or "").lower()
    for keyword, label in _COMMENT_RULES:
        if keyword in text:
            return label
    return "regular"


def game_rows(record):
    game_type = classify_game_type(record["season"], record.get("game_comments", ""))
    rows = []
    for c in record["clues"]:
        value = c["value"]
        if value is None and not (c["round"] == "Final" or c["row"] is None):
            value = board_value(c["round"], c["row"], record["air_date"])
        rows.append({
            "game_id": record["game_id"],
            "air_date": record["air_date"],
            "season": record["season"],
            "game_type": game_type,
            "round": _ROUND_FULL.get(c["round"], c["round"]),
            "category": c["category"],
            "clue_value": value,
            "row": c["row"],
            "column": c["col"],
            "is_daily_double": c["is_daily_double"],
            "dd_wager": c["dd_wager"],
            "clue": c["clue"],
            "answer": c["answer"],
        })
    return rows


def run_build():
    rows = []
    with config.JSONL_PATH.open() as f:
        for line in f:
            line = line.strip()
            if line:
                rows.extend(game_rows(json.loads(line)))
    df = pd.DataFrame(rows)
    df["air_date"] = pd.to_datetime(df["air_date"])
    config.PARQUET_PATH.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(config.PARQUET_PATH, compression="zstd", index=False)
    print(f"Wrote {len(df):,} clues to {config.PARQUET_PATH}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --group scraper pytest jeopardy/tests/test_build.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jeopardy/build_parquet.py jeopardy/tests/test_build.py
git commit -m "feat(jeopardy): build curated clues.parquet from JSONL"
```

---

## Task 8: End-to-end validation on a small slice

**Files:**
- Test: `jeopardy/tests/test_build.py` (add an integration test using the fixture)

**Interfaces:**
- Consumes: everything above. No new production code — this task proves the pipeline composes.

- [ ] **Step 1: Write an integration test (parse → game_rows) from the fixture**

Append to `jeopardy/tests/test_build.py`:
```python
from pathlib import Path
from jeopardy.parse import parse_game

FIXTURES = Path(__file__).parent / "fixtures"


def test_fixture_game_produces_valid_rows():
    record = parse_game((FIXTURES / "game_modern.html").read_text())
    record["game_id"] = 6699
    record["season"] = "36"
    rows = game_rows(record)
    assert len(rows) == 61  # 60 board + 1 final
    finals = [r for r in rows if r["round"] == "Final"]
    assert len(finals) == 1 and finals[0]["clue_value"] is None
    # every board row has a positive derived value and a category
    for r in rows:
        if r["round"] != "Final":
            assert r["clue_value"] and r["clue_value"] > 0
            assert r["category"]
```

- [ ] **Step 2: Run the full test suite**

Run: `uv run --group scraper pytest jeopardy/tests -v`
Expected: PASS (all tests across parse/fetch/crawl/build/cli).

- [ ] **Step 3: Real smoke crawl of one season, then build**

Run a genuine (network) crawl limited to one small named season to validate live behavior end-to-end without a full 3-hour run. Use the Python REPL:
```bash
uv run python -c "
from jeopardy import crawl, config
from jeopardy.fetch import fetch
import json
# crawl just the GOAT tournament season into the real JSONL
html = fetch(f'{config.BASE_URL}/showseason.php?season=goattournament', 'season_goattournament')
gids = crawl.parse_game_ids(html)
config.JSONL_PATH.parent.mkdir(parents=True, exist_ok=True)
done = crawl.existing_game_ids(config.JSONL_PATH)
from jeopardy.parse import parse_game
with config.JSONL_PATH.open('a') as out:
    for gid in gids:
        if gid in done: continue
        rec = parse_game(fetch(f'{config.BASE_URL}/showgame.php?game_id={gid}', f'game_{gid}'))
        if rec is None: continue
        rec['game_id'] = gid; rec['season'] = 'goattournament'
        out.write(json.dumps(rec, ensure_ascii=False) + '\n')
print('slice crawled')
"
uv run --group scraper python -m jeopardy build
```
Expected: a `clues.parquet` is written; the printed clue count is a few hundred.

- [ ] **Step 4: Inspect the Parquet**

Run:
```bash
uv run python -c "
import pandas as pd
df = pd.read_parquet('posts/jeopardy_ds/clues.parquet')
print(df.shape)
print(df['game_type'].value_counts())
print(df[['air_date','round','category','clue_value','row','column','is_daily_double','answer']].head())
print('null categories:', df['category'].isna().sum())
"
```
Expected: rows present, `game_type` is `goat`, columns populated, few/no null categories.

- [ ] **Step 5: Commit the validation test (NOT the slice Parquet)**

The slice Parquet and JSONL are not the real dataset — remove them so they aren't committed prematurely, then commit only the test.
```bash
rm -f posts/jeopardy_ds/clues.parquet
rm -rf jeopardy/data
git add jeopardy/tests/test_build.py
git commit -m "test(jeopardy): end-to-end fixture validation"
```

- [ ] **Step 6: Full crawl (manual, run by Nick when ready)**

This is the real ~2.5–4 hour polite crawl. Not part of the automated plan; run it deliberately:
```bash
uv run --group scraper python -m jeopardy all
```
Then commit the real artifact:
```bash
git add posts/jeopardy_ds/clues.parquet
git commit -m "data(jeopardy): committed clues.parquet from full j-archive crawl"
```

---

## Self-Review

**Spec coverage:**
- Two-layer storage (JSONL raw + committed Parquet) → Tasks 6, 7; gitignore in Task 1. ✓
- fetch/parse/crawl/build separation → Tasks 5, 2–4, 6, 7. ✓
- Polite cached fetching (UA, ~1 req/s, cache) → Task 5. ✓
- Resumability via JSONL checkpoint → Task 6 (`existing_game_ids`). ✓
- Scrape everything + `game_type` tagging → Task 7 (`classify_game_type`, named seasons + comment rules). ✓
- Full schema incl. row/column (DD heatmaps), era-stable value handling, DD wager → Tasks 3, 7. ✓
- click CLI `crawl/build/all` → Tasks 1, 5–7. ✓
- uv-managed deps, scraper group vs main `pyarrow` → Task 1. ✓
- Parser fixture tests (modern game; edge cases) → Tasks 2–4, 8. ✓
- Out of scope: contestant data — not implemented. ✓

**Known limitations (acceptable for A):**
- `game_type` comment classification is heuristic; unmatched tournament games fall back to `regular`. Auditable later from the `game_comments` retained in JSONL.
- Rare tiebreaker clues are not separately captured (folded out; `Final`/board handling only).
- Exact-value parser assertions are anchored on the modern fixture (game 6699). Pre-2001 / tournament games rely on the same DOM structure; the live smoke crawl (Task 8) exercises a tournament season for real.

**Placeholder scan:** none — every step has complete code/commands.

**Type consistency:** `parse_game` keys (`round/row/col/value/is_daily_double/dd_wager/clue/answer/order_number/category`) are consumed unchanged by `game_rows`; `col` → `column` and `round` short code → full name are the only intentional renames, both in `game_rows`. `fetch(url, cache_key)` signature is consistent across `crawl` call sites. ✓
