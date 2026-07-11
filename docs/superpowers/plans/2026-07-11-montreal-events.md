# Montreal Events Guide Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A self-updating Montreal events page on the site, fed from a Google Doc by an in-session Claude Code skill that extracts JSON, checks links, syncs a Google Calendar, and commits — plus a blog post about the build.

**Architecture:** Root-level `montreal_events/` Python package holds the deterministic pipeline (fetch, validate, link-check); the `/update-montreal-events` project skill orchestrates it and performs the two LLM/MCP steps (doc-text→JSON extraction, Google Calendar sync) in-session. The public page is vanilla HTML/CSS/JS reading committed `events.json`; the blog post is a Quarto `.qmd` written from accumulated build notes.

**Tech Stack:** Python ≥3.12 via `uv` (httpx, jsonschema, pytest), vanilla JS/HTML/CSS (no build step), Quarto, Google Calendar MCP (in-session only).

**Spec:** `docs/superpowers/specs/2026-07-11-montreal-events-design.md`

## Global Constraints

- Python `>=3.12`; all Python runs via `uv run --group montreal ...` from the **repo root**.
- New dependency group only — do not touch base `dependencies`: `montreal = ["httpx>=0.28.1", "jsonschema>=4.25.0", "pytest>=9.1.1"]`.
- The page must be self-contained vanilla HTML/CSS/JS: no CDNs, no frameworks, no build step; all assets inline to `posts/montreal_events/events/`.
- **No Anthropic API calls anywhere in code.** LLM extraction and calendar sync happen inside the Claude Code session, driven by `SKILL.md`.
- Google Doc ID (verbatim): `15o4_PIve4R0K3Wgle58lUCxQwmDLBCiMn6f4M0FVOV4`
- Target Google Calendar ID (verbatim): `6c17201ccbff261d301195c10de875890b7935fb87a63484cbf0a831ff8f25cc@group.calendar.google.com`
- Calendar embed URL (for the page header link): `https://calendar.google.com/calendar/embed?src=6c17201ccbff261d301195c10de875890b7935fb87a63484cbf0a831ff8f25cc%40group.calendar.google.com&ctz=America%2FToronto`
- `montreal_events/calendar_map.json` must never move under `posts/` (it holds private calendar event IDs and must not be served).
- Commit style: `feat(montreal): ...` for pipeline/skill, `site:` for `_quarto.yml`, `post(montreal): ...` for the post/page content. End every commit message with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Tasks 6 and 7 require the live Google Doc and the Google Calendar MCP connector — they must run in the main session (not a subagent), since subagents may lack the authenticated MCP connection.

---

### Task 1: Scaffolding + JSON Schema

**Files:**
- Modify: `pyproject.toml` (add dependency group)
- Create: `montreal_events/__init__.py` (empty)
- Create: `montreal_events/tests/__init__.py` (empty)
- Create: `montreal_events/events.schema.json`
- Test: `montreal_events/tests/test_schema.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `montreal_events/events.schema.json` — Draft 2020-12 schema used by `validate.py` (Task 2). Category enum: `festival, music, museum, sports, board-games, trivia, escape-room, hike, market, other`. Status enum: `date-specific, recurring, evergreen, lead`.

- [ ] **Step 1: Add the dependency group**

In `pyproject.toml`, append to the `[dependency-groups]` table (keep existing groups untouched):

```toml
montreal = [
    "httpx>=0.28.1",
    "jsonschema>=4.25.0",
    "pytest>=9.1.1",
]
```

- [ ] **Step 2: Create package dirs**

```bash
mkdir -p montreal_events/tests
touch montreal_events/__init__.py montreal_events/tests/__init__.py
```

- [ ] **Step 3: Write the failing test**

Create `montreal_events/tests/test_schema.py`:

```python
import json
from pathlib import Path

from jsonschema.validators import Draft202012Validator

SCHEMA_PATH = Path(__file__).parent.parent / "events.schema.json"


def test_schema_is_valid_jsonschema():
    schema = json.loads(SCHEMA_PATH.read_text())
    Draft202012Validator.check_schema(schema)


def test_schema_accepts_minimal_valid_document():
    schema = json.loads(SCHEMA_PATH.read_text())
    doc = {
        "last_updated": "2026-07-11",
        "source_doc": "https://docs.google.com/document/d/x/",
        "events": [{
            "id": "nuits-dafrique-2026",
            "title": "Nuits d'Afrique",
            "category": "festival",
            "status": "date-specific",
            "start_date": "2026-07-07",
            "end_date": "2026-07-19",
            "location": "Quartier des spectacles",
            "url": "https://festivalnuitsdafrique.com/",
            "url_ok": None,
            "description": "World-music festival downtown.",
        }],
    }
    assert list(Draft202012Validator(schema).iter_errors(doc)) == []


def test_schema_rejects_bad_category_and_extra_key():
    schema = json.loads(SCHEMA_PATH.read_text())
    doc = {
        "last_updated": "2026-07-11",
        "source_doc": "x",
        "events": [{
            "id": "a", "title": "A", "category": "nightclub",
            "status": "evergreen", "start_date": None, "end_date": None,
            "location": None, "url": None, "url_ok": None,
            "description": "d", "surprise": 1,
        }],
    }
    errors = list(Draft202012Validator(schema).iter_errors(doc))
    assert len(errors) >= 2  # bad enum + additionalProperties
