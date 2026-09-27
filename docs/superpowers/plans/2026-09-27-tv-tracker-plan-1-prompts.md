# TV Tracker Plan 1: API Clients, LLM Calls and Prompt Dry Run

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the project is feasible and tune the two LLM prompts, using a `--dry-run` that fetches real facts from TMDB/TVmaze and prints validated suggestions and news for a hand-written list of shows. No Sheet, no app.

**Architecture:** A Python package `job` under `tv-tracker/`. Thin HTTP clients (`tmdb.py`, `tvmaze.py`) share one retrying `get_json` helper. `llm.py` builds prompts from template files and calls the OpenAI Responses API with web search and a strict JSON schema. `validate.py` applies the spec's rules: suggestions are resolved against TMDB, and news must cite a URL the search tool actually returned, with a date checked from the page. `__main__.py` wires these into a dry run that prints results, dropped items with reasons, and token/search counts.

**Tech Stack:** Python ≥3.12, uv (dependency group `tv-tracker`), httpx, openai (Responses API, `web_search` tool), pytest with `httpx.MockTransport`.

**Spec:** `docs/superpowers/specs/2026-09-27-tv-tracker-design.md` (rev 4). This plan implements Build order step 1. Plans 2 (Sheet I/O + full job + workflow), 3 (app) and 4 (post) follow once the dry run shows the prompts are worth it.

## Global Constraints

- Work in the worktree `/Users/nick/Work/nicholastacik.github.io-tv-tracker` on branch `tv-tracker`.
- The job is run with `tv-tracker/` as the working directory: `uv run --group tv-tracker python -m job …` (the hyphenated folder isn't importable).
- Tests run from the repo root: `uv run --group tv-tracker python -m pytest tv-tracker/tests -q`. No network in tests.
- Timezone: `America/Toronto`. `NEWS_WINDOW_DAYS=7`, `NEWS_MEMORY_DAYS=30`, `MAX_PENDING_SUGGESTIONS=3`.
- HTTP clients retry transient errors (3 tries, backoff) before failing.
- LLM output schemas have an object root: `{"suggestions": [...]}` and `{"news": [...]}`. Request sources with `include: ["web_search_call.action.sources"]`.
- The LLM never supplies an ID, URL or image for a suggestion; TMDB does.
- News `source_url` must match (after normalizing scheme, `www.`, trailing slash, query string) a URL returned by the search call or its `url_citation` annotations.
- News page fetch: 5 s timeout, one try; non-2xx or failure → drop. The page's own date (`article:published_time`, JSON-LD `datePublished`, `<time datetime>`) replaces the model's.
- `OPENAI_MODEL` is config (default `gpt-5.6`, from current OpenAI docs); reasoning effort default `low`.
- Match repo style: ruff formatting, no docstrings or comments beyond what's needed, `uv` for deps.
- Secrets never committed: `tv-tracker/.env` is gitignored.

## Review Focus

1. **A title shared by a remake** (e.g. "Shōgun" 1980 vs 2024): suggestion resolution must match on year, not take TMDB's first result. → test in Task 5.
2. **The LLM's year is off by one** (announced year vs first-air year): an exact title match within ±1 year should still resolve, preferring an exact-year match. → test in Task 5.
3. **Citation URLs carry tracking params** (`?utm_source=chatgpt.com`) while the model's `source_url` doesn't, or vice versa: they must still match. → test in Task 6.
4. **Page dates with time and offset** (`2026-09-25T14:00:00-04:00`) or attribute order reversed in the `<meta>` tag: the date must still be read. → test in Task 6.
5. **Empty tracked list, or a full pending-suggestion queue:** the dry run must skip the LLM call rather than send a pointless request. → test in Task 7.

---

## File Structure

```
tv-tracker/
  .env                      # gitignored: TMDB_TOKEN, OPENAI_API_KEY
  shows.example.json        # hand-written input for the dry run
  job/
    __init__.py             # empty
    __main__.py             # CLI: --dry-run; run_suggestions / run_news
    config.py               # constants + env access
    http.py                 # get_json with retries
    tmdb.py                 # Tmdb client, image_url
    tvmaze.py               # Tvmaze client, next_airing
    llm.py                  # prompts, schemas, run(), extract_sources()
    validate.py             # resolve_suggestions, validate_news, fetch_page
    prompts/
      suggestions.md
      news.md
  tests/
    conftest.py             # puts tv-tracker/ on sys.path
    test_http.py
    test_tmdb.py
    test_tvmaze.py
    test_llm.py
    test_validate.py
    test_main.py
posts/tv_tracker/notes/BUILD_NOTES.md   # dry-run findings (Task 8)
```

The spec lists validation inside `llm.py`. It's split into `validate.py` here so the pure rules are tested without any OpenAI objects. `tv-tracker/tests/` has no `__init__.py` (jeopardy's `tests` package would clash in a shared run; CI runs them separately).

---

### Task 1: Scaffold, config and retrying HTTP helper

**Files:**
- Modify: `pyproject.toml` (new `tv-tracker` dependency group, via `uv add`)
- Modify: `.gitignore`
- Modify: `.github/workflows/test.yml`
- Create: `tv-tracker/job/__init__.py`, `tv-tracker/job/config.py`, `tv-tracker/job/http.py`
- Create: `tv-tracker/tests/conftest.py`
- Test: `tv-tracker/tests/test_http.py`

**Interfaces:**
- Produces: `job.http.get_json(client: httpx.Client, url: str, params: dict | None = None, *, tries: int = 3, sleep=time.sleep) -> Any`, which raises `httpx.HTTPStatusError` on a non-retryable status or after the last try. `job.config`: `TZ`, `NEWS_WINDOW_DAYS`, `NEWS_MEMORY_DAYS`, `MAX_PENDING_SUGGESTIONS`, `OPENAI_MODEL`, `OPENAI_REASONING_EFFORT`, `tmdb_token() -> str`.

- [ ] **Step 1: Add dependencies and ignore the env file**

```bash
cd /Users/nick/Work/nicholastacik.github.io-tv-tracker
uv add --group tv-tracker httpx openai pytest
printf '\n# TV tracker secrets (TMDB_TOKEN, OPENAI_API_KEY)\ntv-tracker/.env\n' >> .gitignore
mkdir -p tv-tracker/job/prompts tv-tracker/tests
touch tv-tracker/job/__init__.py
```

- [ ] **Step 2: Write `conftest.py` and `config.py`**

`tv-tracker/tests/conftest.py`:
```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
```

