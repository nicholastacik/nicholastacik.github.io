# TV Tracker Plan 2: Sheet I/O, Daily Job and Workflow

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Run the real daily job against the Google Sheet: fact cards from TMDB, the weekly schedule from TVmaze (falling back to TMDB), LLM suggestion and news cards, and a `Meta` tab. Seed `Tracked` from `shows.json`, then run it on a GitHub Actions cron.

**Architecture:** `sheet.py` is the only code that talks to Google. It reads whole tabs as header-keyed dicts, and writes **by key**: it re-reads column A right before writing, so rows are located fresh. Everything else is pure: `state.py` (collapsing Tracked rows), `cards.py` (episode facts, new cards, links), `reconcile.py` (content updates, season `current` flags), `schedule.py` (week rows, carry-forward), `llm_cards.py` (LLM results to cards, Sheet state to LLM inputs). `daily.py` orchestrates one run and returns a report; `__main__.py` gains `run` (default) and `setup` commands.

**Tech Stack:** Python ≥3.12, uv group `tv-tracker` (+ `gspread`), httpx, openai, pytest with an in-memory `FakeSpreadsheet`.

**Spec:** `docs/superpowers/specs/2026-09-27-tv-tracker-design.md` (rev 4). Build order step 2. Plan 1's code and `posts/tv_tracker/notes/BUILD_NOTES.md` ("For Plan 2") are inputs.

## Global Constraints

- Worktree `/Users/nick/Work/nicholastacik.github.io-tv-tracker`, branch `tv-tracker`. Tests: `uv run --group tv-tracker python -m pytest tv-tracker/tests -q` from the repo root. No network in tests.
- Tabs and columns exactly as the spec (rev 4):
  - `Tracked`: `tmdb_id | tvmaze_id | name | first_air_year | poster_url | added_at | source | active | updated_at`
  - `Cards`: `card_id | type | tmdb_id | show_name | headline | body | date | link | image_url | source_url | created_at | current | status | updated_at`
  - `Schedule`: `tmdb_id | airstamp | show_name | episode_label | network | image_url | refreshed_at`
  - `Meta`: `key | value` with `last_run_at`, `last_run_ok`, `schedule_week`, `failed_shows`, `failed_steps`
- **Rows are never deleted or reordered.** Writes locate rows by the key in column A, re-read immediately before writing.
- **Column ownership:** the job writes `status` only when appending (`new`). After that it writes only content columns (`show_name`, `headline`, `date`, `image_url`) on episode rows, `current` on season rows, and `tvmaze_id` on Tracked. Never `status`, never `updated_at` on existing rows.
- `card_id`s: `ep:{tmdb}:S{ss}E{ee}`, `season:{tmdb}:{n}:{air_date}`, `sugg:{tmdb}`, `news:{tmdb}:{sha1(normalize_url(url))[:8]}`.
- Episode cards: `added_at ≤ air_date ≤ today` (plain Toronto dates). Seasons are fetched from the latest one premiered on or before `added_at`.
- Season cards: reconcile every season that hasn't premiered or already has cards; append only for dates `≥ today`; `current = TRUE` only for the card matching TMDB's current date.
- Schedule: this Mon–Sun in America/Toronto. `airstamp` is ISO with offset, or date-only when TVmaze has no airtime. **TMDB `next_episode_to_air` fallback** (date only) when TVmaze gives no rows for the show. Failed shows carry their previous in-week rows forward.
- Job exits non-zero if any show or step failed, **after** writing everything that succeeded.
- Workflow: cron `0 10 * * *` + `workflow_dispatch`, `concurrency: {group: tv-tracker-sheet, cancel-in-progress: false}`. Secrets `TMDB_TOKEN`, `OPENAI_API_KEY`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `SHEET_ID`.
- Secrets never in the repo. The local service-account key lives outside the repo (`~/.config/tv-tracker/service-account.json`), referenced by `GOOGLE_SERVICE_ACCOUNT_FILE` in the gitignored `.env`.
- The Sheet is shared Restricted: Nick, his wife, the service account.

## Review Focus

1. **Hand-edited Tracked rows with a blank or garbage `tmdb_id`/`added_at`:** skip the row; don't crash the run. → test in Task 2.
2. **TVmaze specials with `number: null`:** label as `S03 special`; don't crash. → test in Task 5.
3. **A show tracked before it has ever aired:** no episode cards, a season card for the announced date. → test in Task 3.
4. **The same card produced twice in one run** (e.g. two news items for one URL and show): append once. → test in Task 7.
5. **First run on a freshly set-up, empty Sheet:** works, skips the LLM, and writes `Meta`. → test in Task 7.

---

## File Structure

```
tv-tracker/job/
  config.py        # + SHEET_ID, service account loading
  sheet.py         # HEADERS, Update, Sheet (read_all / write / replace / ensure_tabs)
  state.py         # truthy, Show, active_shows, all_tracked_ids
  cards.py         # parse_date, new_card, seasons_to_fetch, episode_facts, episode_link
  reconcile.py     # content_updates, reconcile_seasons
  schedule.py      # week_start, in_week, schedule_rows, merge_schedule
  llm_cards.py     # suggestion_card, news_card_id, news_card, llm_inputs
  steps.py         # run_suggestions, run_news (moved from __main__)
  setup.py         # import_rows
  daily.py         # RunReport, run_daily, meta_rows
  tmdb.py          # + episode_imdb
  tvmaze.py        # + show_with_episodes
  __main__.py      # run (default) | setup ; --dry-run kept
tv-tracker/tests/
  fakes.py         # FakeSpreadsheet, make_spreadsheet, get_cell, set_cell, FakeTmdb, FakeTvmaze, FakeLlm
  test_sheet.py  test_state.py  test_cards.py  test_reconcile.py
  test_schedule.py  test_llm_cards.py  test_setup.py  test_daily.py
.github/workflows/tv-tracker.yml
```

---

### Task 1: Sheet I/O and the in-memory fake

**Files:**
- Modify: `pyproject.toml`, `uv.lock` (via `uv add`)
- Modify: `tv-tracker/job/config.py`
- Create: `tv-tracker/job/sheet.py`, `tv-tracker/tests/fakes.py`
- Test: `tv-tracker/tests/test_sheet.py`

**Interfaces:**
- Produces: `HEADERS: dict[str, list[str]]`; `column_letter(index: int) -> str` (0-based); `@dataclass Update(tab: str, key: str | int, fields: dict)`; `parse_rows(tab, values) -> list[dict]` (string values plus `_row`, blank rows skipped); `class Sheet(spreadsheet)` with `open(info: dict, sheet_id: str)`, `read_all() -> dict[str, list[dict]]`, `write(updates: list[Update], appends: dict[str, list[dict]]) -> None`, `replace(tab: str, rows: list[dict]) -> None`, `ensure_tabs() -> list[str]`. `config.sheet_id()`, `config.service_account_info()`.
- Test utilities: `FakeSpreadsheet`, `make_spreadsheet(**rows_by_tab)`, `get_cell(sp, tab, key, column)`, `set_cell(sp, tab, key, column, value)`.

- [ ] **Step 1: Dependency and config**

```bash
cd /Users/nick/Work/nicholastacik.github.io-tv-tracker && uv add --group tv-tracker gspread
```

Append to `tv-tracker/job/config.py` (and add `import json` and `from pathlib import Path` to its imports):
```python
def sheet_id() -> str:
    return os.environ["SHEET_ID"]


def service_account_info() -> dict:
    if raw := os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON"):
        return json.loads(raw)
    return json.loads(Path(os.environ["GOOGLE_SERVICE_ACCOUNT_FILE"]).expanduser().read_text())
```

- [ ] **Step 2: Write the fake**