```

- [ ] **Step 4: Run test to verify it fails**

Run: `uv run --group montreal pytest montreal_events/tests/test_schema.py -v`
Expected: FAIL (`FileNotFoundError` — schema file doesn't exist yet)

- [ ] **Step 5: Write the schema**

Create `montreal_events/events.schema.json`:

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "Montreal events data",
  "type": "object",
  "required": ["last_updated", "source_doc", "events"],
  "additionalProperties": false,
  "properties": {
    "last_updated": { "type": "string", "pattern": "^\\d{4}-\\d{2}-\\d{2}$" },
    "source_doc": { "type": "string", "minLength": 1 },
    "events": { "type": "array", "items": { "$ref": "#/$defs/event" } }
  },
  "$defs": {
    "event": {
      "type": "object",
      "required": [
        "id", "title", "category", "status", "start_date", "end_date",
        "location", "url", "url_ok", "description"
      ],
      "additionalProperties": false,
      "properties": {
        "id": { "type": "string", "pattern": "^[a-z0-9]+(-[a-z0-9]+)*$" },
        "title": { "type": "string", "minLength": 1 },
        "category": {
          "enum": ["festival", "music", "museum", "sports", "board-games",
                   "trivia", "escape-room", "hike", "market", "other"]
        },
        "status": { "enum": ["date-specific", "recurring", "evergreen", "lead"] },
        "start_date": { "type": ["string", "null"], "pattern": "^\\d{4}-\\d{2}-\\d{2}$" },
        "end_date": { "type": ["string", "null"], "pattern": "^\\d{4}-\\d{2}-\\d{2}$" },
        "location": { "type": ["string", "null"] },
        "url": { "type": ["string", "null"], "pattern": "^https?://" },
        "url_ok": { "type": ["boolean", "null"] },
        "description": { "type": "string", "minLength": 1 },
        "notes": { "type": ["string", "null"] }
      }
    }
  }
}
```