`tv-tracker/job/config.py`:
```python
import os
from zoneinfo import ZoneInfo

TZ = ZoneInfo("America/Toronto")
NEWS_WINDOW_DAYS = 7
NEWS_MEMORY_DAYS = 30
MAX_PENDING_SUGGESTIONS = 3
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.6")
OPENAI_REASONING_EFFORT = os.environ.get("OPENAI_REASONING_EFFORT", "low")


def tmdb_token() -> str:
    return os.environ["TMDB_TOKEN"]
```

- [ ] **Step 3: Write the failing tests**

`tv-tracker/tests/test_http.py`:
```python
import httpx
import pytest

from job.http import get_json


def client_for(responses):
    calls = []

    def handler(request):
        calls.append(request)
        response = responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    client = httpx.Client(base_url="https://x.test", transport=httpx.MockTransport(handler))
    return client, calls


def test_retries_server_error_then_succeeds():
    client, calls = client_for([httpx.Response(503), httpx.Response(200, json={"ok": 1})])
    sleeps = []
    assert get_json(client, "/a", sleep=sleeps.append) == {"ok": 1}
    assert len(calls) == 2
    assert sleeps == [1]


def test_client_error_raises_without_retry():
    client, calls = client_for([httpx.Response(404)])
    with pytest.raises(httpx.HTTPStatusError):
        get_json(client, "/a", sleep=lambda s: None)
    assert len(calls) == 1


def test_gives_up_after_three_tries():
    client, calls = client_for([httpx.Response(503)] * 3)
    with pytest.raises(httpx.HTTPStatusError):
        get_json(client, "/a", sleep=lambda s: None)
    assert len(calls) == 3


def test_retries_transport_error():
    client, calls = client_for([httpx.ConnectError("down"), httpx.Response(200, json=[])])
    assert get_json(client, "/a", sleep=lambda s: None) == []
    assert len(calls) == 2


def test_passes_query_params():
    client, calls = client_for([httpx.Response(200, json={})])
    get_json(client, "/a", {"q": "x"}, sleep=lambda s: None)
    assert calls[0].url.params["q"] == "x"
```

- [ ] **Step 4: Run to verify failure**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_http.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'job.http'`

- [ ] **Step 5: Implement `http.py`**

`tv-tracker/job/http.py`:
```python
import time

import httpx

RETRY_STATUS = {429, 500, 502, 503, 504}


def get_json(client: httpx.Client, url: str, params: dict | None = None, *, tries: int = 3, sleep=time.sleep):
    for attempt in range(tries):
        last = attempt == tries - 1
        try:
            response = client.get(url, params=params)
        except httpx.TransportError:
            if last:
                raise
        else:
            if response.status_code not in RETRY_STATUS or last:
                response.raise_for_status()
                return response.json()
        sleep(2**attempt)
```

- [ ] **Step 6: Run to verify pass**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_http.py -q`
Expected: 5 passed

- [ ] **Step 7: Add the CI step**

In `.github/workflows/test.yml`, after the `Python tests` step, add:
```yaml
      - name: TV tracker tests
        run: uv run --frozen --group tv-tracker python -m pytest tv-tracker/tests -q
```

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock .gitignore .github/workflows/test.yml tv-tracker/job/__init__.py tv-tracker/job/config.py tv-tracker/job/http.py tv-tracker/tests/conftest.py tv-tracker/tests/test_http.py
git commit -m "feat(tv-tracker): scaffold job package with retrying HTTP helper

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 2: TMDB client

**Files:**
- Create: `tv-tracker/job/tmdb.py`
- Test: `tv-tracker/tests/test_tmdb.py`

**Interfaces:**
- Consumes: `job.http.get_json`.
- Produces: `class Tmdb(token: str, transport: httpx.BaseTransport | None = None)` with `show(tmdb_id: int, seasons: Iterable[int] = ()) -> dict` (always appends `external_ids`, plus `season/N` for each season) and `search(title: str) -> list[dict]` (TMDB `results`, no year filter; the year matching happens in `validate.pick_match`). `image_url(path: str | None) -> str` returns `""` for a missing path.

- [ ] **Step 1: Write the failing tests**

`tv-tracker/tests/test_tmdb.py`:
```python
import httpx

from job.tmdb import Tmdb, image_url


def recording(json_body):
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=json_body)

    return httpx.MockTransport(handler), seen


def test_show_appends_external_ids_and_seasons():
    transport, seen = recording({"id": 95396})
    tmdb = Tmdb("tok", transport=transport)
    assert tmdb.show(95396, seasons=[1, 2]) == {"id": 95396}
    request = seen[0]
    assert request.url.path == "/3/tv/95396"
    assert request.url.params["append_to_response"] == "external_ids,season/1,season/2"
    assert request.headers["authorization"] == "Bearer tok"


def test_show_without_seasons_only_appends_external_ids():
    transport, seen = recording({"id": 1})
    Tmdb("tok", transport=transport).show(1)
    assert seen[0].url.params["append_to_response"] == "external_ids"


def test_search_returns_results_list():
    transport, seen = recording({"results": [{"id": 7, "name": "Shōgun"}]})
    assert Tmdb("tok", transport=transport).search("Shōgun") == [{"id": 7, "name": "Shōgun"}]
    assert seen[0].url.path == "/3/search/tv"
    assert seen[0].url.params["query"] == "Shōgun"


def test_image_url():
    assert image_url("/abc.jpg") == "https://image.tmdb.org/t/p/w342/abc.jpg"
    assert image_url(None) == ""
    assert image_url("") == ""
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_tmdb.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'job.tmdb'`

- [ ] **Step 3: Implement**

`tv-tracker/job/tmdb.py`:
```python
from collections.abc import Iterable

import httpx

from job.http import get_json

BASE = "https://api.themoviedb.org/3"
IMAGE_BASE = "https://image.tmdb.org/t/p/w342"


def image_url(path: str | None) -> str:
    return f"{IMAGE_BASE}{path}" if path else ""


class Tmdb:
    def __init__(self, token: str, transport: httpx.BaseTransport | None = None):
        self.client = httpx.Client(
            base_url=BASE,
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
            transport=transport,
        )

    def show(self, tmdb_id: int, seasons: Iterable[int] = ()) -> dict:
        parts = ["external_ids", *(f"season/{n}" for n in seasons)]
        return get_json(self.client, f"/tv/{tmdb_id}", {"append_to_response": ",".join(parts)})

    def search(self, title: str) -> list[dict]:
        return get_json(self.client, "/search/tv", {"query": title})["results"]
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_tmdb.py -q`
Expected: 4 passed

- [ ] **Step 5: Commit**

