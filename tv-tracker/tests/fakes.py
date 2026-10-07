import json
import re
from types import SimpleNamespace as NS

from job.sheet import HEADERS

RANGE = re.compile(
    r"^(?P<tab>\w+)!(?P<c1>[A-Z]+)(?P<r1>\d*)(?::(?P<c2>[A-Z]+)(?P<r2>\d*))?$"
)


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
        self.grid = {
            tab: [[fmt(v) for v in row] for row in rows]
            for tab, rows in (tabs or {}).items()
        }
        self.batch_updates: list[dict] = []

    def worksheets(self):
        return [NS(title=tab) for tab in self.grid]

    def add_worksheet(self, title, rows, cols):
        self.added = getattr(self, "added", []) + [(title, rows, cols)]
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
        self.get_params = getattr(self, "get_params", []) + [params]
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

    def values_append(self, range, params=None, body=None):
        self.appends = getattr(self, "appends", []) + [(range, params)]
        tab = range.split("!")[0]
        grid = self.grid[tab]
        last = max((i for i, row in enumerate(grid) if any(row)), default=-1)
        for i, values in enumerate(body["values"]):
            row = self._row(tab, last + 2 + i)
            row[:] = [fmt(v) for v in values]

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
    def __init__(
        self,
        shows: dict[int, dict],
        seasons: dict[tuple[int, int], dict] | None = None,
        broken=(),
    ):
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

    def season(self, tmdb_id, number):
        if (tmdb_id, number, "season") in self.broken:
            raise RuntimeError("tmdb season down")
        return self.seasons.get((tmdb_id, number), {"episodes": []})

    def movie(self, movie_id):
        return self.shows[("movie", movie_id)]

    def episode_imdb(self, tmdb_id, season, episode):
        return None

    def search(self, title):
        return []


class FakeTvmaze:
    def __init__(
        self,
        lookups: dict[str, int],
        shows: dict[int, dict],
        broken=(),
        specials: dict[int, list[dict]] | None = None,
    ):
        self.lookups, self.shows, self.broken = lookups, shows, set(broken)
        self.special_episodes = specials or {}

    def show(self, tvmaze_id):
        return {
            key: value
            for key, value in self.shows[tvmaze_id].items()
            if key != "_embedded"
        }

    def specials(self, tvmaze_id):
        if ("specials", tvmaze_id) in self.broken:
            raise RuntimeError("tvmaze specials down")
        return self.special_episodes.get(tvmaze_id, [])

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
        output = [
            NS(
                type="web_search_call",
                action=NS(type="search", sources=[NS(url=u) for u in self.sources]),
            )
        ]
        return NS(
            output=output,
            output_text=json.dumps(self.payloads.get(name, {name: []})),
            usage=NS(input_tokens=1, output_tokens=1),
        )
