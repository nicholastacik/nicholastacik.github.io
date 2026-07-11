# Montreal Events Guide — Design

**Date:** 2026-07-11
**Status:** Approved pending user review

## Overview

A living "what's on in Montreal" page on nicholastacik.github.io, driven by the
"Montreal Clubs & Events" Google Doc that ChatGPT updates every Thursday. A
Claude Code project skill (`/update-montreal-events`) refreshes the site's data
from the doc, checks links, and syncs dated events into a personal Google
Calendar — all in-session (subscription-covered, no API billing, no CI
secrets). A supporting Quarto blog post documents the build.

## Key decisions (with rationale)

| Decision | Rationale |
|---|---|
| Read the doc via its public export URL (`/export?format=txt`) | Doc is link-shared; the export endpoint needs no auth. Verified working. |
| LLM extraction (Claude in-session), not a deterministic parser | ChatGPT owns the doc format with no contract; prose → schema is the one genuinely fuzzy step. |
| Project skill instead of GitHub Action + API key | Runs under the existing Claude subscription: $0, no Console account, no repo secrets. Automation (scheduled agent or Action) can wrap the same logic later. |
| Skill + Python helpers (not pure-instruction skill) | Deterministic steps (fetch, validate, link check) live in testable scripts; the LLM only extracts. A schema validator gates the LLM output before anything is committed. |
| Standalone static HTML page, not a `.qmd` | Data updates need only a JSON commit + Pages redeploy — no Quarto/Python in the loop. Matches the Jeopardy research-tool precedent. |
| Calendar sync via Google Calendar MCP (in-session) | User wants events in an existing group calendar. MCP is already connected; no `.ics` feed or manual adding. |
| `calendar_map.json` kept out of the served directory | Sync state (private calendar event IDs) should not be published. |
| Personal framing stripped during extraction | The doc is written personally; the public page is a neutral events guide. |

## Layout

```
montreal_events/                 # root-level pipeline (mirrors jeopardy/)
  fetch_doc.py                   # fetch public export → plain text on stdout
  validate.py                    # jsonschema + sanity checks on events.json
  check_links.py                 # HTTP sweep, writes url_ok flags
  events.schema.json             # the contract for events.json
  calendar_map.json              # event id → gcal event id (sync state, not served)
  tests/                         # pytest for validate.py and check_links.py
posts/montreal_events/           # post + served page (mirrors posts/jeopardy_ds/)
  index.qmd                      # blog post; draft: true until promoted
  notes/BUILD_NOTES.md           # running build/run notes feeding the post
  events/                        # static page, copied into _site verbatim
    index.html
    styles.css
    app.js
    events.json                  # committed data — page's source of truth
.claude/skills/update-montreal-events/SKILL.md
```

`_quarto.yml` changes: add `posts/montreal_events/events/**` to
`project.resources`; exclude `posts/montreal_events/notes/` from render.
Public page URL: `/posts/montreal_events/events/`.

## Data model

`events.json`:

```json
{
  "last_updated": "2026-07-11",
  "source_doc": "https://docs.google.com/document/d/15o4_PIve4R0K3Wgle58lUCxQwmDLBCiMn6f4M0FVOV4/",
  "events": [
    {
      "id": "nuits-dafrique-2026",
      "title": "Festival International Nuits d'Afrique",
      "category": "festival",
      "status": "date-specific",
      "start_date": "2026-07-07",
      "end_date": "2026-07-19",
      "location": "Quartier des spectacles",
      "url": "https://festivalnuitsdafrique.com/",
      "url_ok": true,
      "description": "Free outdoor concerts plus ticketed shows; world-music festival downtown.",
      "notes": "Verify English-language programming before booking."
    }
  ]
}
```

- `id`: stable kebab-case slug (include year for annual events) so identity
  holds week over week; this is the calendar-sync dedup key.
- `category` enum: `festival | music | museum | sports | board-games | trivia
  | escape-room | hike | market | other`.
- `status` enum: `date-specific | recurring | evergreen | lead`. `lead` means
  the doc says "verify before going" (unconfirmed trivia nights, volleyball
  leads, watch items).
- `start_date` / `end_date`: ISO dates, nullable (recurring/evergreen items
  usually have none).
- `url_ok`: `true` / `false` / `null` (null = check inconclusive, e.g.
  network error or bot-blocking; distinct from a confirmed dead link).
- `description`: de-personalized rewrite of the doc's "why it fits".
- `notes`: optional caveats worth showing on the page.

`montreal_events/calendar_map.json`: `{ "<event id>": {"gcal_event_id": "...",
"start_date": "...", "end_date": "..."} }` — dates recorded so the skill can
detect when a synced event's dates changed and update rather than recreate.

## The skill (`/update-montreal-events`)

`SKILL.md` steps, in order:

1. **Fetch**: `uv run montreal_events/fetch_doc.py` — GET the export URL,
   print text. Non-200 or empty body → abort, nothing modified.