```bash
git add tv-tracker/job/tmdb.py tv-tracker/tests/test_tmdb.py
git commit -m "feat(tv-tracker): add TMDB client

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 3: TVmaze client

**Files:**
- Create: `tv-tracker/job/tvmaze.py`
- Test: `tv-tracker/tests/test_tvmaze.py`

**Interfaces:**
- Consumes: `job.http.get_json`.
- Produces: `class Tvmaze(transport: httpx.BaseTransport | None = None)` with `lookup_imdb(imdb_id: str) -> int | None` (follows TVmaze's redirect; `None` on 404) and `episodes(tvmaze_id: int) -> list[dict]`. `next_airing(episodes: list[dict], now: datetime) -> dict | None` returns the earliest episode whose `airstamp` is at or after `now`, ignoring episodes with no airstamp.

- [ ] **Step 1: Write the failing tests**

`tv-tracker/tests/test_tvmaze.py`:
```python
from datetime import UTC, datetime

import httpx

from job.tvmaze import Tvmaze, next_airing


def test_lookup_follows_redirect_to_show():
    def handler(request):
        if request.url.path == "/lookup/shows":
            assert request.url.params["imdb"] == "tt11280740"
            return httpx.Response(301, headers={"Location": "https://api.tvmaze.com/shows/44933"})
        return httpx.Response(200, json={"id": 44933})

    assert Tvmaze(transport=httpx.MockTransport(handler)).lookup_imdb("tt11280740") == 44933


def test_lookup_missing_show_returns_none():
    transport = httpx.MockTransport(lambda request: httpx.Response(404))
    assert Tvmaze(transport=transport).lookup_imdb("tt0") is None


def test_episodes():
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=[{"id": 1}]))
    assert Tvmaze(transport=transport).episodes(44933) == [{"id": 1}]


def test_next_airing_picks_earliest_future_episode():
    now = datetime(2026, 9, 27, 12, tzinfo=UTC)
    episodes = [
        {"id": 1, "airstamp": "2026-09-20T02:00:00+00:00"},
        {"id": 3, "airstamp": "2026-10-04T02:00:00+00:00"},
        {"id": 2, "airstamp": "2026-09-28T02:00:00+00:00"},
        {"id": 4, "airstamp": None},
    ]
    assert next_airing(episodes, now)["id"] == 2


def test_next_airing_none_when_nothing_upcoming():
    now = datetime(2026, 9, 27, 12, tzinfo=UTC)
    assert next_airing([{"id": 1, "airstamp": "2026-09-20T02:00:00+00:00"}], now) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_tvmaze.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'job.tvmaze'`

- [ ] **Step 3: Implement**

`tv-tracker/job/tvmaze.py`:
```python
from datetime import datetime

import httpx

from job.http import get_json

BASE = "https://api.tvmaze.com"


class Tvmaze:
    def __init__(self, transport: httpx.BaseTransport | None = None):
        self.client = httpx.Client(base_url=BASE, timeout=10, follow_redirects=True, transport=transport)

    def lookup_imdb(self, imdb_id: str) -> int | None:
        try:
            return get_json(self.client, "/lookup/shows", {"imdb": imdb_id})["id"]
        except httpx.HTTPStatusError as error:
            if error.response.status_code == 404:
                return None
            raise

    def episodes(self, tvmaze_id: int) -> list[dict]:
        return get_json(self.client, f"/shows/{tvmaze_id}/episodes")


def next_airing(episodes: list[dict], now: datetime) -> dict | None:
    upcoming = [
        (datetime.fromisoformat(e["airstamp"]), e)
        for e in episodes
        if e.get("airstamp") and datetime.fromisoformat(e["airstamp"]) >= now
    ]
    return min(upcoming, key=lambda pair: pair[0], default=(None, None))[1]
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_tvmaze.py -q`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add tv-tracker/job/tvmaze.py tv-tracker/tests/test_tvmaze.py
git commit -m "feat(tv-tracker): add TVmaze client

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 4: Prompts and the OpenAI call

**Files:**
- Create: `tv-tracker/job/prompts/suggestions.md`, `tv-tracker/job/prompts/news.md`
- Create: `tv-tracker/job/llm.py`
- Test: `tv-tracker/tests/test_llm.py`

**Interfaces:**
- Consumes: `job.config`.
- Produces:
  - Show dicts everywhere have the shape `{"tmdb_id": int, "name": str, "first_air_year": int}`. Recent news dicts are `{"show": str, "headline": str}`.
  - `suggestions_prompt(tracked: list[dict], ignored: list[dict], pending: list[dict], k: int) -> str`
  - `news_prompt(tracked: list[dict], recent: list[dict], today: date, window_days: int) -> str`
  - `SUGGESTIONS_SCHEMA`, `NEWS_SCHEMA` (dicts)
  - `@dataclass LlmResult(data: dict, sources: set[str], input_tokens: int, output_tokens: int, searches: int)`
  - `extract_sources(response) -> tuple[set[str], int]` (URLs, number of `search` actions)
  - `run(client, prompt: str, name: str, schema: dict, model: str = config.OPENAI_MODEL, effort: str = config.OPENAI_REASONING_EFFORT) -> LlmResult`

- [ ] **Step 1: Write the prompt templates**

These use `string.Template` (`$name`) so literal braces are safe.

`tv-tracker/job/prompts/suggestions.md`:
```
You recommend TV shows to a couple in Montreal who watch together.

Shows they track (they like these):
$tracked

Shows they rejected (never suggest these or close clones of them):
$ignored

