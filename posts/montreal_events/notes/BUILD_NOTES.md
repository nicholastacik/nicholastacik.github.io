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