`tv-tracker/tests/fakes.py`:
```python
import json
import re
from types import SimpleNamespace as NS

from job.sheet import HEADERS

RANGE = re.compile(r"^(?P<tab>\w+)!(?P<c1>[A-Z]+)(?P<r1>\d*)(?::(?P<c2>[A-Z]+)(?P<r2>\d*))?$")


def col_index(letters: str) -> int:
    n = 0
    for ch in letters:
        n = n * 26 + ord(ch) - 64
    return n - 1


def fmt(value) -> str:
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    return "" if value is None else str(value)


def _trim(row: list[str]) -> list[str]:
    row = list(row)
    while row and row[-1] == "":
        row.pop()
    return row


class FakeSpreadsheet:
    def __init__(self, tabs: dict[str, list[list]] | None = None):
        self.grid = {tab: [[fmt(v) for v in row] for row in rows] for tab, rows in (tabs or {}).items()}
        self.batch_updates: list[dict] = []

    def worksheets(self):
        return [NS(title=tab) for tab in self.grid]

    def add_worksheet(self, title, rows, cols):
        self.grid[title] = []

    def _parse(self, a1: str):
        m = RANGE.match(a1)
        c1 = col_index(m["c1"])
        c2 = col_index(m["c2"]) if m["c2"] else c1
        return m["tab"], int(m["r1"]) if m["r1"] else 1, c1, c2

    def _row(self, tab: str, number: int) -> list[str]:
        grid = self.grid[tab]
        while len(grid) < number:
            grid.append([])
        return grid[number - 1]

    def values_batch_get(self, ranges, params=None):
        out = []
        for a1 in ranges:
            tab, r1, c1, c2 = self._parse(a1)
            rows = [_trim(row[c1 : c2 + 1]) for row in self.grid[tab][r1 - 1 :]]
            while rows and not rows[-1]:
                rows.pop()
            out.append({"range": a1, "values": rows} if rows else {"range": a1})
        return {"valueRanges": out}

    def values_batch_update(self, body):
        self.batch_updates.append(body)
        for item in body["data"]:
            tab, r1, c1, _ = self._parse(item["range"])
            for i, values in enumerate(item["values"]):
                row = self._row(tab, r1 + i)
                for j, value in enumerate(values):
                    while len(row) <= c1 + j:
                        row.append("")
                    row[c1 + j] = fmt(value)

    def values_clear(self, a1):
        tab, r1, c1, c2 = self._parse(a1)
        for row in self.grid[tab][r1 - 1 :]:
            for c in range(c1, min(c2 + 1, len(row))):
                row[c] = ""


def make_spreadsheet(**rows_by_tab) -> FakeSpreadsheet:
    tabs = {tab: [list(header)] for tab, header in HEADERS.items()}
    for tab, rows in rows_by_tab.items():
        tabs[tab] += [[row.get(c, "") for c in HEADERS[tab]] for row in rows]
    return FakeSpreadsheet(tabs)


def _find(sp: FakeSpreadsheet, tab: str, key) -> list[str]:
    return next(row for row in sp.grid[tab][1:] if row and row[0] == str(key))


def get_cell(sp: FakeSpreadsheet, tab: str, key, column: str) -> str:
    row = _find(sp, tab, key)
    index = HEADERS[tab].index(column)
    return row[index] if index < len(row) else ""


def set_cell(sp: FakeSpreadsheet, tab: str, key, column: str, value) -> None:
    row = _find(sp, tab, key)
    index = HEADERS[tab].index(column)
    while len(row) <= index:
        row.append("")
    row[index] = fmt(value)


class FakeTmdb:
    def __init__(self, shows: dict[int, dict], seasons: dict[tuple[int, int], dict] | None = None, broken=()):
        self.shows, self.seasons, self.broken = shows, seasons or {}, set(broken)
        self.calls = []

    def show(self, tmdb_id, seasons=()):
        self.calls.append((tmdb_id, tuple(seasons)))
        if tmdb_id in self.broken:
            raise RuntimeError("tmdb down")
        data = json.loads(json.dumps(self.shows[tmdb_id]))
        for n in seasons:
            data[f"season/{n}"] = self.seasons.get((tmdb_id, n), {"episodes": []})
        return data

    def episode_imdb(self, tmdb_id, season, episode):
        return None

    def search(self, title):
        return []


class FakeTvmaze:
    def __init__(self, lookups: dict[str, int], shows: dict[int, dict], broken=()):
        self.lookups, self.shows, self.broken = lookups, shows, set(broken)

    def lookup_imdb(self, imdb_id):
        return self.lookups.get(imdb_id)

    def show_with_episodes(self, tvmaze_id):
        if tvmaze_id in self.broken:
            raise RuntimeError("tvmaze down")
        return self.shows.get(tvmaze_id, {})


class FakeLlm:
    def __init__(self, payloads: dict[str, dict] | None = None, sources=(), fail=False):
        self.payloads = payloads or {}
        self.sources, self.fail, self.calls = list(sources), fail, []
        self.responses = NS(create=self._create)

    def _create(self, **kwargs):
        name = kwargs["text"]["format"]["name"]
        self.calls.append(name)
        if self.fail:
            raise RuntimeError("openai down")
        output = [NS(type="web_search_call", action=NS(type="search", sources=[NS(url=u) for u in self.sources]))]
        return NS(
            output=output,
            output_text=json.dumps(self.payloads.get(name, {name: []})),
            usage=NS(input_tokens=1, output_tokens=1),
        )
```

- [ ] **Step 3: Write the failing tests**

`tv-tracker/tests/test_sheet.py`:
```python
from fakes import FakeSpreadsheet, get_cell, make_spreadsheet

from job.sheet import HEADERS, Sheet, Update, column_letter

TRACKED = {"tmdb_id": 1, "tvmaze_id": "", "name": "One", "active": True, "added_at": "2026-09-20"}


def test_column_letter():
    assert [column_letter(i) for i in (0, 12, 25, 26, 27)] == ["A", "M", "Z", "AA", "AB"]


def test_read_all_returns_string_rows_with_row_numbers_and_skips_blanks():
    sp = make_spreadsheet(Tracked=[TRACKED])
    sp.grid["Tracked"].append([])
    sp.grid["Tracked"].append(["2", "", "Two"])
    tracked = Sheet(sp).read_all()["Tracked"]
    assert [(r["tmdb_id"], r["name"], r["active"], r["_row"]) for r in tracked] == [("1", "One", "TRUE", 2), ("2", "Two", "", 4)]
    assert tracked[1]["poster_url"] == ""


def test_write_updates_every_row_with_the_key_located_fresh():
    sp = make_spreadsheet(Tracked=[TRACKED, {**TRACKED, "tmdb_id": 2, "name": "Two"}, TRACKED])
    sheet = Sheet(sp)
    sheet.read_all()
    sp.grid["Tracked"].insert(1, ["9", "", "Hand inserted"])
    sheet.write([Update("Tracked", 1, {"tvmaze_id": 44})], {})
    assert [row[1] for row in sp.grid["Tracked"][1:]] == ["", "44", "", "44"]


def test_write_appends_after_last_row_in_one_batch():
    sp = make_spreadsheet(Cards=[{"card_id": "a", "status": "noted"}])
    Sheet(sp).write([Update("Cards", "a", {"headline": "H"})], {"Cards": [{"card_id": "b", "current": True, "status": "new"}]})
    assert len(sp.batch_updates) == 1
    assert sp.batch_updates[0]["valueInputOption"] == "RAW"
    assert get_cell(sp, "Cards", "a", "headline") == "H"
    assert get_cell(sp, "Cards", "a", "status") == "noted"
    assert get_cell(sp, "Cards", "b", "current") == "TRUE"
    assert sp.grid["Cards"][2][0] == "b"


def test_write_with_nothing_to_do_makes_no_calls():
    sp = make_spreadsheet()
    Sheet(sp).write([], {"Cards": []})
    assert sp.batch_updates == []


def test_replace_clears_rows_beyond_the_new_length():
    sp = make_spreadsheet(Schedule=[{"tmdb_id": 1, "airstamp": "a"}, {"tmdb_id": 2, "airstamp": "b"}])
    Sheet(sp).replace("Schedule", [{"tmdb_id": 3, "airstamp": "c"}])
    rows = Sheet(sp).read_all()["Schedule"]
    assert [(r["tmdb_id"], r["airstamp"]) for r in rows] == [("3", "c")]


def test_replace_with_no_rows_leaves_only_the_header():
    sp = make_spreadsheet(Schedule=[{"tmdb_id": 1, "airstamp": "a"}])
    Sheet(sp).replace("Schedule", [])
    assert Sheet(sp).read_all()["Schedule"] == []


def test_ensure_tabs_creates_missing_tabs_and_writes_headers():
    sp = FakeSpreadsheet({"Tracked": []})
    assert Sheet(sp).ensure_tabs() == ["Cards", "Schedule", "Meta"]
    assert all(sp.grid[tab][0] == header for tab, header in HEADERS.items())
```

- [ ] **Step 4: Run to verify failure**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_sheet.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'job.sheet'`

- [ ] **Step 5: Implement**

`tv-tracker/job/sheet.py`:
```python
import string
from dataclasses import dataclass

HEADERS = {
    "Tracked": ["tmdb_id", "tvmaze_id", "name", "first_air_year", "poster_url", "added_at", "source", "active", "updated_at"],
    "Cards": [
        "card_id", "type", "tmdb_id", "show_name", "headline", "body", "date", "link",
        "image_url", "source_url", "created_at", "current", "status", "updated_at",
    ],
    "Schedule": ["tmdb_id", "airstamp", "show_name", "episode_label", "network", "image_url", "refreshed_at"],
    "Meta": ["key", "value"],
}


@dataclass
class Update:
    tab: str
    key: str | int
    fields: dict


def column_letter(index: int) -> str:
    letters, index = "", index + 1
    while index:
        index, remainder = divmod(index - 1, 26)
        letters = string.ascii_uppercase[remainder] + letters
    return letters


def _last_column(tab: str) -> str:
    return column_letter(len(HEADERS[tab]) - 1)


def parse_rows(tab: str, values: list[list[str]]) -> list[dict]:
    header = HEADERS[tab]
    rows = []
    for number, raw in enumerate(values[1:], start=2):
        if not any(raw):
            continue
        row = dict(zip(header, raw + [""] * (len(header) - len(raw))))
        row["_row"] = number
        rows.append(row)
    return rows


def _values(tab: str, rows: list[dict]) -> list[list]:
    return [[row.get(column, "") for column in HEADERS[tab]] for row in rows]


class Sheet:
    def __init__(self, spreadsheet):
        self.spreadsheet = spreadsheet

    @classmethod
    def open(cls, service_account_info: dict, sheet_id: str) -> "Sheet":
        import gspread

        return cls(gspread.service_account_from_dict(service_account_info).open_by_key(sheet_id))

    def read_all(self) -> dict[str, list[dict]]:
        tabs = list(HEADERS)
        response = self.spreadsheet.values_batch_get([f"{tab}!A:{_last_column(tab)}" for tab in tabs])
        return {tab: parse_rows(tab, vr.get("values", [])) for tab, vr in zip(tabs, response["valueRanges"])}

    def write(self, updates: list[Update], appends: dict[str, list[dict]]) -> None:
        tabs = sorted({u.tab for u in updates} | {tab for tab, rows in appends.items() if rows})
        if not tabs:
            return
        response = self.spreadsheet.values_batch_get([f"{tab}!A:A" for tab in tabs])
        keys = {
            tab: [row[0] if row else "" for row in vr.get("values", [])]
            for tab, vr in zip(tabs, response["valueRanges"])
        }
        data = []
        for update in updates:
            header = HEADERS[update.tab]
            for number, key in enumerate(keys[update.tab], start=1):
                if number > 1 and key == str(update.key):
                    for column, value in update.fields.items():
                        cell = f"{update.tab}!{column_letter(header.index(column))}{number}"
                        data.append({"range": cell, "values": [[value]]})
        for tab, rows in appends.items():
            if rows:
                data.append({"range": f"{tab}!A{len(keys[tab]) + 1}", "values": _values(tab, rows)})
        if data:
            self.spreadsheet.values_batch_update({"valueInputOption": "RAW", "data": data})

    def replace(self, tab: str, rows: list[dict]) -> None:
        self.spreadsheet.values_clear(f"{tab}!A2:{_last_column(tab)}")
        if rows:
            self.spreadsheet.values_batch_update(
                {"valueInputOption": "RAW", "data": [{"range": f"{tab}!A2", "values": _values(tab, rows)}]}
            )

    def ensure_tabs(self) -> list[str]:
        existing = {worksheet.title for worksheet in self.spreadsheet.worksheets()}
        created = [tab for tab in HEADERS if tab not in existing]
        for tab in created:
            self.spreadsheet.add_worksheet(title=tab, rows=1000, cols=len(HEADERS[tab]))
        self.spreadsheet.values_batch_update(
            {"valueInputOption": "RAW", "data": [{"range": f"{tab}!A1", "values": [h]} for tab, h in HEADERS.items()]}
        )
        return created