Already suggested and awaiting a decision (don't repeat these):
$pending

Suggest $k show(s) they are likely to enjoy. Prefer shows currently airing or
first released in the last 2 years; at most one older "hidden gem". Use web
search to confirm each show exists and to check recent reception.

For each show give its exact title as listed on TMDB or IMDb, the year it
first aired, and one sentence on why this couple in particular would like it,
naming a specific show they track.
```

`tv-tracker/job/prompts/news.md`:
```
Today is $today. Find significant news published in the last $window days
about these TV shows:
$tracked

Significant means: renewal, cancellation, a premiere or release date
announced or changed, a trailer or teaser released, or major casting news.
Ignore reviews, recaps, rankings, listicles, and fan theories.

Already reported (don't return these, or other outlets' reports of the same
event):
$recent

If there is nothing new for a show, return nothing for it. An empty list is a
good answer. For each item give the show's tmdb_id from the list above, a
short factual headline, a one-sentence summary, the URL of the article you
found it in (the original report where possible), and the article's
publication date as YYYY-MM-DD.
```

- [ ] **Step 2: Write the failing tests**

`tv-tracker/tests/test_llm.py`:
```python
import json
from datetime import date
from types import SimpleNamespace as NS

from job import llm

SEVERANCE = {"tmdb_id": 95396, "name": "Severance", "first_air_year": 2022}
BEAR = {"tmdb_id": 136315, "name": "The Bear", "first_air_year": 2022}


def test_suggestions_prompt_fills_every_placeholder():
    prompt = llm.suggestions_prompt([SEVERANCE], [BEAR], [], 2)
    assert "- Severance (2022)" in prompt
    assert "- The Bear (2022)" in prompt
    assert "(none)" in prompt
    assert "Suggest 2 show(s)" in prompt
    assert "$" not in prompt


def test_news_prompt_includes_ids_and_recent_headlines():
    recent = [{"show": "Severance", "headline": "Severance renewed for season 3"}]
    prompt = llm.news_prompt([SEVERANCE], recent, date(2026, 9, 27), 7)
    assert "Today is 2026-09-27" in prompt
    assert "last 7 days" in prompt
    assert "- Severance (2022) [tmdb_id 95396]" in prompt
    assert "- Severance: Severance renewed for season 3" in prompt
    assert "$" not in prompt


def test_schemas_have_object_roots_and_are_strict():
    for schema, key in [(llm.SUGGESTIONS_SCHEMA, "suggestions"), (llm.NEWS_SCHEMA, "news")]:
        assert schema["type"] == "object"
        assert schema["required"] == [key]
        assert schema["additionalProperties"] is False
        item = schema["properties"][key]["items"]
        assert item["additionalProperties"] is False
        assert sorted(item["required"]) == sorted(item["properties"])


def fake_response(payload):
    return NS(
        output=[
            NS(
                type="web_search_call",
                action=NS(type="search", sources=[NS(url="https://deadline.com/a/"), NS(url="https://variety.com/b")]),
            ),
            NS(type="web_search_call", action=NS(type="open_page", url="https://deadline.com/a/")),
            NS(
                type="message",
                content=[
                    NS(
                        type="output_text",
                        annotations=[NS(type="url_citation", url="https://tvline.com/c?utm_source=chatgpt.com")],
                    )
                ],
            ),
        ],
        output_text=json.dumps(payload),
        usage=NS(input_tokens=1200, output_tokens=300),
    )


def test_extract_sources_collects_search_sources_and_citations():
    urls, searches = llm.extract_sources(fake_response({}))
    assert urls == {"https://deadline.com/a/", "https://variety.com/b", "https://tvline.com/c?utm_source=chatgpt.com"}
    assert searches == 1


def test_extract_sources_tolerates_missing_action_and_sources():
    response = NS(output=[NS(type="web_search_call"), NS(type="web_search_call", action=NS(type="search", sources=None))])
    assert llm.extract_sources(response) == (set(), 1)


def test_run_sends_web_search_and_strict_schema():
    calls = []

    def create(**kwargs):
        calls.append(kwargs)
        return fake_response({"news": []})

    client = NS(responses=NS(create=create))
    result = llm.run(client, "PROMPT", "news", llm.NEWS_SCHEMA, model="m", effort="low")

    sent = calls[0]
    assert sent["model"] == "m"
    assert sent["input"] == "PROMPT"
    assert sent["tools"] == [{"type": "web_search"}]
    assert sent["include"] == ["web_search_call.action.sources"]
    assert sent["reasoning"] == {"effort": "low"}
    assert sent["text"]["format"] == {"type": "json_schema", "name": "news", "strict": True, "schema": llm.NEWS_SCHEMA}
    assert result.data == {"news": []}
    assert (result.input_tokens, result.output_tokens, result.searches) == (1200, 300, 1)
    assert "https://variety.com/b" in result.sources
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_llm.py -q`
Expected: FAIL, `ImportError: cannot import name 'llm' from 'job'`

- [ ] **Step 4: Implement**

`tv-tracker/job/llm.py`:
```python
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from string import Template

from job import config

PROMPTS = Path(__file__).parent / "prompts"


def _array_schema(key: str, properties: dict) -> dict:
    return {
        "type": "object",
        "properties": {
            key: {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": properties,
                    "required": list(properties),
                    "additionalProperties": False,
                },
            }
        },
        "required": [key],
        "additionalProperties": False,
    }


SUGGESTIONS_SCHEMA = _array_schema(
    "suggestions",
    {"title": {"type": "string"}, "year": {"type": "integer"}, "reason": {"type": "string"}},
)
NEWS_SCHEMA = _array_schema(
    "news",
    {
        "tmdb_id": {"type": "integer"},
        "headline": {"type": "string"},
        "summary": {"type": "string"},
        "source_url": {"type": "string"},
        "published_date": {"type": "string"},
    },
)


@dataclass
class LlmResult:
    data: dict
    sources: set[str]
    input_tokens: int
    output_tokens: int
    searches: int


def _bullets(lines) -> str:
    return "\n".join(f"- {line}" for line in lines) or "(none)"


def _label(show: dict) -> str:
    return f"{show['name']} ({show['first_air_year']})"


def _template(name: str) -> Template:
    return Template((PROMPTS / f"{name}.md").read_text())


def suggestions_prompt(tracked: list[dict], ignored: list[dict], pending: list[dict], k: int) -> str:
    return _template("suggestions").substitute(
        tracked=_bullets(map(_label, tracked)),
        ignored=_bullets(map(_label, ignored)),
        pending=_bullets(map(_label, pending)),
        k=k,
    )


def news_prompt(tracked: list[dict], recent: list[dict], today: date, window_days: int) -> str:
    return _template("news").substitute(
        today=today.isoformat(),
        window=window_days,
        tracked=_bullets(f"{_label(s)} [tmdb_id {s['tmdb_id']}]" for s in tracked),
        recent=_bullets(f"{r['show']}: {r['headline']}" for r in recent),
    )


def extract_sources(response) -> tuple[set[str], int]:
    urls, searches = set(), 0
    for item in response.output:
        if item.type == "web_search_call":
            action = getattr(item, "action", None)
            if getattr(action, "type", None) == "search":
                searches += 1
                urls.update(source.url for source in getattr(action, "sources", None) or [])
        elif item.type == "message":
            for part in item.content:
                for annotation in getattr(part, "annotations", None) or []:
                    if annotation.type == "url_citation":
                        urls.add(annotation.url)
    return urls, searches


def run(
    client,
    prompt: str,
    name: str,
    schema: dict,
    model: str = config.OPENAI_MODEL,
    effort: str = config.OPENAI_REASONING_EFFORT,
) -> LlmResult:
    response = client.responses.create(
        model=model,
        reasoning={"effort": effort},
        tools=[{"type": "web_search"}],
        include=["web_search_call.action.sources"],
        input=prompt,
        text={"format": {"type": "json_schema", "name": name, "strict": True, "schema": schema}},
    )
    sources, searches = extract_sources(response)
    return LlmResult(
        data=json.loads(response.output_text),
        sources=sources,
        input_tokens=response.usage.input_tokens,
        output_tokens=response.usage.output_tokens,
        searches=searches,
    )
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_llm.py -q`
Expected: 6 passed

- [ ] **Step 6: Commit**

```bash
git add tv-tracker/job/llm.py tv-tracker/job/prompts tv-tracker/tests/test_llm.py
git commit -m "feat(tv-tracker): add suggestion/news prompts and OpenAI web-search call

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 5: Suggestion validation (confirmed against TMDB)

