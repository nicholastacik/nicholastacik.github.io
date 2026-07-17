# Montreal Events — build & run notes

Raw material for the blog post (posts/montreal_events/index.qmd).
Build phases append decisions/surprises; each skill run appends a changelog.

## Build log

### 2026-07-11 — design
- Doc is publicly exportable (`export?format=txt`) — no Google auth anywhere.
- Chose in-session skill over GitHub Action + API key: $0, no secrets.
- LLM extraction gated by a jsonschema validator; deterministic steps in Python.
- Calendar sync via Google Calendar MCP; sync state kept out of the served dir.

### 2026-07-11 — app.js (page logic)
- Weekend window: getDay()===0 (Sunday) maps to Friday 2 days prior; Mon–Sat compute offset via (5-dow). Evergreen/lead events only shown in "All" view.
- Cards render title + 2-3 badges (closing-soon, status), metadata (category · date range · location), description, and optional notes + website/map links.

## Run log

### 2026-07-11 — skill run (first real run)
- Added: 63 events extracted from the doc (first run — everything is new): 8 festivals, 6 music, 18 museums, 12 sports, 4 board-games, 5 trivia leads, 5 escape rooms, 5 hikes/nature, plus markets/other.
- Removed: none (first run; no date-specific event in the doc has ended before today).
- Changed: n/a (first run).
- Dead links: 6 — larecreation.ca, sauvequipeut.ca/en/, ezkapaz.com/en/, and all three sepaq.com park pages. The SEPAQ trio failing together suggests bot-blocking of both HEAD and GET rather than genuinely dead pages; worth eyeballing in a browser.
- Calendar: not yet enabled.
- Observation for the blog post: extraction judgment calls — Otakuthon and Cirque du Soleil got category "other"; "until X" exhibits get null start_date; long-running exhibits kept status date-specific since they have real end dates.

### 2026-07-16 — skill run (doc V2 migration)
- The doc was restructured to "V2" today: entry cards with canonical IDs (EVT-003, MUS-007...), pipe-delimited fields (Type/Status/Cost/English/Tags/Confidence), a CALENDAR index, ARCHIVE and WISHLIST sections. Extraction rules in SKILL.md updated to match; the doc's IDs (lowercased) are now our event ids and the calendar-sync key — switching cost nothing since calendar_map was still empty.
- Added: 5 Ottawa weekend-trip entries (trp-001..005 — Bluesfest, Capital Pride, Animation Festival, CityFolk, Chamberfest).
- Removed: Montréal Complètement Cirque (ended July 12, doc archived it); Immersia merged into puz-004 with Sauve Qui Peut (doc treats them as one card).
- Net: 63 → 66 events. All ids migrated to doc-canonical form.
- Dead links: same 6 as last run (larecreation, sauvequipeut, ezkapaz, 3× sepaq — still suspect bot-blocking for SEPAQ).
- Calendar: skipped — Google Calendar MCP still needs re-authorization.
- Blog observation: the V2 restructure is the LLM-extraction bet paying off — the format changed completely and the pipeline needed only prompt-rule edits in SKILL.md, zero code changes. A deterministic parser would have been a rewrite.

### 2026-07-16 (late) — initial calendar sync
- Calendar access solved cross-account: the group calendar lives on a different Google account than the Claude connector, so it was shared to the connector account with "Make changes to events" — the MCP then has owner-level access by calendar ID. No design change needed.
- Created 27 all-day events (11 festivals/events, 14 exhibits, 2 Ottawa trips); calendar_map.json now holds all id → gcal_event_id mappings.
- Convention adopted and codified in SKILL.md: null-start "until X" exhibits become single-day closing markers titled "(ends <date>)" with "Last day:" descriptions — a month-spanning bar for every exhibit would have wallpapered the calendar.
- Verified dedup: list_events shows exactly 27, one per id; re-running the sync is a no-op.