2. **Extract** (Claude, in-session): doc text → new `events.json` conforming
   to `events.schema.json`. Rules: stable ids; strip personal framing; drop
   date-specific events whose `end_date` is in the past; preserve the doc's
   verify-first caveats in `notes`; carry over `url_ok` values from the
   previous committed file (the link check refreshes them next).
3. **Validate**: `uv run montreal_events/validate.py` — jsonschema plus
   sanity checks (dates parse and start ≤ end, enums valid, ids unique and
   slug-shaped, no expired date-specific events, `last_updated` is today).
   Failure → skill stops and reports; nothing committed.
4. **Link check**: `uv run montreal_events/check_links.py` — request each
   distinct URL (HEAD, falling back to GET), set `url_ok`. Timeouts/network
   errors → `null`. Report newly dead links in the session summary.
5. **Calendar sync** (Claude via Google Calendar MCP): target calendar
   `6c17201ccbff261d301195c10de875890b7935fb87a63484cbf0a831ff8f25cc@group.calendar.google.com`.
   For each `date-specific` event with dates that hasn't already ended:
   - not in `calendar_map.json` → create an all-day event spanning
     start→end, titled with the event title, description linking to the
     event URL; record the mapping.
   - in the map but dates changed → update the calendar event and the map.
   - Ended events stay on the calendar (history) and are pruned from the map.
   MCP failures don't block the commit; the sync self-heals on the next run.
6. **Record + commit**: append a dated changelog entry to
   `posts/montreal_events/notes/BUILD_NOTES.md` (added/removed/changed
   events, dead links found, calendar actions taken); commit `events.json`,
   `calendar_map.json`, and the notes; push. GitHub Pages redeploys.

## The page

Vanilla HTML/CSS/JS in `posts/montreal_events/events/`; no build step; no
external dependencies; `app.js` fetches `./events.json` at load.

- **Views**: All · This weekend (Fri–Sun window containing/next after today) ·
  Next 30 days. Date views include date-specific events whose range overlaps
  the window, plus recurring items.
- **Category filter chips**, combinable with the view toggle.
- **Sort**: date-specific ascending by `end_date` (soonest-ending first),
  then recurring, then evergreen, then leads.
- **Badges**: closing-soon (`end_date` within 14 days); status badges, with
  `lead` rendered as "unverified — check before going"; broken-link warning
  icon when `url_ok === false`.
- **Freshness banner**: "Last updated {date}"; turns into an amber warning
  when `last_updated` is more than 10 days old.
- **Map links**: Google Maps search URL on `location` + "Montréal" (only when
  `location` is present).
- **Calendar link**: header link to the public Google Calendar embed.
- **Theme**: light/dark via `prefers-color-scheme`, visually consistent with
  the site's cosmo/darkly themes.
- Empty/error states: JSON fetch failure shows a plain error message rather
  than a blank page.

## Blog post + notes

`BUILD_NOTES.md` accumulates: phase-by-phase build decisions and surprises,
and per-run changelogs from the skill. The post (`posts/montreal_events/index.qmd`,
`draft: true`) is written last from those notes. Outline: the doc-as-API trick
(public export endpoint), LLM-extraction-behind-a-schema-validator pattern,
why an in-session skill beat paid CI for this, calendar sync via MCP, and the
page itself.

## Error handling

- Fetch failure or validation failure → abort before any write/commit.
- Link check is advisory: it can't fail the run, only annotate.
- Calendar MCP unavailable (not authed / headless) → skip sync with a warning;
  JSON still commits; next run reconciles.
- Page handles missing/malformed JSON with a visible error state.

## Testing

- `pytest` under `montreal_events/tests/`: `validate.py` (accept/reject
  fixtures — bad enum, expired event, duplicate id, start > end) and
  `check_links.py` (mocked responses: 200, 404, timeout → true/false/null).
- Extraction has no unit test; the validator gates it on every real run.
- Page: manual verification against the committed `events.json` (open via
  `python -m http.server` or the rendered site).

## Build phases

1. **Pipeline + skill**: scripts, schema, tests, `SKILL.md` (fetch → extract
   → validate → link check → notes → commit). First real run produces
   `events.json` from the live doc.
2. **Calendar sync**: map file, MCP create/update flow, dedup rules; added to
   the skill.
3. **Page**: HTML/CSS/JS, `_quarto.yml` resources entry, verify on the
   rendered site.
4. **Blog post**: write `index.qmd` from `BUILD_NOTES.md`, add thumbnail,
   promote from draft when ready.

## Out of scope (deliberate)

- Scheduled automation (cloud agent routine or GitHub Action) — the skill is
  the v1 interface; automation can wrap it later.
- Price indicators, indoor/outdoor tags, "pick for us" button, transit tags,
  weekly changelog page (git history covers it).
- Editing the Google Doc — ChatGPT's Thursday workflow owns the doc;
  this pipeline is read-only toward it.
