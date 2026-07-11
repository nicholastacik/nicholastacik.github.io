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