```

- [ ] **Step 6: Run to verify pass**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_sheet.py -q`
Expected: 8 passed

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock tv-tracker/job/config.py tv-tracker/job/sheet.py tv-tracker/tests/fakes.py tv-tracker/tests/test_sheet.py
git commit -m "feat(tv-tracker): Sheet I/O with key-located writes and an in-memory fake

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: Tracked state

**Files:**
- Create: `tv-tracker/job/state.py`
- Test: `tv-tracker/tests/test_state.py`

**Interfaces:**
- Consumes: rows from `Sheet.read_all()["Tracked"]` (all string values).
- Produces: `truthy(value) -> bool`; `@dataclass Show(tmdb_id: int, name: str, first_air_year: int | None, poster_url: str, added_at: date, tvmaze_id: int | None)`; `active_shows(rows) -> list[Show]` (duplicates collapsed: earliest active `added_at`, any `tvmaze_id`); `all_tracked_ids(rows) -> set[int]` (active or not).

- [ ] **Step 1: Write the failing tests**

`tv-tracker/tests/test_state.py`:
```python
from datetime import date

from job.state import active_shows, all_tracked_ids, truthy


def row(**overrides):
    base = {"tmdb_id": "1", "tvmaze_id": "", "name": "One", "first_air_year": "2020", "poster_url": "p", "added_at": "2026-09-20", "active": "TRUE"}
    return base | overrides


def test_truthy():
    assert truthy("TRUE") and truthy(" true ") and truthy(True)
    assert not truthy("FALSE") and not truthy("") and not truthy("yes")


def test_active_shows_parses_types():
    [show] = active_shows([row(tvmaze_id="44")])
    assert (show.tmdb_id, show.name, show.first_air_year, show.added_at, show.tvmaze_id) == (1, "One", 2020, date(2026, 9, 20), 44)


def test_duplicates_collapse_to_earliest_added_and_any_tvmaze_id():
    [show] = active_shows([row(added_at="2026-09-22"), row(added_at="2026-09-10", tvmaze_id="44"), row(added_at="2026-09-01", active="FALSE")])
    assert show.added_at == date(2026, 9, 10)
    assert show.tvmaze_id == 44


def test_inactive_and_garbage_rows_are_skipped():
    rows = [row(active="FALSE"), row(tmdb_id=""), row(tmdb_id="abc"), row(tmdb_id="2", added_at="soon"), row(tmdb_id="3", first_air_year="")]
    assert [(s.tmdb_id, s.first_air_year) for s in active_shows(rows)] == [(3, None)]


def test_all_tracked_ids_includes_inactive():
    assert all_tracked_ids([row(), row(tmdb_id="2", active="FALSE"), row(tmdb_id="")]) == {1, 2}
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_state.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'job.state'`

- [ ] **Step 3: Implement**

`tv-tracker/job/state.py`:
```python
from dataclasses import dataclass
from datetime import date


def truthy(value) -> bool:
    return str(value).strip().upper() == "TRUE"


@dataclass
class Show:
    tmdb_id: int
    name: str
    first_air_year: int | None
    poster_url: str
    added_at: date
    tvmaze_id: int | None


def _int(value: str) -> int | None:
    return int(value) if str(value).strip().isdigit() else None


def active_shows(rows: list[dict]) -> list[Show]:
    shows: dict[int, Show] = {}
    for row in rows:
        tmdb_id = _int(row["tmdb_id"])
        if not truthy(row["active"]) or tmdb_id is None:
            continue
        try:
            added_at = date.fromisoformat(row["added_at"])
        except ValueError:
            continue
        tvmaze_id = _int(row["tvmaze_id"])
        show = shows.get(tmdb_id)
        if show is None:
            shows[tmdb_id] = Show(tmdb_id, row["name"], _int(row["first_air_year"]), row["poster_url"], added_at, tvmaze_id)
        else:
            show.added_at = min(show.added_at, added_at)
            show.tvmaze_id = show.tvmaze_id or tvmaze_id
    return list(shows.values())


def all_tracked_ids(rows: list[dict]) -> set[int]:
    return {tmdb_id for row in rows if (tmdb_id := _int(row["tmdb_id"])) is not None}
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_state.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add tv-tracker/job/state.py tv-tracker/tests/test_state.py
git commit -m "feat(tv-tracker): collapse Tracked rows into active shows

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: Episode facts, new cards and links

**Files:**
- Modify: `tv-tracker/job/tmdb.py` (add `episode_imdb`)
- Create: `tv-tracker/job/cards.py`
- Test: `tv-tracker/tests/test_cards.py`, `tv-tracker/tests/test_tmdb.py` (append)

**Interfaces:**
- Consumes: `Show`; TMDB show JSON (`seasons`, `poster_path`, `name`, `external_ids`, and `season/N` keys with `episodes`).
- Produces: `parse_date(value) -> date | None`; `new_card(*, now: str, **fields) -> dict` (defaults `body/link/image_url/source_url = ""`, sets `created_at`, `updated_at` = now, `current=True`, `status="new"`); `EPISODE_CONTENT = ("show_name", "headline", "date", "image_url")`; `seasons_to_fetch(data, added_at, today) -> list[int]` (max 19); `episode_facts(show, data, today) -> list[dict]` (keys `card_id, type, tmdb_id, show_name, headline, date, image_url, season, episode`); `episode_link(lookup, tmdb_id, show_imdb, season, episode) -> str`. `Tmdb.episode_imdb(tmdb_id, season, episode) -> str | None`.

- [ ] **Step 1: Write the failing tests**

Append to `tv-tracker/tests/test_tmdb.py`:
```python
def test_episode_imdb():
    transport, seen = recording({"imdb_id": "tt9"})
    assert Tmdb("tok", transport=transport).episode_imdb(1, 2, 3) == "tt9"
    assert seen[0].url.path == "/3/tv/1/season/2/episode/3/external_ids"
```

`tv-tracker/tests/test_cards.py`:
```python
from datetime import date

from job.cards import episode_facts, episode_link, new_card, seasons_to_fetch
from job.state import Show

SHOW = Show(1, "One", 2020, "https://poster", date(2026, 9, 20), None)
SEASONS = [
    {"season_number": 0, "air_date": "2019-01-01"},
    {"season_number": 1, "air_date": "2025-01-10"},
    {"season_number": 2, "air_date": "2026-08-01"},
    {"season_number": 3, "air_date": "2026-09-25"},
    {"season_number": 4, "air_date": "2027-01-01"},
    {"season_number": 5, "air_date": None},
]


def test_seasons_from_the_one_current_at_tracking_through_latest_aired():
    assert seasons_to_fetch({"seasons": SEASONS}, date(2026, 9, 20), date(2026, 9, 28)) == [2, 3]


def test_seasons_when_tracked_before_any_premiere_start_at_first_aired():
    assert seasons_to_fetch({"seasons": SEASONS}, date(2020, 1, 1), date(2026, 9, 28)) == [1, 2, 3]


def test_seasons_for_a_show_that_has_never_aired():
    assert seasons_to_fetch({"seasons": [{"season_number": 1, "air_date": "2027-01-01"}]}, date(2026, 9, 20), date(2026, 9, 28)) == []
    assert seasons_to_fetch({}, date(2026, 9, 20), date(2026, 9, 28)) == []


def test_seasons_capped_at_nineteen_most_recent():
    many = [{"season_number": n, "air_date": f"{2000 + n}-01-01"} for n in range(1, 25)]
    assert seasons_to_fetch({"seasons": many}, date(1990, 1, 1), date(2026, 9, 28)) == list(range(6, 25))


def episode(season, number, air_date, name="Ep", still=None):
    return {"season_number": season, "episode_number": number, "air_date": air_date, "name": name, "still_path": still}


def test_episode_facts_window_is_inclusive_and_builds_fields():
    data = {
        "name": "One (TMDB)",
        "poster_path": "/p.jpg",
        "season/3": {
            "episodes": [
                episode(3, 1, "2026-09-19"),
                episode(3, 2, "2026-09-20", "Two", "/s.jpg"),
                episode(3, 3, "2026-09-28", "TBA"),
                episode(3, 4, "2026-09-29"),
                episode(3, 5, None),
            ]
        },
    }
    facts = episode_facts(SHOW, data, date(2026, 9, 28))
    assert [f["card_id"] for f in facts] == ["ep:1:S03E02", "ep:1:S03E03"]
    first = facts[0]
    assert first["headline"] == "S03E02 · Two"
    assert first["show_name"] == "One (TMDB)"
    assert first["image_url"] == "https://image.tmdb.org/t/p/w342/s.jpg"
    assert facts[1]["image_url"] == "https://image.tmdb.org/t/p/w342/p.jpg"
    assert (first["type"], first["tmdb_id"], first["date"], first["season"], first["episode"]) == ("episode", 1, "2026-09-20", 3, 2)


def test_episode_facts_falls_back_to_tracked_name_and_poster():
    data = {"season/1": {"episodes": [episode(1, 1, "2026-09-21", name="")]}}
    [fact] = episode_facts(SHOW, data, date(2026, 9, 28))
    assert (fact["show_name"], fact["image_url"], fact["headline"]) == ("One", "https://poster", "S01E01 · TBA")


def test_new_card_defaults():
    card = new_card(now="T", card_id="x", type="news", headline="h")
    assert card == {
        "body": "", "link": "", "image_url": "", "source_url": "",
        "card_id": "x", "type": "news", "headline": "h",
        "created_at": "T", "current": True, "status": "new", "updated_at": "T",
    }


def test_episode_link_prefers_episode_then_show_imdb_then_tmdb():
    assert episode_link(lambda *a: "tt9", 1, "tt1", 3, 2) == "https://www.imdb.com/title/tt9/"
    assert episode_link(lambda *a: None, 1, "tt1", 3, 2) == "https://www.imdb.com/title/tt1/"
    assert episode_link(lambda *a: None, 1, None, 3, 2) == "https://www.themoviedb.org/tv/1/season/3/episode/2"
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_cards.py tv-tracker/tests/test_tmdb.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'job.cards'` (and `episode_imdb` missing)

- [ ] **Step 3: Implement**

Add to the `Tmdb` class in `tv-tracker/job/tmdb.py`:
```python
    def episode_imdb(self, tmdb_id: int, season: int, episode: int) -> str | None:
        path = f"/tv/{tmdb_id}/season/{season}/episode/{episode}/external_ids"
        return get_json(self.client, path).get("imdb_id")
