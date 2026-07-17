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
`montreal_events/events.schema.json` exactly.

The doc (V2, since 2026-07-16) is card-structured: entries look like
`◆ [EVT-003] Name` followed by pipe-delimited fields (Type, Status, Location,
Cost, English, Best for, Tags, Why we recommend it, Related, Confidence,
Link). **The entry cards are the source of truth**; TOP PICKS, CALENDAR,
DATE IDEAS, MEET NEW PEOPLE, and DAY TRIPS are index/cross-reference
sections — use them only to resolve dates a card leaves vague. Rules:

- One entry per card. `id` = the card's ID, lowercased (`EVT-003` →
  `evt-003`) — the doc's IDs are canonical and stable; they are the
  calendar-sync key.
- **Skip**: everything under ARCHIVE; wishlist entries with no venue/link
  (goal-only cards like WISH-002/003/004 — keep venue watch items like
  WISH-001 as `lead`); cross-category bundle cards with no venue of their
  own (e.g. FOD-001); the REVIEWS section.
- Cards listing multiple links (`Links: a | b`): use the first as `url`,
  mention the alternative in `notes`.
- `category`: one of `festival, music, museum, sports, board-games, trivia,
  escape-room, hike, market, other` — judge from the card's Type/Tags
  (ART-*/MUS-* → museum; NAT-* → hike; PUZ-* → escape-room; SOC trivia
  leads → trivia; parks → other; conventions/shows → other). Ottawa TRP-*
  entries keep their content category (music/festival) with an Ottawa
  `location`.
- `status` from the card's Status field: an explicit date/range →
  `date-specific`; Recurring/Seasonal variants → `recurring`;
  Evergreen variants → `evergreen`; Verify/Watch variants → `lead`.
  Archived → skip.
- Confidence below "Confirmed" (Strong lead / Watch only) → reflect the
  caveat in `notes` (and prefer `lead` status when the card itself says
  verify-first).
- Dates from the Status field: "July 16–19, 2026" → both dates;
  "Through October 11, 2026" → `start_date: null`.
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