(Note: `pattern`/`minLength` on a `["string","null"]` type only constrains string values — `null` passes. That's intended.)

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run --group montreal pytest montreal_events/tests/test_schema.py -v`
Expected: 3 PASS

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml uv.lock montreal_events/
git commit -m "feat(montreal): scaffolding + events JSON schema

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: validate.py

**Files:**
- Create: `montreal_events/validate.py`
- Test: `montreal_events/tests/test_validate.py`

**Interfaces:**
- Consumes: `montreal_events/events.schema.json` (Task 1).
- Produces: `validate_events(data: dict, today: datetime.date) -> list[str]` (empty list = valid) and a CLI: `uv run --group montreal python -m montreal_events.validate posts/montreal_events/events/events.json` — prints errors, exit code 1 on any error, prints `OK (<n> events)` and exits 0 when clean. Task 5's SKILL.md and Task 6 call this CLI.

- [ ] **Step 1: Write the failing tests**

Create `montreal_events/tests/test_validate.py`:

```python
import datetime

from montreal_events.validate import validate_events

TODAY = datetime.date(2026, 7, 11)


def make_doc(**event_overrides):
    event = {
        "id": "nuits-dafrique-2026",
        "title": "Nuits d'Afrique",
        "category": "festival",
        "status": "date-specific",
        "start_date": "2026-07-07",
        "end_date": "2026-07-19",
        "location": "Quartier des spectacles",
        "url": "https://festivalnuitsdafrique.com/",
        "url_ok": None,
        "description": "World-music festival downtown.",
    }
    event.update(event_overrides)
    return {
        "last_updated": "2026-07-11",
        "source_doc": "https://docs.google.com/document/d/x/",
        "events": [event],
    }


def test_valid_document_has_no_errors():
    assert validate_events(make_doc(), TODAY) == []


def test_schema_violation_reported():
    errors = validate_events(make_doc(category="nightclub"), TODAY)
    assert len(errors) == 1
    assert "nightclub" in errors[0]


def test_expired_date_specific_event_rejected():
    errors = validate_events(make_doc(end_date="2026-07-01"), TODAY)
    assert any("expired" in e for e in errors)


def test_start_after_end_rejected():
    errors = validate_events(
        make_doc(start_date="2026-07-20", end_date="2026-07-19"), TODAY
    )
    assert any("start_date after end_date" in e for e in errors)


def test_invalid_calendar_date_rejected():
    errors = validate_events(make_doc(start_date="2026-02-31"), TODAY)
    assert any("not a valid date" in e for e in errors)


def test_duplicate_ids_rejected():
    doc = make_doc()
    doc["events"].append(dict(doc["events"][0]))
    errors = validate_events(doc, TODAY)
    assert any("duplicate id" in e for e in errors)


def test_stale_last_updated_rejected():
    doc = make_doc()
    doc["last_updated"] = "2026-07-01"
    errors = validate_events(doc, TODAY)
    assert any("last_updated" in e for e in errors)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --group montreal pytest montreal_events/tests/test_validate.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'montreal_events.validate'`

- [ ] **Step 3: Implement validate.py**

Create `montreal_events/validate.py`:

```python
"""Schema + sanity validation for events.json. Gate between LLM extraction and commit."""

import datetime
import json
import sys
from pathlib import Path

from jsonschema.validators import Draft202012Validator

SCHEMA_PATH = Path(__file__).parent / "events.schema.json"


def _parse_date(value, field, event_id, errors):
    if value is None:
        return None
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        errors.append(f"{event_id}: {field} {value!r} is not a valid date")
        return None


def validate_events(data: dict, today: datetime.date) -> list[str]:
    schema = json.loads(SCHEMA_PATH.read_text())
    errors = [
        f"schema: {e.json_path}: {e.message}"
        for e in Draft202012Validator(schema).iter_errors(data)
    ]
    if errors:
        return errors  # semantic checks assume structural validity

    if data["last_updated"] != today.isoformat():
        errors.append(
            f"last_updated is {data['last_updated']}, expected {today.isoformat()}"
        )

    seen = set()
    for ev in data["events"]:
        eid = ev["id"]
        if eid in seen:
            errors.append(f"duplicate id: {eid}")
        seen.add(eid)

        start = _parse_date(ev["start_date"], "start_date", eid, errors)
        end = _parse_date(ev["end_date"], "end_date", eid, errors)
        if start and end and start > end:
            errors.append(f"{eid}: start_date after end_date")
        if ev["status"] == "date-specific" and end and end < today:
            errors.append(f"{eid}: expired (ended {end.isoformat()})")

    return errors


def main() -> int:
    path = Path(sys.argv[1])
    data = json.loads(path.read_text())
    errors = validate_events(data, datetime.date.today())
    for e in errors:
        print(f"ERROR: {e}")
    if errors:
        return 1
    print(f"OK ({len(data['events'])} events)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --group montreal pytest montreal_events/tests/test_validate.py -v`
Expected: 7 PASS

- [ ] **Step 5: Commit**

```bash
git add montreal_events/validate.py montreal_events/tests/test_validate.py
git commit -m "feat(montreal): schema + sanity validator for events.json

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: fetch_doc.py

**Files:**
- Create: `montreal_events/fetch_doc.py`
- Test: `montreal_events/tests/test_fetch_doc.py`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces: `fetch_text(client: httpx.Client) -> str` and CLI `uv run --group montreal python -m montreal_events.fetch_doc` printing the doc text to stdout (exit 1 with stderr message on failure). Used by SKILL.md (Task 5).

- [ ] **Step 1: Write the failing tests**

Create `montreal_events/tests/test_fetch_doc.py`:

```python
import httpx
import pytest

from montreal_events.fetch_doc import EXPORT_URL, fetch_text

LONG_TEXT = "Montreal Clubs & Events\n" + ("x" * 600)


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_returns_body():
    def handler(request):
        assert str(request.url) == EXPORT_URL
        return httpx.Response(200, text=LONG_TEXT)

    assert fetch_text(_client(handler)) == LONG_TEXT


def test_fetch_raises_on_http_error():
    def handler(request):
        return httpx.Response(404)

    with pytest.raises(httpx.HTTPStatusError):
        fetch_text(_client(handler))


def test_fetch_raises_on_suspiciously_short_body():
    def handler(request):
        return httpx.Response(200, text="Sign in required")

    with pytest.raises(ValueError, match="short"):
        fetch_text(_client(handler))
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --group montreal pytest montreal_events/tests/test_fetch_doc.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'montreal_events.fetch_doc'`

- [ ] **Step 3: Implement fetch_doc.py**

Create `montreal_events/fetch_doc.py`:

```python
"""Fetch the Montreal events Google Doc as plain text via its public export URL."""

import sys

import httpx

DOC_ID = "15o4_PIve4R0K3Wgle58lUCxQwmDLBCiMn6f4M0FVOV4"
EXPORT_URL = f"https://docs.google.com/document/d/{DOC_ID}/export?format=txt"
MIN_LENGTH = 500  # a real doc is thousands of chars; short bodies mean auth/error pages


def fetch_text(client: httpx.Client) -> str:
    response = client.get(EXPORT_URL, follow_redirects=True)
    response.raise_for_status()
    text = response.text
    if len(text.strip()) < MIN_LENGTH:
        raise ValueError(
            f"export body suspiciously short ({len(text)} chars) — "
            "doc may no longer be link-shared"
        )
    return text


def main() -> int:
    try:
        with httpx.Client(timeout=30) as client:
            print(fetch_text(client))
    except (httpx.HTTPError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --group montreal pytest montreal_events/tests/test_fetch_doc.py -v`
Expected: 3 PASS

- [ ] **Step 5: Live smoke test**

Run: `uv run --group montreal python -m montreal_events.fetch_doc | head -3`
Expected: first lines of the doc, starting with `Montreal Clubs & Events` (exit code 0)

- [ ] **Step 6: Commit**

```bash
git add montreal_events/fetch_doc.py montreal_events/tests/test_fetch_doc.py
git commit -m "feat(montreal): fetch Google Doc via public export URL

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: check_links.py

**Files:**
- Create: `montreal_events/check_links.py`
- Test: `montreal_events/tests/test_check_links.py`

**Interfaces:**
- Consumes: `events.json` shape from Task 1's schema.
- Produces: `check_url(client: httpx.Client, url: str) -> bool | None` and `apply_link_checks(data: dict, client: httpx.Client) -> list[str]` (mutates `url_ok` in place, returns list of dead URLs). CLI: `uv run --group montreal python -m montreal_events.check_links posts/montreal_events/events/events.json` — rewrites the file (2-space indent, trailing newline), prints dead links, always exits 0 (advisory only, per spec).

- [ ] **Step 1: Write the failing tests**

Create `montreal_events/tests/test_check_links.py`:

```python
import httpx

from montreal_events.check_links import apply_link_checks, check_url


def _client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_ok_url_returns_true():
    client = _client(lambda request: httpx.Response(200))
    assert check_url(client, "https://example.com/") is True


def test_404_returns_false():
    client = _client(lambda request: httpx.Response(404))
    assert check_url(client, "https://example.com/gone") is False


def test_head_rejected_falls_back_to_get():
    def handler(request):
        if request.method == "HEAD":
            return httpx.Response(405)
        return httpx.Response(200)

    assert check_url(_client(handler), "https://example.com/") is True


def test_network_error_returns_none():
    def handler(request):
        raise httpx.ConnectTimeout("boom")

    assert check_url(_client(handler), "https://example.com/") is None


def test_apply_link_checks_sets_flags_and_dedupes():
    calls = []

    def handler(request):
        calls.append(str(request.url))
        return httpx.Response(404 if "dead" in str(request.url) else 200)

    data = {"events": [
        {"id": "a", "url": "https://ok.example/", "url_ok": None},
        {"id": "b", "url": "https://ok.example/", "url_ok": None},
        {"id": "c", "url": "https://dead.example/", "url_ok": None},
        {"id": "d", "url": None, "url_ok": None},
    ]}
    dead = apply_link_checks(data, _client(handler))
    assert [e["url_ok"] for e in data["events"]] == [True, True, False, None]
    assert dead == ["https://dead.example/"]
    assert len(set(calls)) == len(calls) == 2  # each distinct URL hit once
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --group montreal pytest montreal_events/tests/test_check_links.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'montreal_events.check_links'`

- [ ] **Step 3: Implement check_links.py**

Create `montreal_events/check_links.py`:

```python
"""Advisory link health sweep over events.json. Sets url_ok; never fails the run."""

import json
import sys
from pathlib import Path

import httpx

TIMEOUT = 10
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; nicholastacik.github.io link check)"}


def check_url(client: httpx.Client, url: str) -> bool | None:
    try:
        response = client.head(url, follow_redirects=True, timeout=TIMEOUT)
        if response.status_code >= 400:
            # many sites reject HEAD (405) or bot-block it; retry with GET
            response = client.get(url, follow_redirects=True, timeout=TIMEOUT)
        return response.status_code < 400
    except httpx.HTTPError:
        return None  # inconclusive, not confirmed dead


def apply_link_checks(data: dict, client: httpx.Client) -> list[str]:
    urls = {e["url"] for e in data["events"] if e["url"]}
    results = {url: check_url(client, url) for url in sorted(urls)}
    for event in data["events"]:
        event["url_ok"] = results[event["url"]] if event["url"] else None
    return [url for url, ok in results.items() if ok is False]


def main() -> int:
    path = Path(sys.argv[1])
    data = json.loads(path.read_text())
    with httpx.Client(headers=HEADERS) as client:
        dead = apply_link_checks(data, client)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    for url in dead:
        print(f"DEAD LINK: {url}")
    print(f"checked {len({e['url'] for e in data['events'] if e['url']})} urls, "
          f"{len(dead)} dead")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --group montreal pytest montreal_events/tests/ -v`
Expected: all tests PASS (schema 3, validate 7, fetch 3, links 5)

- [ ] **Step 5: Commit**

```bash
git add montreal_events/check_links.py montreal_events/tests/test_check_links.py
git commit -m "feat(montreal): advisory link checker for events.json

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: The skill (SKILL.md v1) + notes scaffold

**Files:**
- Create: `.claude/skills/update-montreal-events/SKILL.md`
- Create: `posts/montreal_events/notes/BUILD_NOTES.md`
- Modify: `_quarto.yml` (exclude notes from render — the `render:` list, after the jeopardy exclusions)

**Interfaces:**
- Consumes: CLIs from Tasks 2–4 (exact commands embedded below).
- Produces: the `/update-montreal-events` skill, minus calendar sync (added in Task 7). Task 6 executes it.

- [ ] **Step 1: Create the notes scaffold**

Create `posts/montreal_events/notes/BUILD_NOTES.md`:

```markdown
# Montreal Events — build & run notes

Raw material for the blog post (posts/montreal_events/index.qmd).
Build phases append decisions/surprises; each skill run appends a changelog.

## Build log

### 2026-07-11 — design
- Doc is publicly exportable (`export?format=txt`) — no Google auth anywhere.
- Chose in-session skill over GitHub Action + API key: $0, no secrets.
- LLM extraction gated by a jsonschema validator; deterministic steps in Python.
- Calendar sync via Google Calendar MCP; sync state kept out of the served dir.

## Run log
```

- [ ] **Step 2: Exclude notes from Quarto render**

In `_quarto.yml`, in the `project.render` list, add after `- "!posts/jeopardy_ds/notes/"`:

```yaml
    - "!posts/montreal_events/notes/"
```

- [ ] **Step 3: Write SKILL.md**

Create `.claude/skills/update-montreal-events/SKILL.md`:

````markdown
---
name: update-montreal-events
description: Refresh the Montreal events page from the Google Doc — fetch, extract to JSON, validate, check links, sync Google Calendar, commit. Run weekly (doc updates Thursdays).
---

# Update Montreal Events

Refresh `posts/montreal_events/events/events.json` from the "Montreal Clubs &
Events" Google Doc. Run every step from the repo root, in order. If any step
below says ABORT, stop without committing and report why.

## 1. Fetch the doc

```bash
uv run --group montreal python -m montreal_events.fetch_doc > /tmp/montreal_doc.txt
```

Non-zero exit → ABORT. Read `/tmp/montreal_doc.txt`.

## 2. Extract to JSON (you do this)

Read the current `posts/montreal_events/events/events.json` (if it exists),
then write a fresh version extracted from the doc text. Follow
`montreal_events/events.schema.json` exactly. Rules:

- One entry per distinct event/venue/activity in the doc.
- `id`: stable kebab-case slug; include the year for annual events
  (e.g. `osheaga-2026`). Reuse the same id as the previous file for the same
  event — ids are the calendar-sync key.
- `category`: one of `festival, music, museum, sports, board-games, trivia,
  escape-room, hike, market, other`.
- `status`: `date-specific` (has an end date to act on), `recurring`
  (schedule repeats), `evergreen` (always available), `lead` (the doc says
  verify/unconfirmed — trivia leads, volleyball leads, watch items).
- **Drop** date-specific events whose end date has already passed.
- `description`: 1–2 sentences, neutral tone. **Strip all personal framing**
  (no names, "couple", neighborhood references, personal habits).
- `notes`: caveats worth showing publicly ("Verify English shows before
  booking"), else omit or null.
- Carry over each event's `url_ok` from the previous file (new events: null);
  step 4 refreshes them.
- Set `last_updated` to today (ISO date) and keep `source_doc` as the doc URL.

## 3. Validate — the gate

```bash
uv run --group montreal python -m montreal_events.validate posts/montreal_events/events/events.json
```

Exit 1 → fix your extraction and re-run. Still failing after 3 attempts →
ABORT (restore the previous events.json via `git checkout`).

## 4. Check links

```bash
uv run --group montreal python -m montreal_events.check_links posts/montreal_events/events/events.json
```

Always exits 0. Note any `DEAD LINK:` lines for the run log and final report.

## 5. Sync Google Calendar

(Added in phase 2 — skip if this section is the placeholder.)

## 6. Record the run + commit

Append to `posts/montreal_events/notes/BUILD_NOTES.md` under `## Run log`:

```markdown
### <today> — skill run
- Added: <new event ids, or "none">
- Removed: <dropped event ids (expired/gone), or "none">
- Changed: <events whose dates/details changed, or "none">
- Dead links: <urls, or "none">
- Calendar: <created/updated/skipped counts, or "not yet enabled">
```

Then:

```bash
git add posts/montreal_events/events/events.json montreal_events/calendar_map.json posts/montreal_events/notes/BUILD_NOTES.md
git commit -m "data(montreal): weekly events refresh <today>

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push
```

Finish by telling the user: counts (total / added / removed), dead links
found, and calendar actions taken.
````

- [ ] **Step 4: Verify the skill is discoverable**

Run: `ls .claude/skills/update-montreal-events/SKILL.md && head -5 .claude/skills/update-montreal-events/SKILL.md`
Expected: file exists; frontmatter shows `name: update-montreal-events`

- [ ] **Step 5: Commit**

```bash
git add .claude/skills/update-montreal-events/ posts/montreal_events/notes/ _quarto.yml
git commit -m "feat(montreal): /update-montreal-events skill v1 + build notes scaffold

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 6: First real run (produces events.json)

**⚠ Main session only** — the extraction is LLM work driven by SKILL.md.

**Files:**
- Create: `posts/montreal_events/events/events.json` (extracted from the live doc)
- Modify: `posts/montreal_events/notes/BUILD_NOTES.md` (run-log entry)

**Interfaces:**
- Consumes: SKILL.md (Task 5), CLIs (Tasks 2–4).
- Produces: the first committed `events.json` — the real data Tasks 8–9 render.

- [ ] **Step 1: Execute SKILL.md steps 1–4** (fetch → extract → validate → link check). Calendar section is still a placeholder — skip it.
- [ ] **Step 2: Sanity-read the result** — spot-check ~5 events against the doc: dates right, no personal framing in descriptions, statuses sensible (e.g. Piknic Électronik = `recurring`, volleyball leads = `lead`).
- [ ] **Step 3: Execute SKILL.md step 6** (run-log entry, commit, push). Calendar line: "not yet enabled".

---

### Task 7: Calendar sync

**⚠ Main session only** — requires the authenticated Google Calendar MCP connector.

**Files:**
- Create: `montreal_events/calendar_map.json` (initially `{}`)
- Modify: `.claude/skills/update-montreal-events/SKILL.md` (replace section 5 placeholder)

**Interfaces:**
- Consumes: `events.json` (Task 6), Google Calendar MCP tools (`create_event`, `update_event`, `list_calendars`).
- Produces: populated `calendar_map.json`; SKILL.md section 5 final text. Map shape: `{"<event id>": {"gcal_event_id": "...", "start_date": "...", "end_date": "..."}}`.

- [ ] **Step 1: Create the empty map**

```bash
echo '{}' > montreal_events/calendar_map.json
```

- [ ] **Step 2: Replace SKILL.md section 5 with the real instructions**

Replace the `## 5. Sync Google Calendar` section body with:

````markdown
Target calendar ID:
`6c17201ccbff261d301195c10de875890b7935fb87a63484cbf0a831ff8f25cc@group.calendar.google.com`

If the Google Calendar MCP is unavailable or errors, skip this section with a
warning in your final report — the commit still proceeds; sync self-heals
next run.

Read `montreal_events/calendar_map.json`. For each event in events.json with
`status: date-specific` and a non-null `end_date` that is today or later:

- **Not in the map** → create an all-day event on the target calendar:
  summary = event title; start date = `start_date` (or `end_date` if start is
  null); end date = `end_date` **plus one day** (all-day end dates are
  exclusive); description = event description + the event URL. Record
  `{"gcal_event_id", "start_date", "end_date"}` in the map.
- **In the map with different dates** → update the calendar event's dates
  (same exclusive-end rule) and refresh the map entry.
- **In the map with same dates** → do nothing.

Then prune map entries whose event id is no longer in events.json or whose
`end_date` has passed (leave the calendar events themselves — they're
history). Write the map back with 2-space indent.
````

- [ ] **Step 3: Run the initial sync now** — follow the new section 5 against the current `events.json`. Confirm the target calendar is visible via the MCP (`list_calendars`) before creating anything.
- [ ] **Step 4: Verify dedup** — re-run section 5 immediately; expected result: zero creates, zero updates ("in the map with same dates" for every event). Verify on the calendar (via MCP `list_events` on the target calendar) that each event appears exactly once with correct dates.
- [ ] **Step 5: Record + commit**

Append to the notes run log: calendar events created (count + ids).

```bash
git add .claude/skills/update-montreal-events/SKILL.md montreal_events/calendar_map.json posts/montreal_events/notes/BUILD_NOTES.md
git commit -m "feat(montreal): google calendar sync in skill + initial sync

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push
```

---

### Task 8: Page markup + styles

**Files:**
- Create: `posts/montreal_events/events/index.html`
- Create: `posts/montreal_events/events/styles.css`
- Modify: `_quarto.yml` (resources entry)

**Interfaces:**
- Consumes: nothing at runtime yet (app.js arrives in Task 9).
- Produces: DOM structure app.js (Task 9) targets — element ids: `freshness`, `views`, `chips`, `list`; view buttons carry `data-view` values `all | weekend | month`; CSS classes used by JS: `card`, `badge`, `badge-closing`, `badge-lead`, `badge-status`, `dead-link`, `chip`, `active`, `stale`, `error`.

- [ ] **Step 1: Add the resources entry**

In `_quarto.yml`, under `project.resources`, add after the jeopardy entry:

```yaml
    - "posts/montreal_events/events/**"
```

- [ ] **Step 2: Write index.html**

Create `posts/montreal_events/events/index.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Montréal Events Guide</title>
  <link rel="stylesheet" href="styles.css">
</head>
<body>
  <header>
    <h1>Montréal Events Guide</h1>
    <p class="subtitle">
      A living guide to festivals, museums, sports, and nights out —
      refreshed weekly from a curated doc.
      <a href="https://calendar.google.com/calendar/embed?src=6c17201ccbff261d301195c10de875890b7935fb87a63484cbf0a831ff8f25cc%40group.calendar.google.com&amp;ctz=America%2FToronto">
        View as a calendar →</a>
    </p>
    <p id="freshness" hidden></p>
  </header>

  <nav>
    <div id="views" role="group" aria-label="Time window">
      <button data-view="all" class="active">All</button>
      <button data-view="weekend">This weekend</button>
      <button data-view="month">Next 30 days</button>
    </div>
    <div id="chips" role="group" aria-label="Categories"></div>
  </nav>

  <main id="list" aria-live="polite"></main>

  <footer>
    <p>Built with a Google Doc, a Claude Code skill, and a static page —
      <a href="../">read how</a>.</p>
  </footer>

  <script src="app.js"></script>
</body>
</html>
```

- [ ] **Step 3: Write styles.css**

Create `posts/montreal_events/events/styles.css`:

```css
:root {
  --bg: #ffffff;
  --fg: #1f2430;
  --muted: #5c6470;
  --card: #f5f6f8;
  --border: #d9dde3;
  --accent: #2b6cb0;
  --warn-bg: #fff3cd;
  --warn-fg: #7a5b00;
  --danger: #b23b3b;
}

@media (prefers-color-scheme: dark) {
  :root {
    --bg: #16181d;
    --fg: #e6e8ec;
    --muted: #9aa2ad;
    --card: #1f2229;
    --border: #343a44;
    --accent: #6ea8dc;
    --warn-bg: #4a3d10;
    --warn-fg: #ffd970;
    --danger: #e08585;
  }
}

* { box-sizing: border-box; }

body {
  margin: 0 auto;
  max-width: 46rem;
  padding: 1.5rem 1rem 3rem;
  font: 16px/1.55 system-ui, -apple-system, "Segoe UI", sans-serif;
  background: var(--bg);
  color: var(--fg);
}

h1 { margin: 0 0 .25rem; font-size: 1.7rem; }
.subtitle { margin: 0 0 .75rem; color: var(--muted); }
a { color: var(--accent); }

#freshness {
  margin: 0 0 .5rem;
  font-size: .85rem;
  color: var(--muted);
}
#freshness.stale {
  padding: .5rem .75rem;
  border-radius: .4rem;
  background: var(--warn-bg);
  color: var(--warn-fg);
}

nav { margin: 1rem 0; display: flex; flex-direction: column; gap: .6rem; }
#views, #chips { display: flex; flex-wrap: wrap; gap: .4rem; }

button, .chip {
  padding: .3rem .7rem;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: transparent;
  color: var(--fg);
  font-size: .85rem;
  cursor: pointer;
}
button.active, .chip.active {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}

.card {
  padding: .85rem 1rem;
  margin: 0 0 .75rem;
  border: 1px solid var(--border);
  border-radius: .55rem;
  background: var(--card);
}
.card h2 { margin: 0 0 .2rem; font-size: 1.05rem; }
.card .meta { font-size: .82rem; color: var(--muted); margin: 0 0 .35rem; }
.card p { margin: .35rem 0 0; font-size: .92rem; }
.card .links { margin-top: .45rem; font-size: .85rem; }
.card .links a { margin-right: .9rem; }

.badge {
  display: inline-block;
  padding: .08rem .5rem;
  margin-left: .4rem;
  border-radius: 999px;
  font-size: .72rem;
  vertical-align: middle;
  border: 1px solid var(--border);
  color: var(--muted);
}
.badge-closing { background: var(--warn-bg); color: var(--warn-fg); border-color: transparent; }
.badge-lead { color: var(--danger); border-color: var(--danger); }
.dead-link { color: var(--danger); font-size: .8rem; }

.error { color: var(--danger); }
footer { margin-top: 2.5rem; font-size: .82rem; color: var(--muted); }
```

- [ ] **Step 4: Verify statically**

```bash
python3 -m http.server 8899 --directory posts/montreal_events/events & sleep 1
curl -s http://localhost:8899/ | grep -c 'id="list"'
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8899/styles.css
kill %1
```

Expected: `1` and `200`

- [ ] **Step 5: Commit**

```bash
git add posts/montreal_events/events/index.html posts/montreal_events/events/styles.css _quarto.yml
git commit -m "post(montreal): events page markup + styles; serve as site resource

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 9: Page logic (app.js) + end-to-end verification

**Files:**
- Create: `posts/montreal_events/events/app.js`

**Interfaces:**
- Consumes: DOM ids/classes from Task 8; `events.json` (Task 6) fetched relative (`./events.json`).
- Produces: the finished interactive page.

- [ ] **Step 1: Write app.js**

Create `posts/montreal_events/events/app.js`:

```javascript
// Montreal events page. Reads ./events.json (committed by the update skill).
const CATEGORY_LABELS = {
  festival: "Festivals", music: "Music", museum: "Museums", sports: "Sports",
  "board-games": "Board games", trivia: "Trivia", "escape-room": "Escape rooms",
  hike: "Hikes", market: "Markets", other: "Other",
};
const STATUS_LABELS = {
  "date-specific": "Dated", recurring: "Recurring",
  evergreen: "Evergreen", lead: "Unverified — check first",
};
const STATUS_ORDER = { "date-specific": 0, recurring: 1, evergreen: 2, lead: 3 };
const CLOSING_SOON_DAYS = 14;
const STALE_DAYS = 10;

const state = { view: "all", categories: new Set() };
let events = [];

const $ = (sel) => document.querySelector(sel);
const parseDate = (s) => (s ? new Date(s + "T00:00:00") : null);
const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
const addDays = (d, n) => { const c = new Date(d); c.setDate(c.getDate() + n); return c; };
const dayMs = 86400000;

function weekendWindow() {
  // Fri–Sun window containing today, or the upcoming one (Mon–Thu).
  const t = today();
  const dow = t.getDay(); // Sun=0 ... Sat=6
  const fri = addDays(t, dow === 0 ? -2 : 5 - dow);
  return [fri, addDays(fri, 2)];
}

function windowFor(view) {
  if (view === "weekend") return weekendWindow();
  if (view === "month") return [today(), addDays(today(), 30)];
  return null;
}

function inView(ev, win) {
  if (!win) return true;
  if (ev.status === "recurring") return true;
  const start = parseDate(ev.start_date), end = parseDate(ev.end_date);
  if (!start && !end) return false; // evergreen/leads only in "All"
  return (start ?? end) <= win[1] && (end ?? start) >= win[0];
}

function fmtRange(ev) {
  const opts = { month: "short", day: "numeric" };
  const start = parseDate(ev.start_date), end = parseDate(ev.end_date);
  if (start && end && ev.start_date !== ev.end_date)
    return `${start.toLocaleDateString("en-CA", opts)} – ${end.toLocaleDateString("en-CA", opts)}`;
  const one = end ?? start;
  return one ? `until ${one.toLocaleDateString("en-CA", opts)}` : "";
}

function badges(ev) {
  const out = [];
  const end = parseDate(ev.end_date);
  if (end) {
    const days = Math.round((end - today()) / dayMs);
    if (days >= 0 && days <= CLOSING_SOON_DAYS)
      out.push(`<span class="badge badge-closing">closing soon</span>`);
  }
  const cls = ev.status === "lead" ? "badge badge-lead" : "badge badge-status";
  out.push(`<span class="${cls}">${STATUS_LABELS[ev.status]}</span>`);
  return out.join("");
}

function card(ev) {
  const meta = [CATEGORY_LABELS[ev.category], fmtRange(ev), ev.location]
    .filter(Boolean).join(" · ");
  const links = [];
  if (ev.url) {
    links.push(`<a href="${ev.url}" rel="noopener">Website</a>`);
    if (ev.url_ok === false)
      links.push(`<span class="dead-link">⚠ link may be dead</span>`);
  }
  if (ev.location) {
    const q = encodeURIComponent(`${ev.location}, Montréal, QC`);
    links.push(`<a href="https://www.google.com/maps/search/?api=1&query=${q}" rel="noopener">Map</a>`);
  }
  return `<article class="card">
    <h2>${ev.title}${badges(ev)}</h2>
    <p class="meta">${meta}</p>
    <p>${ev.description}${ev.notes ? ` <em>${ev.notes}</em>` : ""}</p>
    ${links.length ? `<div class="links">${links.join(" ")}</div>` : ""}
  </article>`;
}

function render() {
  const win = windowFor(state.view);
  const visible = events
    .filter((ev) => inView(ev, win))
    .filter((ev) => !state.categories.size || state.categories.has(ev.category))
    .sort((a, b) =>
      STATUS_ORDER[a.status] - STATUS_ORDER[b.status] ||
      (a.end_date ?? "9999").localeCompare(b.end_date ?? "9999") ||
      a.title.localeCompare(b.title));
  $("#list").innerHTML = visible.length
    ? visible.map(card).join("")
    : `<p class="meta">Nothing matches — try widening the filters.</p>`;
}

function renderChips() {
  const present = [...new Set(events.map((e) => e.category))]
    .sort((a, b) => CATEGORY_LABELS[a].localeCompare(CATEGORY_LABELS[b]));
  $("#chips").innerHTML = present.map((c) =>
    `<button class="chip" data-category="${c}">${CATEGORY_LABELS[c]}</button>`).join("");
  $("#chips").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    const c = chip.dataset.category;
    state.categories.has(c) ? state.categories.delete(c) : state.categories.add(c);
    chip.classList.toggle("active");
    render();
  });
}

function renderFreshness(lastUpdated) {
  const el = $("#freshness");
  el.hidden = false;
  const days = Math.round((today() - parseDate(lastUpdated)) / dayMs);
  el.textContent = `Last updated ${lastUpdated}`;
  if (days > STALE_DAYS) {
    el.classList.add("stale");
    el.textContent += ` — this data is ${days} days old.`;
  }
}

$("#views").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-view]");
  if (!btn) return;
  state.view = btn.dataset.view;
  document.querySelectorAll("#views button").forEach((b) =>
    b.classList.toggle("active", b === btn));
  render();
});