```

`tv-tracker/job/cards.py`:
```python
from datetime import date

from job.state import Show
from job.tmdb import image_url

EPISODE_CONTENT = ("show_name", "headline", "date", "image_url")
MAX_SEASONS = 19


def parse_date(value) -> date | None:
    try:
        return date.fromisoformat(value) if value else None
    except ValueError:
        return None


def new_card(*, now: str, **fields) -> dict:
    return {
        "body": "",
        "link": "",
        "image_url": "",
        "source_url": "",
        **fields,
        "created_at": now,
        "current": True,
        "status": "new",
        "updated_at": now,
    }


def seasons_to_fetch(data: dict, added_at: date, today: date) -> list[int]:
    aired = []
    for season in data.get("seasons", []):
        premiered = parse_date(season.get("air_date"))
        if season["season_number"] > 0 and premiered and premiered <= today:
            aired.append((season["season_number"], premiered))
    aired.sort()
    if not aired:
        return []
    started = [number for number, premiered in aired if premiered <= added_at]
    first = started[-1] if started else aired[0][0]
    return [number for number, _ in aired if number >= first][-MAX_SEASONS:]


def episode_facts(show: Show, data: dict, today: date) -> list[dict]:
    show_name = data.get("name") or show.name
    poster = image_url(data.get("poster_path")) or show.poster_url
    facts = []
    for key, season in data.items():
        if not key.startswith("season/"):
            continue
        for episode in season.get("episodes", []):
            aired = parse_date(episode.get("air_date"))
            if aired is None or not show.added_at <= aired <= today:
                continue
            s, e = episode["season_number"], episode["episode_number"]
            facts.append(
                {
                    "card_id": f"ep:{show.tmdb_id}:S{s:02}E{e:02}",
                    "type": "episode",
                    "tmdb_id": show.tmdb_id,
                    "show_name": show_name,
                    "headline": f"S{s:02}E{e:02} · {episode.get('name') or 'TBA'}",
                    "date": aired.isoformat(),
                    "image_url": image_url(episode.get("still_path")) or poster,
                    "season": s,
                    "episode": e,
                }
            )
    return facts


def episode_link(lookup, tmdb_id: int, show_imdb: str | None, season: int, episode: int) -> str:
    imdb_id = lookup(tmdb_id, season, episode) or show_imdb
    if imdb_id:
        return f"https://www.imdb.com/title/{imdb_id}/"
    return f"https://www.themoviedb.org/tv/{tmdb_id}/season/{season}/episode/{episode}"
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add tv-tracker/job/tmdb.py tv-tracker/job/cards.py tv-tracker/tests/test_cards.py tv-tracker/tests/test_tmdb.py
git commit -m "feat(tv-tracker): episode facts with season catch-up, card builder, episode links

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Reconcile content and season cards

**Files:**
- Create: `tv-tracker/job/reconcile.py`
- Test: `tv-tracker/tests/test_reconcile.py`

**Interfaces:**
- Consumes: `Update`, `truthy`, `parse_date`, `new_card`, `image_url`; existing Cards rows (string values).
- Produces: `content_updates(existing: dict[str, dict], facts: list[dict], fields) -> list[Update]`; `reconcile_seasons(tmdb_id: int, show_name: str, data: dict, cards: list[dict], today: date, poster: str, now: str) -> tuple[list[dict], list[Update]]`.

- [ ] **Step 1: Write the failing tests**

`tv-tracker/tests/test_reconcile.py`:
```python
from datetime import date

from job.reconcile import content_updates, reconcile_seasons
from job.sheet import Update

TODAY = date(2026, 9, 27)


def test_content_updates_only_changed_fields_of_existing_cards():
    existing = {"ep:1:S01E01": {"card_id": "ep:1:S01E01", "show_name": "One", "headline": "S01E01 · TBA", "date": "2026-09-27", "image_url": "i", "status": "noted"}}
    facts = [
        {"card_id": "ep:1:S01E01", "show_name": "One", "headline": "S01E01 · Pilot", "date": "2026-09-27", "image_url": "i"},
        {"card_id": "ep:1:S01E02", "show_name": "One", "headline": "new", "date": "2026-09-27", "image_url": "i"},
    ]
    assert content_updates(existing, facts, ("show_name", "headline", "date", "image_url")) == [
        Update("Cards", "ep:1:S01E01", {"headline": "S01E01 · Pilot"})
    ]


def season_card(date_, current="TRUE", status="new"):
    return {"card_id": f"season:1:2:{date_}", "current": current, "status": status}


def run(air_date, cards, seasons=None):
    data = {"seasons": seasons if seasons is not None else [{"season_number": 1, "air_date": "2025-01-01"}, {"season_number": 2, "air_date": air_date, "poster_path": "/s2.jpg"}]}
    return reconcile_seasons(1, "One", data, cards, TODAY, "poster", "T")


def test_announced_date_appends_current_card():
    appends, updates = run("2026-12-01", [])
    assert updates == []
    [card] = appends
    assert card["card_id"] == "season:1:2:2026-12-01"
    assert (card["type"], card["headline"], card["date"], card["current"], card["status"]) == ("season", "Season 2 premieres", "2026-12-01", True, "new")
    assert card["link"] == "https://www.themoviedb.org/tv/1/season/2"
    assert card["image_url"] == "https://image.tmdb.org/t/p/w342/s2.jpg"


def test_date_change_hides_old_and_appends_new():
    appends, updates = run("2026-12-15", [season_card("2026-12-01")])
    assert [c["card_id"] for c in appends] == ["season:1:2:2026-12-15"]
    assert updates == [Update("Cards", "season:1:2:2026-12-01", {"current": False})]


def test_date_changing_back_reactivates_original():
    cards = [season_card("2026-12-01", current="FALSE"), season_card("2026-12-15")]
    appends, updates = run("2026-12-01", cards)
    assert appends == []
    assert updates == [
        Update("Cards", "season:1:2:2026-12-01", {"current": True}),
        Update("Cards", "season:1:2:2026-12-15", {"current": False}),
    ]


def test_withdrawn_date_and_removed_season_hide_cards():
    _, updates = run(None, [season_card("2026-12-01")])
    assert updates == [Update("Cards", "season:1:2:2026-12-01", {"current": False})]
    _, updates = run("x", [season_card("2026-12-01")], seasons=[{"season_number": 1, "air_date": "2025-01-01"}])
    assert updates == [Update("Cards", "season:1:2:2026-12-01", {"current": False})]


def test_date_corrected_into_the_past_hides_card_without_appending():
    appends, updates = run("2026-09-26", [season_card("2026-09-30")])
    assert appends == []
    assert updates == [Update("Cards", "season:1:2:2026-09-30", {"current": False})]


def test_premiered_on_announced_date_stays_current_and_never_touches_status():
    appends, updates = run("2026-09-20", [season_card("2026-09-20", status="noted")])
    assert (appends, updates) == ([], [])


def test_show_not_yet_aired_gets_season_card():
    appends, _ = run("x", [], seasons=[{"season_number": 1, "air_date": "2026-11-01"}])
    assert [c["card_id"] for c in appends] == ["season:1:1:2026-11-01"]


def test_premiere_today_is_announced():
    appends, _ = run("2026-09-27", [])
    assert [c["card_id"] for c in appends] == ["season:1:2:2026-09-27"]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_reconcile.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'job.reconcile'`

- [ ] **Step 3: Implement**

`tv-tracker/job/reconcile.py`:
```python
from datetime import date

from job.cards import new_card, parse_date
from job.sheet import Update
from job.state import truthy
from job.tmdb import image_url


def content_updates(existing: dict[str, dict], facts: list[dict], fields) -> list[Update]:
    updates = []
    for fact in facts:
        row = existing.get(fact["card_id"])
        if row is None:
            continue
        changed = {field: fact[field] for field in fields if str(fact[field]) != str(row[field])}
        if changed:
            updates.append(Update("Cards", fact["card_id"], changed))
    return updates


def reconcile_seasons(
    tmdb_id: int, show_name: str, data: dict, cards: list[dict], today: date, poster: str, now: str
) -> tuple[list[dict], list[Update]]:
    seasons = {s["season_number"]: s for s in data.get("seasons", []) if s["season_number"] > 0}
    prefix = f"season:{tmdb_id}:"
    by_number: dict[int, list[dict]] = {}
    for card in cards:
        if card["card_id"].startswith(prefix):
            by_number.setdefault(int(card["card_id"].split(":")[2]), []).append(card)

    upcoming = {n for n, s in seasons.items() if (d := parse_date(s.get("air_date"))) is None or d >= today}
    appends, updates = [], []
    for number in sorted(upcoming | set(by_number)):
        season = seasons.get(number, {})
        air = parse_date(season.get("air_date"))
        target = f"{prefix}{number}:{air.isoformat()}" if air else None
        existing = by_number.get(number, [])
        if target and air >= today and target not in {c["card_id"] for c in existing}:
            appends.append(
                new_card(
                    now=now,
                    card_id=target,
                    type="season",
                    tmdb_id=tmdb_id,
                    show_name=show_name,
                    headline=f"Season {number} premieres",
                    date=air.isoformat(),
                    link=f"https://www.themoviedb.org/tv/{tmdb_id}/season/{number}",
                    image_url=image_url(season.get("poster_path")) or poster,
                )
            )
        for card in existing:
            wanted = card["card_id"] == target
            if truthy(card["current"]) != wanted:
                updates.append(Update("Cards", card["card_id"], {"current": wanted}))
    return appends, updates
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_reconcile.py -q`
Expected: 9 passed

- [ ] **Step 5: Commit**