**Files:**
- Create: `tv-tracker/job/validate.py`
- Test: `tv-tracker/tests/test_validate.py`

**Interfaces:**
- Consumes: `job.tmdb.image_url`; a `search: Callable[[str], list[dict]]` (in practice `Tmdb.search`).
- Produces: `@dataclass Suggestion(tmdb_id: int, name: str, year: int, reason: str, poster_url: str, link: str)`; `pick_match(results: list[dict], title: str, year: int) -> dict | None`; `resolve_suggestions(raw: list[dict], search, known_ids: set[int]) -> tuple[list[Suggestion], list[str]]` (kept, drop reasons).

- [ ] **Step 1: Write the failing tests**

`tv-tracker/tests/test_validate.py`:
```python
from job.validate import pick_match, resolve_suggestions

SHOGUN_1980 = {"id": 1, "name": "Shōgun", "original_name": "Shōgun", "first_air_date": "1980-09-15", "poster_path": "/a.jpg"}
SHOGUN_2024 = {"id": 2, "name": "Shōgun", "original_name": "Shōgun", "first_air_date": "2024-02-27", "poster_path": "/b.jpg"}
OTHER = {"id": 3, "name": "Shōgun Assassin", "first_air_date": "2024-01-01"}


def test_pick_match_uses_year_not_first_result():
    assert pick_match([SHOGUN_1980, SHOGUN_2024], "Shōgun", 2024)["id"] == 2


def test_pick_match_allows_one_year_off_but_prefers_exact():
    assert pick_match([SHOGUN_2024], "shōgun", 2023)["id"] == 2
    near = {**SHOGUN_2024, "id": 9, "first_air_date": "2025-01-01"}
    assert pick_match([near, SHOGUN_2024], "Shōgun", 2024)["id"] == 2


def test_pick_match_rejects_title_mismatch_and_far_years():
    assert pick_match([OTHER], "Shōgun", 2024) is None
    assert pick_match([SHOGUN_1980], "Shōgun", 2024) is None
    assert pick_match([{"id": 4, "name": "Shōgun", "first_air_date": ""}], "Shōgun", 2024) is None


def test_pick_match_accepts_original_name():
    show = {"id": 5, "name": "Money Heist", "original_name": "La casa de papel", "first_air_date": "2017-05-02"}
    assert pick_match([show], "La Casa de Papel", 2017)["id"] == 5


def test_resolve_keeps_confirmed_and_drops_with_reasons():
    results = {"Shōgun": [SHOGUN_1980, SHOGUN_2024], "Made Up Show": []}
    raw = [
        {"title": "Shōgun", "year": 2024, "reason": "Like Severance, it's slow and tense."},
        {"title": "Made Up Show", "year": 2025, "reason": "x"},
    ]
    kept, dropped = resolve_suggestions(raw, results.__getitem__, known_ids=set())
    assert len(kept) == 1
    s = kept[0]
    assert (s.tmdb_id, s.name, s.year) == (2, "Shōgun", 2024)
    assert s.reason == "Like Severance, it's slow and tense."
    assert s.poster_url == "https://image.tmdb.org/t/p/w342/b.jpg"
    assert s.link == "https://www.themoviedb.org/tv/2"
    assert dropped == ["Made Up Show (2025): no TMDB match"]


def test_resolve_drops_known_and_in_batch_duplicates():
    raw = [
        {"title": "Shōgun", "year": 2024, "reason": "a"},
        {"title": "Shōgun", "year": 2024, "reason": "b"},
    ]
    kept, dropped = resolve_suggestions(raw, lambda title: [SHOGUN_2024], known_ids=set())
    assert [s.reason for s in kept] == ["a"]
    assert dropped == ["Shōgun (2024): already tracked, ignored or suggested"]

    kept, dropped = resolve_suggestions(raw[:1], lambda title: [SHOGUN_2024], known_ids={2})
    assert kept == []
    assert len(dropped) == 1
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_validate.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'job.validate'`

- [ ] **Step 3: Implement**

`tv-tracker/job/validate.py`:
```python
from dataclasses import dataclass

from job.tmdb import image_url


@dataclass
class Suggestion:
    tmdb_id: int
    name: str
    year: int
    reason: str
    poster_url: str
    link: str


def _year(result: dict) -> int | None:
    prefix = (result.get("first_air_date") or "")[:4]
    return int(prefix) if prefix.isdigit() else None


def _names(result: dict) -> set[str]:
    return {(result.get(key) or "").casefold().strip() for key in ("name", "original_name")}


def pick_match(results: list[dict], title: str, year: int) -> dict | None:
    wanted = title.casefold().strip()
    near = None
    for result in results:
        result_year = _year(result)
        if wanted not in _names(result) or result_year is None or abs(result_year - year) > 1:
            continue
        if result_year == year:
            return result
        near = near or result
    return near


def resolve_suggestions(raw: list[dict], search, known_ids: set[int]) -> tuple[list[Suggestion], list[str]]:
    kept, dropped, seen = [], [], set(known_ids)
    for item in raw:
        label = f"{item['title']} ({item['year']})"
        match = pick_match(search(item["title"]), item["title"], item["year"])
        if match is None:
            dropped.append(f"{label}: no TMDB match")
            continue
        if match["id"] in seen:
            dropped.append(f"{label}: already tracked, ignored or suggested")
            continue
        seen.add(match["id"])
        kept.append(
            Suggestion(
                tmdb_id=match["id"],
                name=match["name"],
                year=_year(match),
                reason=item["reason"],
                poster_url=image_url(match.get("poster_path")),
                link=f"https://www.themoviedb.org/tv/{match['id']}",
            )
        )
    return kept, dropped
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_validate.py -q`
Expected: 6 passed

- [ ] **Step 5: Commit**