fetch("./events.json")
  .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
  .then((data) => {
    events = data.events;
    renderFreshness(data.last_updated);
    renderChips();
    render();
  })
  .catch(() => {
    $("#list").innerHTML = `<p class="error">Couldn't load events data. Try refreshing.</p>`;
  });
```

- [ ] **Step 2: Verify against real data in a browser-equivalent check**

```bash
python3 -m http.server 8899 --directory posts/montreal_events/events & sleep 1
curl -s http://localhost:8899/events.json | uv run --group montreal python -c "import json,sys; d=json.load(sys.stdin); print(len(d['events']), 'events,', d['last_updated'])"
kill %1
```

Expected: a positive event count and today's-ish date. Then open `http://localhost:8899/` in a browser (or ask the user to) and confirm: cards render, view toggles change the list, chips filter, badges appear, freshness line shows.

- [ ] **Step 3: Verify the Quarto site serves it**

```bash
quarto render
ls _site/posts/montreal_events/events/
```

Expected: `index.html styles.css app.js events.json` all present.

- [ ] **Step 4: Append a build-log note**

Add to `BUILD_NOTES.md` under `## Build log`: one or two lines on anything notable from building the page (rendering decisions, weekend-window logic, surprises).

- [ ] **Step 5: Commit**

```bash
git add posts/montreal_events/events/app.js posts/montreal_events/notes/BUILD_NOTES.md
git commit -m "post(montreal): events page logic — views, filters, badges, freshness

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push
```