```bash
git add tv-tracker/job/reconcile.py tv-tracker/tests/test_reconcile.py
git commit -m "feat(tv-tracker): reconcile episode content and season-card current flags

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Weekly schedule

**Files:**
- Modify: `tv-tracker/job/tvmaze.py` (add `show_with_episodes`)
- Create: `tv-tracker/job/schedule.py`
- Test: `tv-tracker/tests/test_schedule.py`, `tv-tracker/tests/test_tvmaze.py` (append)

**Interfaces:**
- Consumes: `Show`, `config.TZ`, `image_url`; TVmaze `/shows/{id}?embed=episodes` JSON; TMDB show JSON.
- Produces: `Tvmaze.show_with_episodes(tvmaze_id) -> dict`; `week_start(today) -> date` (Monday); `in_week(stamp: str, today) -> bool`; `schedule_rows(show, tvmaze_show: dict, tmdb_data: dict, today, now: str) -> list[dict]`; `merge_schedule(fresh: dict[int, list[dict]], failed: set[int], previous: list[dict], today) -> list[dict]` (sorted by `airstamp`).

- [ ] **Step 1: Write the failing tests**

Append to `tv-tracker/tests/test_tvmaze.py`:
```python
def test_show_with_episodes_embeds_episodes():
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json={"id": 5, "_embedded": {"episodes": []}})

    assert Tvmaze(transport=httpx.MockTransport(handler)).show_with_episodes(5)["id"] == 5
    assert seen[0].url.path == "/shows/5"
    assert seen[0].url.params["embed"] == "episodes"
```

`tv-tracker/tests/test_schedule.py`:
```python
from datetime import date

from job.schedule import in_week, merge_schedule, schedule_rows, week_start
from job.state import Show

TODAY = date(2026, 9, 30)  # Wednesday; week is Mon 09-28 .. Sun 10-04
SHOW = Show(1, "One", 2020, "https://poster", date(2026, 9, 1), 11)


def ep(season, number, airstamp, airtime="21:00", name="Ep", image=None):
    return {"season": season, "number": number, "name": name, "airstamp": airstamp, "airtime": airtime, "image": image}


def tv(*episodes, network="FX", web=None):
    return {"network": {"name": network} if network else None, "webChannel": {"name": web} if web else None, "image": {"medium": "https://tvm"}, "_embedded": {"episodes": list(episodes)}}


def test_week_bounds():
    assert week_start(TODAY) == date(2026, 9, 28)
    assert week_start(date(2026, 9, 28)) == date(2026, 9, 28)
    assert in_week("2026-09-28", TODAY) and in_week("2026-10-04T23:30-04:00", TODAY)
    assert not in_week("2026-09-27", TODAY) and not in_week("2026-10-05", TODAY)


def test_rows_in_toronto_week_with_times_and_labels():
    show_json = tv(
        ep(1, 1, "2026-09-28T01:00:00+00:00"),  # Sun 09-27 21:00 local: last week
        ep(1, 2, "2026-09-29T01:00:00+00:00", name="Two"),  # Mon 09-28 21:00
        ep(1, 3, "2026-10-05T01:00:00+00:00"),  # Sun 10-04 21:00: this week
        ep(1, 4, None),
    )
    rows = schedule_rows(SHOW, show_json, {}, TODAY, "T")
    assert [(r["airstamp"], r["episode_label"]) for r in rows] == [
        ("2026-09-28T21:00-04:00", "S01E02 · Two"),
        ("2026-10-04T21:00-04:00", "S01E03 · Ep"),
    ]
    assert rows[0] == {
        "tmdb_id": 1, "airstamp": "2026-09-28T21:00-04:00", "show_name": "One", "episode_label": "S01E02 · Two",
        "network": "FX", "image_url": "https://tvm", "refreshed_at": "T",
    }


def test_streaming_without_airtime_is_date_only_and_uses_web_channel():
    rows = schedule_rows(SHOW, tv(ep(6, 1, "2026-09-30T12:00:00+00:00", airtime=""), network=None, web="Apple TV"), {}, TODAY, "T")
    assert [(r["airstamp"], r["network"]) for r in rows] == [("2026-09-30", "Apple TV")]


def test_special_with_no_number():
    rows = schedule_rows(SHOW, tv(ep(3, None, "2026-10-01T01:00:00+00:00", name="Halloween")), {}, TODAY, "T")
    assert rows[0]["episode_label"] == "S03 special · Halloween"


def test_tmdb_fallback_when_tvmaze_has_nothing_this_week():
    tmdb = {"poster_path": "/p.jpg", "networks": [{"name": "Cartoon Network"}], "next_episode_to_air": {"air_date": "2026-10-03", "season_number": 1, "episode_number": 7, "name": "Special"}}
    rows = schedule_rows(SHOW, {}, tmdb, TODAY, "T")
    assert [(r["airstamp"], r["episode_label"], r["network"], r["image_url"]) for r in rows] == [
        ("2026-10-03", "S01E07 · Special", "Cartoon Network", "https://image.tmdb.org/t/p/w342/p.jpg")
    ]
    later = {"next_episode_to_air": {"air_date": "2026-10-10", "season_number": 1, "episode_number": 7, "name": "x"}}
    assert schedule_rows(SHOW, {}, later, TODAY, "T") == []


def test_no_tmdb_fallback_when_tvmaze_has_rows():
    tmdb = {"next_episode_to_air": {"air_date": "2026-10-03", "season_number": 1, "episode_number": 7, "name": "x"}}
    rows = schedule_rows(SHOW, tv(ep(1, 6, "2026-09-29T01:00:00+00:00")), tmdb, TODAY, "T")
    assert len(rows) == 1


def test_merge_carries_failed_shows_in_week_and_sorts():
    fresh = {1: [{"tmdb_id": 1, "airstamp": "2026-10-01T21:00-04:00"}]}
    previous = [
        {"tmdb_id": "2", "airstamp": "2026-09-29", "show_name": "Two", "_row": 2},
        {"tmdb_id": "2", "airstamp": "2026-09-21", "show_name": "Two", "_row": 3},
        {"tmdb_id": "1", "airstamp": "2026-09-30", "show_name": "One", "_row": 4},
        {"tmdb_id": "3", "airstamp": "2026-09-30", "show_name": "Gone", "_row": 5},
    ]
    merged = merge_schedule(fresh, {2}, previous, TODAY)
    assert merged == [
        {"tmdb_id": "2", "airstamp": "2026-09-29", "show_name": "Two"},
        {"tmdb_id": 1, "airstamp": "2026-10-01T21:00-04:00"},
    ]
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_schedule.py tv-tracker/tests/test_tvmaze.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'job.schedule'`

- [ ] **Step 3: Implement**

Add to the `Tvmaze` class in `tv-tracker/job/tvmaze.py`:
```python
    def show_with_episodes(self, tvmaze_id: int) -> dict:
        return get_json(self.client, f"/shows/{tvmaze_id}", {"embed": "episodes"})
```

`tv-tracker/job/schedule.py`:
```python
from datetime import date, datetime, timedelta

from job.config import TZ
from job.state import Show
from job.tmdb import image_url


def week_start(today: date) -> date:
    return today - timedelta(days=today.weekday())


def in_week(stamp: str, today: date) -> bool:
    start = week_start(today)
    return start <= date.fromisoformat(stamp[:10]) < start + timedelta(days=7)


def _label(season: int, number: int | None, name: str | None) -> str:
    code = f"S{season:02}E{number:02}" if number else f"S{season:02} special"
    return f"{code} · {name}" if name else code


def _row(show: Show, airstamp: str, label: str, network: str, image: str, now: str) -> dict:
    return {
        "tmdb_id": show.tmdb_id,
        "airstamp": airstamp,
        "show_name": show.name,
        "episode_label": label,
        "network": network,
        "image_url": image,
        "refreshed_at": now,
    }


def schedule_rows(show: Show, tvmaze_show: dict, tmdb_data: dict, today: date, now: str) -> list[dict]:
    network = (tvmaze_show.get("network") or tvmaze_show.get("webChannel") or {}).get("name", "")
    show_image = (
        (tvmaze_show.get("image") or {}).get("medium") or image_url(tmdb_data.get("poster_path")) or show.poster_url
    )
    rows = []
    for episode in tvmaze_show.get("_embedded", {}).get("episodes", []):
        if not episode.get("airstamp"):
            continue
        local = datetime.fromisoformat(episode["airstamp"]).astimezone(TZ)
        stamp = local.isoformat(timespec="minutes") if episode.get("airtime") else local.date().isoformat()
        if in_week(stamp, today):
            image = (episode.get("image") or {}).get("medium") or show_image
            label = _label(episode["season"], episode.get("number"), episode.get("name"))
            rows.append(_row(show, stamp, label, network, image, now))

    upcoming = tmdb_data.get("next_episode_to_air") or {}
    if not rows and upcoming.get("air_date") and in_week(upcoming["air_date"], today):
        tmdb_network = (tmdb_data.get("networks") or [{}])[0].get("name", "")
        label = _label(upcoming["season_number"], upcoming.get("episode_number"), upcoming.get("name"))
        image = image_url(upcoming.get("still_path")) or show_image
        rows.append(_row(show, upcoming["air_date"], label, network or tmdb_network, image, now))
    return rows


def merge_schedule(fresh: dict[int, list[dict]], failed: set[int], previous: list[dict], today: date) -> list[dict]:
    carried = [
        {key: value for key, value in row.items() if key != "_row"}
        for row in previous
        if row["tmdb_id"].isdigit() and int(row["tmdb_id"]) in failed and row["airstamp"] and in_week(row["airstamp"], today)
    ]
    rows = [row for show_rows in fresh.values() for row in show_rows] + carried
    return sorted(rows, key=lambda row: row["airstamp"])
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add tv-tracker/job/tvmaze.py tv-tracker/job/schedule.py tv-tracker/tests/test_schedule.py tv-tracker/tests/test_tvmaze.py
git commit -m "feat(tv-tracker): weekly schedule with TMDB fallback and carry-forward

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: LLM cards and Sheet-driven LLM inputs

**Files:**
- Create: `tv-tracker/job/steps.py` (move `run_suggestions` / `run_news` out of `__main__.py`)
- Modify: `tv-tracker/job/__main__.py` (import them from `job.steps`)
- Create: `tv-tracker/job/llm_cards.py`
- Test: `tv-tracker/tests/test_llm_cards.py`, `tv-tracker/tests/test_main.py` (append)

