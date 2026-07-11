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