```bash
git add tv-tracker/job/validate.py tv-tracker/tests/test_validate.py
git commit -m "feat(tv-tracker): resolve LLM suggestions against TMDB

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 6: News validation (cited, not confirmed)

**Files:**
- Modify: `tv-tracker/job/validate.py` (append)
- Test: `tv-tracker/tests/test_validate_news.py`

**Interfaces:**
- Consumes: a `fetch: Callable[[str], str | None]` (in practice `fetch_page`).
- Produces: `@dataclass NewsItem(tmdb_id: int, headline: str, summary: str, source_url: str, published: date)`; `normalize_url(url: str) -> str`; `published_date(html: str) -> date | None`; `fetch_page(url: str, client: httpx.Client | None = None) -> str | None`; `validate_news(raw: list[dict], sources: set[str], tracked_ids: set[int], fetch, today: date, window_days: int) -> tuple[list[NewsItem], list[str]]`.

- [ ] **Step 1: Write the failing tests**

`tv-tracker/tests/test_validate_news.py`:
```python
from datetime import date

import httpx

from job.validate import fetch_page, normalize_url, published_date, validate_news

TODAY = date(2026, 9, 27)
URL = "https://deadline.com/2026/09/severance-season-3-date/"


def item(**overrides):
    return {
        "tmdb_id": 95396,
        "headline": "Severance season 3 gets a date",
        "summary": "Apple set a January premiere.",
        "source_url": URL,
        "published_date": "2026-09-25",
    } | overrides


def page(date_html=""):
    return f"<html><head>{date_html}</head><body>story</body></html>"


def run(raw, sources=(URL,), pages=None, tracked=(95396,)):
    pages = {URL: page()} if pages is None else pages
    return validate_news(raw, set(sources), set(tracked), pages.get, TODAY, 7)


def test_normalize_url_ignores_scheme_www_slash_and_query():
    assert normalize_url("https://www.Deadline.com/a/b/?utm_source=chatgpt.com#x") == "deadline.com/a/b"
    assert normalize_url("http://deadline.com/a/b") == "deadline.com/a/b"


def test_keeps_item_whose_url_is_a_search_source():
    kept, dropped = run([item()])
    assert [n.headline for n in kept] == ["Severance season 3 gets a date"]
    assert kept[0].published == date(2026, 9, 25)
    assert dropped == []


def test_tracking_params_on_either_side_still_match():
    kept, _ = run([item()], sources=(URL + "?utm_source=chatgpt.com",))
    assert len(kept) == 1
    kept, _ = run([item(source_url=URL + "?utm_source=chatgpt.com")])
    assert len(kept) == 1


def test_drops_untracked_show_bad_scheme_and_unsourced_url():
    _, dropped = run(
        [
            item(tmdb_id=1),
            item(source_url="ftp://deadline.com/x"),
            item(source_url="https://madeup.com/story"),
        ]
    )
    assert dropped == [
        "Severance season 3 gets a date: not a tracked show",
        "Severance season 3 gets a date: not an http(s) URL",
        "Severance season 3 gets a date: URL not among search sources",
    ]


def test_drops_unreachable_page():
    kept, dropped = run([item()], pages={})
    assert kept == []
    assert dropped == ["Severance season 3 gets a date: page unreachable"]


def test_page_date_overrides_model_date():
    stale = page('<meta property="article:published_time" content="2026-08-01T10:00:00Z">')
    kept, dropped = run([item()], pages={URL: stale})
    assert kept == []
    assert dropped == ["Severance season 3 gets a date: published 2026-08-01, outside window"]

    fresh = page('<meta property="article:published_time" content="2026-09-26T10:00:00Z">')
    kept, _ = run([item(published_date="2020-01-01")], pages={URL: fresh})
    assert kept[0].published == date(2026, 9, 26)


def test_falls_back_to_model_date_and_drops_unusable_one():
    kept, _ = run([item(published_date="2026-09-01")])
    assert kept == []
    _, dropped = run([item(published_date="last week")])
    assert dropped == ["Severance season 3 gets a date: no usable publish date"]


def test_duplicate_url_kept_once():
    kept, dropped = run([item(), item(headline="Same story")])
    assert len(kept) == 1
    assert dropped == ["Same story: duplicate URL"]


def test_published_date_formats():
    assert published_date('<meta property="article:published_time" content="2026-09-25T14:00:00-04:00">') == date(2026, 9, 25)
    assert published_date('<meta content="2026-09-24" property="article:published_time">') == date(2026, 9, 24)
    assert published_date('<script type="application/ld+json">{"datePublished": "2026-09-23T08:00:00Z"}</script>') == date(2026, 9, 23)
    assert published_date('<time class="x" datetime="2026-09-22">Sept 22</time>') == date(2026, 9, 22)
    assert published_date('<meta property="article:published_time" content="soon">') is None
    assert published_date("<p>no date</p>") is None


def test_fetch_page_returns_text_on_success_and_none_otherwise():
    seen = []

    def handler(request):
        seen.append(request)
        if request.url.path == "/ok":
            return httpx.Response(200, text="<html>hi</html>")
        return httpx.Response(403)

    client = httpx.Client(transport=httpx.MockTransport(handler))
    assert fetch_page("https://x.test/ok", client) == "<html>hi</html>"
    assert fetch_page("https://x.test/blocked", client) is None
    assert "Mozilla" in seen[0].headers["user-agent"]

    def boom(request):
        raise httpx.ConnectError("down")

    assert fetch_page("https://x.test/ok", httpx.Client(transport=httpx.MockTransport(boom))) is None
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_validate_news.py -q`
Expected: FAIL, `ImportError: cannot import name 'fetch_page' from 'job.validate'`

- [ ] **Step 3: Implement (append to `validate.py`)**

Add to the imports at the top of `tv-tracker/job/validate.py`:
```python
import re
from datetime import date, timedelta
from urllib.parse import urlsplit

import httpx
```

Append:
```python
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"

DATE_PATTERNS = [
    re.compile(r"<meta[^>]+property=[\"']article:published_time[\"'][^>]+content=[\"']([^\"']+)", re.I),
    re.compile(r"<meta[^>]+content=[\"']([^\"']+)[\"'][^>]+property=[\"']article:published_time", re.I),
    re.compile(r"\"datePublished\"\s*:\s*\"([^\"]+)\""),
    re.compile(r"<time[^>]+datetime=[\"']([^\"']+)", re.I),
]


@dataclass
class NewsItem:
    tmdb_id: int
    headline: str
    summary: str
    source_url: str
    published: date


def normalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    return parts.netloc.lower().removeprefix("www.") + parts.path.rstrip("/")


def _parse_date(value: str) -> date | None:
    try:
        return date.fromisoformat(value.strip()[:10])
    except ValueError:
        return None


def published_date(html: str) -> date | None:
    for pattern in DATE_PATTERNS:
        match = pattern.search(html)
        if match and (parsed := _parse_date(match.group(1))):
            return parsed
    return None