**Interfaces:**
- Consumes: `Suggestion`, `NewsItem`, `normalize_url`, `new_card`, `Show`, `all_tracked_ids`.
- Produces: `job.steps.run_suggestions(shows, client, search)` (now also treats `shows["other_known_ids"]` as known), `job.steps.run_news(shows, client, fetch, today)`, both with the same signatures and returns as Plan 1; `suggestion_card(s, now) -> dict`; `news_card_id(tmdb_id, url) -> str`; `news_card(item, show_name, poster, now) -> dict`; `llm_inputs(shows: list[Show], tracked_rows, cards, today, memory_days) -> dict` (keys `tracked, ignored, pending, recent_news, other_known_ids`).

- [ ] **Step 1: Move the steps (no behaviour change)**

Create `tv-tracker/job/steps.py` containing `run_suggestions` and `run_news` **moved verbatim** from `tv-tracker/job/__main__.py`, with the imports they need (`from datetime import date`, `from job import config, llm, validate`). In `__main__.py`, delete both functions and add `from job.steps import run_news, run_suggestions`.

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests -q`
Expected: all pass (pure move)

- [ ] **Step 2: Write the failing tests**

Append to `tv-tracker/tests/test_main.py`:
```python
def test_suggestions_treat_other_known_ids_as_known():
    calls = []
    payload = {"suggestions": [{"title": "X", "year": 2020, "reason": "r"}]}
    x_result = [{"id": 7, "name": "X", "first_air_date": "2020-01-01"}]
    shows = {"tracked": [SEVERANCE], "other_known_ids": [7]}
    _, kept, dropped = run_suggestions(shows, client_returning(payload, calls), lambda title: x_result)
    assert kept == []
    assert dropped == ["X (2020): already tracked, ignored or suggested"]
```

`tv-tracker/tests/test_llm_cards.py`:
```python
import hashlib
from datetime import date

from job.llm_cards import llm_inputs, news_card, news_card_id, suggestion_card
from job.state import Show
from job.validate import NewsItem, Suggestion

SHOWS = [Show(1, "One", 2020, "p1", date(2026, 9, 1), None), Show(2, "Two", None, "p2", date(2026, 9, 1), None)]


def test_suggestion_card():
    s = Suggestion(9, "Nine", 2025, "Because.", "https://poster", "https://www.themoviedb.org/tv/9")
    card = suggestion_card(s, "T")
    assert {k: card[k] for k in ("card_id", "type", "tmdb_id", "show_name", "headline", "body", "date", "link", "image_url", "status")} == {
        "card_id": "sugg:9", "type": "suggestion", "tmdb_id": 9, "show_name": "Nine", "headline": "Nine",
        "body": "Because.", "date": "2025", "link": "https://www.themoviedb.org/tv/9", "image_url": "https://poster", "status": "new",
    }


def test_news_card_id_uses_normalized_url_and_show():
    digest = hashlib.sha1(b"deadline.com/a").hexdigest()[:8]
    assert news_card_id(1, "https://www.deadline.com/a/?utm_source=x") == f"news:1:{digest}"
    assert news_card_id(2, "https://deadline.com/a") == f"news:2:{digest}"


def test_news_card():
    item = NewsItem(1, "Renewed", "It was renewed.", "https://deadline.com/a", date(2026, 9, 26))
    card = news_card(item, "One", "p1", "T")
    assert (card["type"], card["show_name"], card["headline"], card["body"], card["date"], card["link"], card["source_url"], card["image_url"]) == (
        "news", "One", "Renewed", "It was renewed.", "2026-09-26", "https://deadline.com/a", "https://deadline.com/a", "p1"
    )


def card(**fields):
    return {"card_id": "x", "type": "suggestion", "tmdb_id": "9", "show_name": "Nine", "headline": "", "date": "2025", "status": "new", "created_at": "2026-09-27T06:00:00-04:00"} | fields


def test_llm_inputs_from_sheet_state():
    tracked_rows = [{"tmdb_id": "1"}, {"tmdb_id": "2"}, {"tmdb_id": "5"}]
    cards = [
        card(),
        card(tmdb_id="8", show_name="Eight", date="2019", status="ignored"),
        card(tmdb_id="7", show_name="Seven", status="tracked"),
        card(type="news", tmdb_id="1", show_name="One", headline="Old news", created_at="2026-08-01T06:00:00-04:00"),
        card(type="news", tmdb_id="1", show_name="One", headline="Recent news", created_at="2026-09-20T06:00:00-04:00"),
    ]
    inputs = llm_inputs(SHOWS, tracked_rows, cards, date(2026, 9, 27), 30)
    assert inputs["tracked"] == [{"tmdb_id": 1, "name": "One", "first_air_year": 2020}, {"tmdb_id": 2, "name": "Two", "first_air_year": "?"}]
    assert inputs["pending"] == [{"tmdb_id": 9, "name": "Nine", "first_air_year": "2025"}]
    assert inputs["ignored"] == [{"tmdb_id": 8, "name": "Eight", "first_air_year": "2019"}]
    assert inputs["recent_news"] == [{"show": "One", "headline": "Recent news"}]
    assert inputs["other_known_ids"] == [1, 2, 5, 7, 8, 9]
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_llm_cards.py tv-tracker/tests/test_main.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'job.llm_cards'`; and `test_suggestions_treat_other_known_ids_as_known` fails (X kept)

- [ ] **Step 4: Implement**

In `tv-tracker/job/steps.py`, `run_suggestions`, change the `known = …` line to:
```python
    known = {s["tmdb_id"] for key in ("tracked", "ignored", "pending") for s in shows.get(key, [])}
    known |= set(shows.get("other_known_ids", []))
```

`tv-tracker/job/llm_cards.py`:
```python
import hashlib
from datetime import date, timedelta

from job.cards import new_card
from job.state import Show, all_tracked_ids
from job.validate import NewsItem, Suggestion, normalize_url


def suggestion_card(s: Suggestion, now: str) -> dict:
    return new_card(
        now=now,
        card_id=f"sugg:{s.tmdb_id}",
        type="suggestion",
        tmdb_id=s.tmdb_id,
        show_name=s.name,
        headline=s.name,
        body=s.reason,
        date=str(s.year),
        link=s.link,
        image_url=s.poster_url,
    )


def news_card_id(tmdb_id: int, url: str) -> str:
    return f"news:{tmdb_id}:{hashlib.sha1(normalize_url(url).encode()).hexdigest()[:8]}"


def news_card(item: NewsItem, show_name: str, poster: str, now: str) -> dict:
    return new_card(
        now=now,
        card_id=news_card_id(item.tmdb_id, item.source_url),
        type="news",
        tmdb_id=item.tmdb_id,
        show_name=show_name,
        headline=item.headline,
        body=item.summary,
        date=item.published.isoformat(),
        link=item.source_url,
        image_url=poster,
        source_url=item.source_url,
    )


def _as_show(card: dict) -> dict:
    return {"tmdb_id": int(card["tmdb_id"]), "name": card["show_name"], "first_air_year": card["date"]}


def llm_inputs(shows: list[Show], tracked_rows: list[dict], cards: list[dict], today: date, memory_days: int) -> dict:
    suggestions = [c for c in cards if c["type"] == "suggestion" and c["tmdb_id"].isdigit()]
    cutoff = (today - timedelta(days=memory_days)).isoformat()
    return {
        "tracked": [{"tmdb_id": s.tmdb_id, "name": s.name, "first_air_year": s.first_air_year or "?"} for s in shows],
        "ignored": [_as_show(c) for c in suggestions if c["status"] == "ignored"],
        "pending": [_as_show(c) for c in suggestions if c["status"] == "new"],
        "recent_news": [
            {"show": c["show_name"], "headline": c["headline"]}
            for c in cards
            if c["type"] == "news" and c["created_at"][:10] >= cutoff
        ],
        "other_known_ids": sorted(all_tracked_ids(tracked_rows) | {int(c["tmdb_id"]) for c in suggestions}),
    }
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests -q`
Expected: all pass

- [ ] **Step 6: Commit**

```bash
git add tv-tracker/job/steps.py tv-tracker/job/__main__.py tv-tracker/job/llm_cards.py tv-tracker/tests/test_llm_cards.py tv-tracker/tests/test_main.py
git commit -m "feat(tv-tracker): LLM result cards and Sheet-driven LLM inputs

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: The daily run

**Files:**
- Create: `tv-tracker/job/daily.py`
- Test: `tv-tracker/tests/test_daily.py`

**Interfaces:**
- Consumes: everything above; `tmdb` needs `show`, `episode_imdb` and `search`; `tvmaze` needs `lookup_imdb` and `show_with_episodes`.
- Produces: `@dataclass RunReport(appended: int, updated: int, failed_shows: list[str], failed_steps: list[str])` with `.ok`; `meta_rows(report, now: str, today: date) -> list[dict]`; `run_daily(sheet, tmdb, tvmaze, llm_client, fetch, now: datetime) -> RunReport`.

- [ ] **Step 1: Write the failing tests**