---

### Task 10: Blog post

**Files:**
- Create: `posts/montreal_events/index.qmd`

**Interfaces:**
- Consumes: `posts/montreal_events/notes/BUILD_NOTES.md` (all accumulated entries), the live page at `events/`.
- Produces: the draft post.

- [ ] **Step 1: Write the post**

Create `posts/montreal_events/index.qmd` with this frontmatter:

```yaml
---
title: "A Self-Updating Montreal Events Guide"
description: "Turning a ChatGPT-maintained Google Doc into a live events page with a Claude Code skill, a JSON schema, and zero hosting or API costs."
date: today's date
draft: true
categories: [claude, automation, quarto]
---
```

Write the body from `BUILD_NOTES.md`, covering in order:

1. **The setup** — a Google Doc that ChatGPT refreshes weekly; wanting it as a browsable page.
2. **The doc-as-API trick** — link-shared Google Docs expose an unauthenticated `export?format=txt` endpoint.
3. **LLM extraction behind a schema validator** — why deterministic parsing loses to an LLM here, and why `validate.py` makes the LLM step safe (show the schema or an excerpt of it).
4. **In-session skill vs. paid CI** — the cost/infrastructure comparison; why the skill won.
5. **Calendar sync via MCP** — id-keyed dedup through `calendar_map.json`.
6. **The page** — link to `events/`, screenshot, feature run-through.
7. **What broke / surprised** — pull honest material from the build/run logs.

Include a link to the live page (`[the events page](events/)`) and at least one code excerpt from the repo (real code, not paraphrased).

- [ ] **Step 2: Render and check**

```bash
quarto render posts/montreal_events/index.qmd
ls _site/posts/montreal_events/index.html
```

Expected: renders without errors; file exists. Because `draft: true` with `draft-mode: unlinked`, it's reachable by URL but not listed.

- [ ] **Step 3: Screenshot thumbnail**

Take a screenshot of the rendered events page, save as `posts/montreal_events/thumbnail.png`, and add `image: thumbnail.png` to the frontmatter (mirrors the jeopardy post).

- [ ] **Step 4: Commit**

```bash
git add posts/montreal_events/index.qmd posts/montreal_events/thumbnail.png
git commit -m "post(montreal): draft blog post on the self-updating events guide

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
git push
```

Leave `draft: true` — the user promotes it when happy.