def fetch_page(url: str, client: httpx.Client | None = None) -> str | None:
    client = client or httpx.Client(timeout=5, follow_redirects=True)
    try:
        response = client.get(url, headers={"User-Agent": USER_AGENT})
    except httpx.HTTPError:
        return None
    return response.text if response.is_success else None


def validate_news(
    raw: list[dict], sources: set[str], tracked_ids: set[int], fetch, today: date, window_days: int
) -> tuple[list[NewsItem], list[str]]:
    allowed = {normalize_url(url) for url in sources}
    cutoff = today - timedelta(days=window_days)
    kept, dropped, seen = [], [], set()

    for item in raw:
        headline, url = item["headline"], item["source_url"]
        key = normalize_url(url)
        if item["tmdb_id"] not in tracked_ids:
            dropped.append(f"{headline}: not a tracked show")
        elif not url.startswith(("http://", "https://")):
            dropped.append(f"{headline}: not an http(s) URL")
        elif key not in allowed:
            dropped.append(f"{headline}: URL not among search sources")
        elif key in seen:
            dropped.append(f"{headline}: duplicate URL")
        elif (html := fetch(url)) is None:
            dropped.append(f"{headline}: page unreachable")
        elif (published := published_date(html) or _parse_date(item["published_date"])) is None:
            dropped.append(f"{headline}: no usable publish date")
        elif published < cutoff:
            dropped.append(f"{headline}: published {published.isoformat()}, outside window")
        else:
            seen.add(key)
            kept.append(NewsItem(item["tmdb_id"], headline, item["summary"], url, published))
    return kept, dropped
```

- [ ] **Step 4: Run to verify pass**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests -q`
Expected: all pass (10 new in `test_validate_news.py`)

- [ ] **Step 5: Commit**

```bash
git add tv-tracker/job/validate.py tv-tracker/tests/test_validate_news.py
git commit -m "feat(tv-tracker): validate LLM news against search sources and page dates

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 7: Dry-run CLI

**Files:**
- Create: `tv-tracker/job/__main__.py`
- Create: `tv-tracker/shows.example.json`
- Test: `tv-tracker/tests/test_main.py`

**Interfaces:**
- Consumes: everything above.
- Produces: `main(argv: list[str] | None = None) -> None`; `run_suggestions(shows: dict, client, search) -> tuple[LlmResult, list[Suggestion], list[str]] | None`; `run_news(shows: dict, client, fetch, today: date) -> tuple[LlmResult, list[NewsItem], list[str]] | None`. The shows file has the shape `{"tracked": [show], "ignored": [show], "pending": [show], "recent_news": [{"show", "headline"}]}`, where only `tracked` is required.

- [ ] **Step 1: Write the example input**

`tv-tracker/shows.example.json` (IDs to be confirmed by the dry run's facts output in Task 8):
```json
{
  "tracked": [
    {"tmdb_id": 95396, "name": "Severance", "first_air_year": 2022},
    {"tmdb_id": 136315, "name": "The Bear", "first_air_year": 2022},
    {"tmdb_id": 107113, "name": "Only Murders in the Building", "first_air_year": 2021}
  ],
  "ignored": [],
  "pending": [],
  "recent_news": []
}
```

- [ ] **Step 2: Write the failing tests**

`tv-tracker/tests/test_main.py`:
```python
import json
from datetime import date
from types import SimpleNamespace as NS

import pytest

from job.__main__ import main, run_news, run_suggestions

SEVERANCE = {"tmdb_id": 95396, "name": "Severance", "first_air_year": 2022}


def client_returning(payload, calls):
    def create(**kwargs):
        calls.append(kwargs)
        return NS(output=[], output_text=json.dumps(payload), usage=NS(input_tokens=1, output_tokens=1))

    return NS(responses=NS(create=create))


def test_requires_dry_run_flag():
    with pytest.raises(SystemExit):
        main([])


def test_news_skipped_when_nothing_tracked():
    assert run_news({"tracked": []}, client=None, fetch=None, today=date(2026, 9, 27)) is None


def test_suggestions_skipped_when_queue_full():
    shows = {"tracked": [SEVERANCE], "pending": [SEVERANCE] * 3}
    assert run_suggestions(shows, client=None, search=None) is None


def test_suggestions_ask_for_remaining_slots_and_treat_all_lists_as_known():
    calls = []
    shows = {
        "tracked": [SEVERANCE],
        "ignored": [{"tmdb_id": 7, "name": "X", "first_air_year": 2020}],
        "pending": [{"tmdb_id": 8, "name": "Y", "first_air_year": 2021}],
    }
    payload = {"suggestions": [{"title": "X", "year": 2020, "reason": "r"}]}
    x_result = [{"id": 7, "name": "X", "first_air_date": "2020-01-01"}]
    result, kept, dropped = run_suggestions(shows, client_returning(payload, calls), lambda title: x_result)
    assert "Suggest 2 show(s)" in calls[0]["input"]
    assert kept == []
    assert dropped == ["X (2020): already tracked, ignored or suggested"]


def test_news_validates_against_tracked_ids():
    calls = []
    payload = {"news": [{"tmdb_id": 1, "headline": "h", "summary": "s", "source_url": "https://a.com/x", "published_date": "2026-09-26"}]}
    result, kept, dropped = run_news({"tracked": [SEVERANCE]}, client_returning(payload, calls), lambda url: "", date(2026, 9, 27))
    assert kept == []
    assert dropped == ["h: not a tracked show"]
```

- [ ] **Step 3: Run to verify failure**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests/test_main.py -q`
Expected: FAIL, `ModuleNotFoundError: No module named 'job.__main__'`

- [ ] **Step 4: Implement**