`tv-tracker/tests/test_daily.py`:
```python
from datetime import datetime

from fakes import FakeLlm, FakeTmdb, FakeTvmaze, get_cell, make_spreadsheet, set_cell

from job.config import TZ
from job.daily import run_daily
from job.sheet import Sheet

NOW = datetime(2026, 9, 28, 6, 0, tzinfo=TZ)  # Monday


def tracked(tmdb_id, name, added_at="2026-09-20", tvmaze_id=""):
    return {"tmdb_id": tmdb_id, "tvmaze_id": tvmaze_id, "name": name, "first_air_year": 2020, "poster_url": "", "added_at": added_at, "source": "import", "active": True}


def show_json(tmdb_id, name, seasons, next_episode=None):
    return {"id": tmdb_id, "name": name, "poster_path": f"/p{tmdb_id}.jpg", "external_ids": {"imdb_id": f"tt{tmdb_id}"}, "seasons": seasons, "next_episode_to_air": next_episode}


def episodes(*rows):
    return {"episodes": [{"season_number": s, "episode_number": e, "name": n, "air_date": d, "still_path": None} for s, e, n, d in rows]}


ONE = show_json(1, "One", [{"season_number": 1, "air_date": "2026-09-01"}, {"season_number": 2, "air_date": "2026-12-01"}])
ONE_S1 = episodes((1, 1, "Pilot", "2026-09-01"), (1, 2, "Two", "2026-09-28"))
ONE_TV = {"network": {"name": "FX"}, "_embedded": {"episodes": [{"season": 1, "number": 2, "name": "Two", "airstamp": "2026-09-29T01:00:00+00:00", "airtime": "21:00"}]}}
TWO = show_json(2, "Two", [{"season_number": 1, "air_date": "2026-01-01"}])


def world(sp_rows=None, tmdb_broken=(), tvmaze_broken=(), llm=None):
    sp = make_spreadsheet(**(sp_rows if sp_rows is not None else {"Tracked": [tracked(1, "One")]}))
    tmdb = FakeTmdb({1: ONE, 2: TWO}, {(1, 1): ONE_S1}, broken=tmdb_broken)
    tvmaze = FakeTvmaze({"tt1": 11, "tt2": 22}, {11: ONE_TV, 22: {}}, broken=tvmaze_broken)
    return sp, Sheet(sp), tmdb, tvmaze, llm or FakeLlm()


def meta(sp):
    return {row[0]: (row[1] if len(row) > 1 else "") for row in sp.grid["Meta"][1:] if row and row[0]}


def test_first_run_writes_cards_tvmaze_id_schedule_and_meta():
    sp, sheet, tmdb, tvmaze, llm = world()
    report = run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    assert report.ok
    cards = {r["card_id"]: r for r in sheet.read_all()["Cards"]}
    assert set(cards) == {"ep:1:S01E02", "season:1:2:2026-12-01"}
    assert cards["ep:1:S01E02"]["link"] == "https://www.imdb.com/title/tt1/"
    assert cards["ep:1:S01E02"]["status"] == "new"
    assert get_cell(sp, "Tracked", 1, "tvmaze_id") == "11"
    schedule = sheet.read_all()["Schedule"]
    assert [(r["airstamp"], r["network"]) for r in schedule] == [("2026-09-28T21:00-04:00", "FX")]
    assert meta(sp) == {"last_run_at": "2026-09-28T06:00:00-04:00", "last_run_ok": "TRUE", "schedule_week": "2026-09-28", "failed_shows": "", "failed_steps": ""}
    assert llm.calls == ["suggestions", "news"]


def test_second_run_is_idempotent():
    sp, sheet, tmdb, tvmaze, llm = world()
    run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    report = run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    assert (report.appended, report.updated) == (0, 0)
    assert len(sheet.read_all()["Cards"]) == 2


def test_noted_click_between_read_and_write_survives_content_update():
    sp, sheet, tmdb, tvmaze, llm = world()
    run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    tmdb.seasons[(1, 1)] = episodes((1, 2, "Second", "2026-09-28"))
    real_write = sheet.write

    def racing_write(updates, appends):
        set_cell(sp, "Cards", "ep:1:S01E02", "status", "noted")
        real_write(updates, appends)

    sheet.write = racing_write
    run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    assert get_cell(sp, "Cards", "ep:1:S01E02", "status") == "noted"
    assert get_cell(sp, "Cards", "ep:1:S01E02", "headline") == "S01E02 · Second"


def test_partial_failure_carries_schedule_and_reports():
    rows = {
        "Tracked": [tracked(1, "One"), tracked(2, "Two", tvmaze_id=22)],
        "Schedule": [{"tmdb_id": 2, "airstamp": "2026-09-30", "show_name": "Two", "episode_label": "S01E05"}],
    }
    sp, sheet, tmdb, tvmaze, llm = world(rows, tvmaze_broken={22})
    report = run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    assert not report.ok
    assert report.failed_shows == ["Two"]
    assert [(r["tmdb_id"], r["airstamp"]) for r in sheet.read_all()["Schedule"]] == [("1", "2026-09-28T21:00-04:00"), ("2", "2026-09-30")]
    assert meta(sp)["last_run_ok"] == "FALSE"
    assert meta(sp)["failed_shows"] == "Two"
    assert "ep:1:S01E02" in {r["card_id"] for r in sheet.read_all()["Cards"]}


def test_llm_outage_still_writes_fact_cards():
    sp, sheet, tmdb, tvmaze, _ = world(llm=FakeLlm(fail=True))
    report = run_daily(sheet, tmdb, tvmaze, FakeLlm(fail=True), lambda url: None, NOW)
    assert report.failed_steps == ["suggestions", "news"]
    assert len(sheet.read_all()["Cards"]) == 2
    assert meta(sp)["failed_steps"] == "suggestions, news"


def test_duplicate_news_in_one_run_appended_once():
    url = "https://deadline.com/one-renewed"
    item = {"tmdb_id": 1, "headline": "One renewed", "summary": "s", "source_url": url, "published_date": "2026-09-27"}
    llm = FakeLlm({"news": {"news": [item, item | {"headline": "Same story"}]}}, sources=[url])
    sp, sheet, tmdb, tvmaze, _ = world(llm=llm)
    run_daily(sheet, tmdb, tvmaze, llm, lambda u: "<html></html>", NOW)
    news = [r for r in sheet.read_all()["Cards"] if r["type"] == "news"]
    assert [(r["headline"], r["show_name"], r["image_url"]) for r in news] == [("One renewed", "One", "https://image.tmdb.org/t/p/w342/p1.jpg")]


def test_news_already_in_sheet_is_not_appended_again():
    url = "https://deadline.com/one-renewed"
    item = {"tmdb_id": 1, "headline": "One renewed", "summary": "s", "source_url": url, "published_date": "2026-09-27"}
    llm = FakeLlm({"news": {"news": [item]}}, sources=[url])
    sp, sheet, tmdb, tvmaze, _ = world(llm=llm)
    run_daily(sheet, tmdb, tvmaze, llm, lambda u: "<html></html>", NOW)
    report = run_daily(sheet, tmdb, tvmaze, llm, lambda u: "<html></html>", NOW)
    assert report.appended == 0
    assert len([r for r in sheet.read_all()["Cards"] if r["type"] == "news"]) == 1


def test_empty_sheet_skips_llm_and_writes_meta():
    sp, sheet, tmdb, tvmaze, llm = world({})
    report = run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    assert report.ok
    assert llm.calls == []
    assert meta(sp)["last_run_ok"] == "TRUE"
    assert sheet.read_all()["Schedule"] == []


def test_tmdb_failure_marks_show_failed_and_skips_it():
    sp, sheet, tmdb, tvmaze, llm = world(tmdb_broken={1})
    report = run_daily(sheet, tmdb, tvmaze, llm, lambda url: None, NOW)
    assert report.failed_shows == ["One"]
    assert sheet.read_all()["Cards"] == []
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_daily.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'job.daily'`

- [ ] **Step 3: Implement**

`tv-tracker/job/daily.py`:
```python
import traceback
from dataclasses import dataclass, field
from datetime import date, datetime

from job import config
from job.cards import EPISODE_CONTENT, episode_facts, episode_link, new_card, seasons_to_fetch
from job.llm_cards import llm_inputs, news_card, suggestion_card
from job.reconcile import content_updates, reconcile_seasons
from job.schedule import merge_schedule, schedule_rows, week_start
from job.sheet import Update
from job.state import active_shows
from job.steps import run_news, run_suggestions
from job.tmdb import image_url

CARD_FIELDS = ("card_id", "type", "tmdb_id", "show_name", "headline", "date", "image_url")


@dataclass
class RunReport:
    appended: int = 0
    updated: int = 0
    failed_shows: list[str] = field(default_factory=list)
    failed_steps: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.failed_shows and not self.failed_steps


def meta_rows(report: RunReport, now: str, today: date) -> list[dict]:
    values = {
        "last_run_at": now,
        "last_run_ok": report.ok,
        "schedule_week": week_start(today).isoformat(),
        "failed_shows": ", ".join(report.failed_shows),
        "failed_steps": ", ".join(report.failed_steps),
    }
    return [{"key": key, "value": value} for key, value in values.items()]


def _failed(what: str) -> None:
    print(f"FAILED {what}:")
    traceback.print_exc()


def run_daily(sheet, tmdb, tvmaze, llm_client, fetch, now: datetime) -> RunReport:
    today, stamp = now.date(), now.isoformat(timespec="seconds")
    state = sheet.read_all()
    cards = state["Cards"]
    existing = {card["card_id"]: card for card in cards}
    shows = active_shows(state["Tracked"])
    report = RunReport()
    appends: list[dict] = []
    updates: list[Update] = []
    fresh: dict[int, list[dict]] = {}
    failed: set[int] = set()
    posters: dict[int, str] = {}

    def add(card: dict) -> None:
        if card["card_id"] not in existing:
            existing[card["card_id"]] = card
            appends.append(card)

    for show in shows:
        try:
            data = tmdb.show(show.tmdb_id)
            poster = posters[show.tmdb_id] = image_url(data.get("poster_path")) or show.poster_url
            show_imdb = data["external_ids"].get("imdb_id")
            if show.tvmaze_id is None and show_imdb:
                show.tvmaze_id = tvmaze.lookup_imdb(show_imdb)
                if show.tvmaze_id:
                    updates.append(Update("Tracked", show.tmdb_id, {"tvmaze_id": show.tvmaze_id}))
            if numbers := seasons_to_fetch(data, show.added_at, today):
                data = tmdb.show(show.tmdb_id, numbers)
            facts = episode_facts(show, data, today)
            updates += content_updates(existing, facts, EPISODE_CONTENT)
            for fact in facts:
                if fact["card_id"] not in existing:
                    link = episode_link(tmdb.episode_imdb, show.tmdb_id, show_imdb, fact["season"], fact["episode"])
                    add(new_card(now=stamp, link=link, **{key: fact[key] for key in CARD_FIELDS}))
            season_appends, season_updates = reconcile_seasons(
                show.tmdb_id, data.get("name") or show.name, data, cards, today, poster, stamp
            )
            for card in season_appends:
                add(card)
            updates += season_updates
            tvmaze_show = tvmaze.show_with_episodes(show.tvmaze_id) if show.tvmaze_id else {}
            fresh[show.tmdb_id] = schedule_rows(show, tvmaze_show, data, today, stamp)
        except Exception:
            _failed(show.name)
            report.failed_shows.append(show.name)
            failed.add(show.tmdb_id)

    inputs = llm_inputs(shows, state["Tracked"], cards, today, config.NEWS_MEMORY_DAYS)
    try:
        outcome = run_suggestions(inputs, llm_client, tmdb.search)
        for suggestion in outcome[1] if outcome else []:
            add(suggestion_card(suggestion, stamp))
    except Exception:
        _failed("suggestions")
        report.failed_steps.append("suggestions")
    try:
        outcome = run_news(inputs, llm_client, fetch, today)
        names = {show.tmdb_id: show.name for show in shows}
        for item in outcome[1] if outcome else []:
            add(news_card(item, names[item.tmdb_id], posters.get(item.tmdb_id, ""), stamp))
    except Exception:
        _failed("news")
        report.failed_steps.append("news")

    report.appended, report.updated = len(appends), len(updates)
    sheet.write(updates, {"Cards": appends})
    sheet.replace("Schedule", merge_schedule(fresh, failed, state["Schedule"], today))
    sheet.replace("Meta", meta_rows(report, stamp, today))
    return report
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests -q`
Expected: all pass