`tv-tracker/job/__main__.py`:
```python
import argparse
import json
from datetime import date, datetime
from pathlib import Path

from job import config, llm, validate
from job.tmdb import Tmdb
from job.tvmaze import Tvmaze, next_airing


def run_suggestions(shows: dict, client, search):
    pending = shows.get("pending", [])
    k = config.MAX_PENDING_SUGGESTIONS - len(pending)
    if k <= 0:
        return None
    prompt = llm.suggestions_prompt(shows["tracked"], shows.get("ignored", []), pending, k)
    result = llm.run(client, prompt, "suggestions", llm.SUGGESTIONS_SCHEMA)
    known = {s["tmdb_id"] for key in ("tracked", "ignored", "pending") for s in shows.get(key, [])}
    kept, dropped = validate.resolve_suggestions(result.data["suggestions"], search, known)
    return result, kept, dropped


def run_news(shows: dict, client, fetch, today: date):
    tracked = shows["tracked"]
    if not tracked:
        return None
    prompt = llm.news_prompt(tracked, shows.get("recent_news", []), today, config.NEWS_WINDOW_DAYS)
    result = llm.run(client, prompt, "news", llm.NEWS_SCHEMA)
    tracked_ids = {s["tmdb_id"] for s in tracked}
    kept, dropped = validate.validate_news(
        result.data["news"], result.sources, tracked_ids, fetch, today, config.NEWS_WINDOW_DAYS
    )
    return result, kept, dropped


def print_facts(tracked: list[dict], tmdb: Tmdb, tvmaze: Tvmaze, now: datetime) -> None:
    print("== Facts (TMDB + TVmaze) ==")
    for show in tracked:
        try:
            data = tmdb.show(show["tmdb_id"])
            imdb_id = data["external_ids"].get("imdb_id")
            tvmaze_id = tvmaze.lookup_imdb(imdb_id) if imdb_id else None
            upcoming = next_airing(tvmaze.episodes(tvmaze_id), now) if tvmaze_id else None
            next_tmdb = data.get("next_episode_to_air") or {}
            print(f"- {data['name']} (tmdb {show['tmdb_id']}, imdb {imdb_id}, tvmaze {tvmaze_id})")
            print(f"    seasons: {data.get('number_of_seasons')}, status: {data.get('status')}")
            print(f"    TMDB next: {next_tmdb.get('air_date')} {next_tmdb.get('name') or ''}")
            print(f"    TVmaze next: {upcoming['airstamp'] if upcoming else None}")
        except Exception as error:
            print(f"- {show['name']}: FAILED ({error!r})")


def print_usage(result: llm.LlmResult) -> None:
    print(f"  [tokens in/out {result.input_tokens}/{result.output_tokens}, web searches {result.searches}]")


def print_dropped(dropped: list[str]) -> None:
    for reason in dropped:
        print(f"  dropped: {reason}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="job")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--shows", type=Path, default=Path("shows.example.json"))
    parser.add_argument("--skip", action="append", choices=["facts", "suggestions", "news"], default=[])
    args = parser.parse_args(argv)
    if not args.dry_run:
        parser.error("only --dry-run exists until the Sheet is wired up (Plan 2)")

    from openai import OpenAI

    shows = json.loads(args.shows.read_text())
    now = datetime.now(config.TZ)
    tmdb = Tmdb(config.tmdb_token())
    client = OpenAI()
    print(f"model {config.OPENAI_MODEL}, effort {config.OPENAI_REASONING_EFFORT}, {now:%Y-%m-%d %H:%M %Z}\n")

    if "facts" not in args.skip:
        print_facts(shows["tracked"], tmdb, Tvmaze(), now)

    if "suggestions" not in args.skip:
        print("\n== Suggestions ==")
        outcome = run_suggestions(shows, client, tmdb.search)
        if outcome is None:
            print("  skipped: pending queue full")
        else:
            result, kept, dropped = outcome
            for s in kept:
                print(f"- {s.name} ({s.year}) tmdb {s.tmdb_id}\n    {s.reason}\n    {s.link}")
            print_dropped(dropped)
            print_usage(result)

    if "news" not in args.skip:
        print("\n== News ==")
        outcome = run_news(shows, client, validate.fetch_page, now.date())
        if outcome is None:
            print("  skipped: nothing tracked")
        else:
            result, kept, dropped = outcome
            names = {s["tmdb_id"]: s["name"] for s in shows["tracked"]}
            for n in kept:
                print(f"- [{names[n.tmdb_id]}] {n.headline} ({n.published})\n    {n.summary}\n    {n.source_url}")
            print_dropped(dropped)
            print(f"  sources returned by search: {len(result.sources)}")
            print_usage(result)


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Run to verify pass**

Run: `uv run --group tv-tracker python -m pytest tv-tracker/tests -q`
Expected: all pass

- [ ] **Step 6: Lint**

Run: `uvx ruff format tv-tracker && uvx ruff check tv-tracker`
Expected: no errors (fix any that appear, re-run tests)

- [ ] **Step 7: Commit**

```bash
git add tv-tracker/job/__main__.py tv-tracker/shows.example.json tv-tracker/tests/test_main.py
git commit -m "feat(tv-tracker): add --dry-run printing facts, suggestions and news

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

---

### Task 8: Live dry run and prompt iteration (needs Nick)

**Files:**
- Create: `tv-tracker/shows.json` (Nick's real shows, committed; not secret)
- Create: `posts/tv_tracker/notes/BUILD_NOTES.md`
- Modify: `tv-tracker/job/prompts/*.md` (only if the runs show problems)

**Interfaces:**
- Consumes: the CLI from Task 7.
- Produces: tuned prompts and a written go/no-go for Plan 2.

- [ ] **Step 1: Nick creates credentials** (manual)

- TMDB: themoviedb.org → Settings → API → copy the **API Read Access Token**.
- OpenAI: platform.openai.com → API keys → create a key; add a few dollars of credit.
- Write `tv-tracker/.env`:
```
TMDB_TOKEN=...
OPENAI_API_KEY=...
```

- [ ] **Step 2: First run with the example list**

Run (from `tv-tracker/`): `uv run --group tv-tracker --env-file .env python -m job --dry-run`
Expected: a Facts section with the right show names and a TVmaze id for each; suggestions that resolve; news items or an honest empty list; token/search counts. If a Facts name is wrong, fix the ID in `shows.example.json`.

- [ ] **Step 3: Nick writes `tv-tracker/shows.json`** with the shows you actually track (IDs via themoviedb.org URLs), and some `ignored` shows you'd never watch to test that exclusion.

- [ ] **Step 4: Run on 3 separate days** with `--shows shows.json`. After each run, copy that day's kept news headlines into `recent_news` so the next run tests dedupe. Record in `posts/tv_tracker/notes/BUILD_NOTES.md`:
  - Suggestions: how many resolved, how many dropped and why, would you actually watch them?
  - News: kept vs dropped (by reason), any reviews/recaps that got through, any repeats of `recent_news`, anything real that was missed.
  - Cost: tokens and searches per run (check the OpenAI usage dashboard for the dollar amount).

- [ ] **Step 5: Adjust prompts only for observed problems**, re-run, and note what changed and why in BUILD_NOTES. Typical fixes: tighten "significant" wording, raise `OPENAI_REASONING_EFFORT` to `medium` if results are shallow.

- [ ] **Step 6: Commit**

```bash
git add tv-tracker/shows.json tv-tracker/job/prompts posts/tv_tracker/notes/BUILD_NOTES.md
git commit -m "docs(tv-tracker): record dry-run findings and prompt tuning

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- [ ] **Step 7: Go/no-go.** If suggestions are mostly good and news is mostly real, well dated and non-repeating, proceed to Plan 2. Otherwise decide with Nick whether to change the approach (e.g. news from a curated RSS list instead of web search).