- [ ] **Step 5: Commit**

```bash
git add tv-tracker/job/daily.py tv-tracker/tests/test_daily.py
git commit -m "feat(tv-tracker): daily run orchestrating facts, schedule, LLM cards and Meta

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: CLI (`run` / `setup`) and the workflow

**Files:**
- Create: `tv-tracker/job/setup.py`
- Modify: `tv-tracker/job/__main__.py`
- Create: `.github/workflows/tv-tracker.yml`
- Test: `tv-tracker/tests/test_setup.py`, `tv-tracker/tests/test_main.py` (modify)

**Interfaces:**
- Consumes: `Sheet`, `run_daily`, `all_tracked_ids`, `image_url`.
- Produces: `import_rows(tracked: list[dict], existing_rows: list[dict], tmdb, now: datetime) -> list[dict]`; CLI `python -m job [run|setup] [--dry-run] [--shows PATH]`. `run` exits 1 when `report.ok` is false.

- [ ] **Step 1: Write the failing tests**

`tv-tracker/tests/test_setup.py`:
```python
from datetime import datetime

from fakes import FakeTmdb

from job.config import TZ
from job.setup import import_rows


def test_import_rows_skips_existing_and_fetches_posters():
    tmdb = FakeTmdb({1: {"poster_path": "/p1.jpg"}, 2: {"poster_path": None}})
    shows = [
        {"tmdb_id": 1, "name": "One", "first_air_year": 2020},
        {"tmdb_id": 2, "name": "Two", "first_air_year": 2021},
        {"tmdb_id": 3, "name": "Three", "first_air_year": 2022},
        {"tmdb_id": 1, "name": "One again", "first_air_year": 2020},
    ]
    rows = import_rows(shows, [{"tmdb_id": "3"}], tmdb, datetime(2026, 9, 28, 7, 0, tzinfo=TZ))
    assert rows == [
        {"tmdb_id": 1, "tvmaze_id": "", "name": "One", "first_air_year": 2020, "poster_url": "https://image.tmdb.org/t/p/w342/p1.jpg",
         "added_at": "2026-09-28", "source": "import", "active": True, "updated_at": "2026-09-28T07:00:00-04:00"},
        {"tmdb_id": 2, "tvmaze_id": "", "name": "Two", "first_air_year": 2021, "poster_url": "",
         "added_at": "2026-09-28", "source": "import", "active": True, "updated_at": "2026-09-28T07:00:00-04:00"},
    ]
```

In `tv-tracker/tests/test_main.py`, replace `test_requires_dry_run_flag` with:
```python
def test_rejects_unknown_command():
    with pytest.raises(SystemExit):
        main(["bogus"])
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_setup.py tv-tracker/tests/test_main.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'job.setup'`. (`test_rejects_unknown_command` already passes under the old parser; it pins that behaviour through the rewrite.)

- [ ] **Step 3: Implement**

`tv-tracker/job/setup.py`:
```python
from datetime import datetime

from job.state import all_tracked_ids
from job.tmdb import image_url


def import_rows(tracked: list[dict], existing_rows: list[dict], tmdb, now: datetime) -> list[dict]:
    have = all_tracked_ids(existing_rows)
    stamp = now.isoformat(timespec="seconds")
    rows = []
    for show in tracked:
        if show["tmdb_id"] in have:
            continue
        data = tmdb.show(show["tmdb_id"])
        rows.append(
            {
                "tmdb_id": show["tmdb_id"],
                "tvmaze_id": "",
                "name": show["name"],
                "first_air_year": show["first_air_year"],
                "poster_url": image_url(data.get("poster_path")),
                "added_at": now.date().isoformat(),
                "source": "import",
                "active": True,
                "updated_at": stamp,
            }
        )
        have.add(show["tmdb_id"])
    return rows
```

In `tv-tracker/job/__main__.py`:
- Add imports: `import sys`, `from job.daily import run_daily`, `from job.setup import import_rows`, `from job.sheet import Sheet`.
- Replace `main` with the version below. Move the current body after argument parsing (from `from openai import OpenAI` to the end) into a new function `dry_run(args) -> None`, unchanged.

```python
def open_sheet() -> Sheet:
    return Sheet.open(config.service_account_info(), config.sheet_id())


def setup(shows_path: Path) -> None:
    sheet = open_sheet()
    print(f"created tabs: {sheet.ensure_tabs() or 'none'}")
    tracked = json.loads(shows_path.read_text())["tracked"]
    rows = import_rows(tracked, sheet.read_all()["Tracked"], Tmdb(config.tmdb_token()), datetime.now(config.TZ))
    sheet.write([], {"Tracked": rows})
    print(f"imported {len(rows)} show(s)")


def run() -> None:
    from openai import OpenAI

    report = run_daily(
        open_sheet(), Tmdb(config.tmdb_token()), Tvmaze(), OpenAI(), validate.fetch_page, datetime.now(config.TZ)
    )
    print(f"appended {report.appended} card(s), updated {report.updated} cell group(s)")
    if not report.ok:
        print(f"failed shows: {report.failed_shows}; failed steps: {report.failed_steps}")
        sys.exit(1)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="job")
    parser.add_argument("command", nargs="?", choices=["run", "setup"], default="run")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--shows", type=Path, default=Path("shows.example.json"))
    parser.add_argument("--skip", action="append", choices=["facts", "suggestions", "news"], default=[])
    args = parser.parse_args(argv)
    if args.command == "setup":
        setup(args.shows)
    elif args.dry_run:
        dry_run(args)
    else:
        run()
```

`.github/workflows/tv-tracker.yml`:
```yaml
name: TV tracker daily

on:
  schedule:
    - cron: "0 10 * * *"
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: tv-tracker-sheet
  cancel-in-progress: false

jobs:
  run:
    runs-on: ubuntu-latest
    steps:
      - name: Check out
        uses: actions/checkout@v4

      - name: Set up uv
        uses: astral-sh/setup-uv@v6

      - name: Run daily job
        working-directory: tv-tracker
        env:
          TMDB_TOKEN: ${{ secrets.TMDB_TOKEN }}
          OPENAI_API_KEY: ${{ secrets.OPENAI_API_KEY }}
          GOOGLE_SERVICE_ACCOUNT_JSON: ${{ secrets.GOOGLE_SERVICE_ACCOUNT_JSON }}
          SHEET_ID: ${{ secrets.SHEET_ID }}
        run: uv run --frozen --group tv-tracker python -m job
```

- [ ] **Step 4: Run to verify pass and lint**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests -q && uvx ruff check --fix tv-tracker && uvx ruff format tv-tracker && uv run --group tv-tracker python -m pytest tv-tracker/tests -q`
Expected: all pass, no lint errors

- [ ] **Step 5: Commit**

```bash
git add tv-tracker .github/workflows/tv-tracker.yml
git commit -m "feat(tv-tracker): run/setup commands and daily GitHub Actions workflow

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 9: Go live (needs Nick)

**Files:** none committed except notes; credentials stay outside the repo.

- [ ] **Step 1: Google setup (Nick, manual)**
  1. console.cloud.google.com → new project `tv-tracker` → APIs & Services → enable **Google Sheets API**.
  2. IAM & Admin → Service Accounts → create `tv-tracker-job` (no roles) → Keys → Add key → JSON. Move the download to `~/.config/tv-tracker/service-account.json`.
  3. Create a blank Google Sheet named "TV Tracker". Share it as Editor with the service account's email (`…@….iam.gserviceaccount.com`) and with your wife. General access: **Restricted**.
  4. Copy the Sheet ID from its URL (`/d/<ID>/edit`).
  5. Add to `tv-tracker/.env`:
     ```
     SHEET_ID=...
     GOOGLE_SERVICE_ACCOUNT_FILE=~/.config/tv-tracker/service-account.json
     ```

- [ ] **Step 2: Set up and import**

Run (from `tv-tracker/`): `uv run --group tv-tracker --env-file .env python -m job setup --shows shows.json`
Expected: `created tabs: ['Tracked', 'Cards', 'Schedule', 'Meta']` (or similar), `imported 11 show(s)`. Delete the default `Sheet1` tab by hand.

- [ ] **Step 3: First real run locally**

Run: `uv run --group tv-tracker --env-file .env python -m job`
Expected: `appended N card(s)`, exit 0. Open the Sheet: Tracked has `tvmaze_id`s, Schedule has this week, Meta `last_run_ok` TRUE, Cards has season and suggestion cards (episode cards only for today's airings, since `added_at` is today).

- [ ] **Step 4: GitHub secrets (Nick)**

```bash
gh secret set TMDB_TOKEN        # paste when prompted
gh secret set OPENAI_API_KEY    # paste when prompted
gh secret set SHEET_ID          # paste when prompted
gh secret set GOOGLE_SERVICE_ACCOUNT_JSON < ~/.config/tv-tracker/service-account.json
```

- [ ] **Step 5: Merge to `main` and push (ask Nick first).** Scheduled workflows only run from the default branch. Then run `gh workflow run tv-tracker.yml` and watch it with `gh run watch`. Expected: green, and Meta's `last_run_at` updates.

- [ ] **Step 6: Notes.** Append go-live findings (aggregate only) to `posts/tv_tracker/notes/BUILD_NOTES.md` and commit.
