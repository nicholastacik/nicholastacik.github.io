# Events Page — Auth & Write Foundation (E1) — Design

**Date:** 2026-08-06
**Status:** Approved pending user review
**Sub-project:** E1 of the events-page evolution (E1 auth foundation · E2 calendar · E3 verify+recurrence · E4 auto-images)

## Overview

Turn the read-only Montréal events page into one that can write a user
decision back to the source Google Doc, gated by Google sign-in, proven on
the simplest possible action: **hide / unhide an event**. E1 builds the
plumbing every later sub-project reuses — browser OAuth, doc-write, an
optimistic local overlay — and deliberately does the least on top of it.

The page stays public and static (GitHub Pages, no backend). Viewing needs no
auth; only writing prompts sign-in, and a write only succeeds for a Google
account with edit access to the doc — so Google's own permission model is the
access gate.

## Key decisions (with rationale)

| Decision | Rationale |
|---|---|
| One opaque machine line per card, not four labeled fields | The page edits it via the Docs API; a single unique full-line string can be swapped with one `replaceAllText` op — no character-index math, robust to reformatting. The user does not hand-edit the doc, so human legibility of these fields has no value. |
| Client-side OAuth (Google Identity Services), no backend | Keeps the site static and free. Google's doc-permission model gates writes: strangers can view but cannot edit a doc never shared with them. |
| OAuth consent screen in "testing" mode | Two named users (Nick + wife) — avoids Google's app-verification process entirely; one-time "unverified app" click-through is acceptable. |
| `replaceAllText` on the exact current line, not index splicing | The machine line is unique per card (contains the id). Read the live line, swap the whole string. Atomic, and immune to spacing/format drift. |
| Optimistic localStorage overlay | The page reads committed `events.json` (weekly snapshot); a write lands in the doc and won't appear in `events.json` until the next rebuild. The overlay makes the action feel instant and self-retires once the committed data catches up. |
| E1 carries all four managed values through the pipeline but only *acts on* `hidden` | Avoids validation failures when the doc already has the full machine line, without building E2–E4 features early. |

## The machine-line contract

Each doc entry ends with exactly one line:

```
{{tool <id> | hidden=<no|yes> | calendar=<no|yes> | recurrence=<none|schedule> | image=<auto|url>}}
```

- `<id>` is the entry's lowercased ID (`evt-003`). The `{{tool <id>` prefix is
  unique in the document — this is the write anchor.
- ChatGPT creates the line with all defaults on new entries, never edits the
  values, and carries it verbatim across restructures (enforced by the doc's
  Weekly-update standard).
- The unauthenticated `export?format=txt` the pipeline already uses includes
  this line as plain text, so the read path is unchanged — only the parser grows.

## Components & data flow

```
Google Doc  ──export?format=txt──▶  skill extraction ──▶ events.json ──▶ page (read)
   ▲                                (parses {{tool}} line)                  │
   │                                                                        │ hide/unhide
   └────────────── Docs API replaceAllText (browser, OAuth) ◀──────────────┘
                                                          + optimistic overlay (localStorage)
```

**Pipeline (read side):**
- `montreal_events/events.schema.json`: add four fields — `hidden` (boolean),
  `calendar` (boolean), `recurrence` (string|null), `image` (string|null).
- `SKILL.md` extraction rules: parse the `{{tool <id> | ...}}` line for each
  card into those fields. Missing line → apply defaults (`hidden=false`,
  `calendar=false`, `recurrence=null`, `image=null`) and note it in the run log.
- `validate.py`: accept and sanity-check the four fields (booleans parse; if
  `hidden` is absent default false).

**Page (write side):**
- **Sign-in:** a header control ("Sign in to edit"). Google Identity Services
  token client, scope `https://www.googleapis.com/auth/documents`. Token held
  in memory for the session. Viewing never triggers it.
- **Hide/unhide control** per event card. On click (signed in):
  1. `documents.get` the doc.
  2. Locate the text segment starting `{{tool <id>` through the next `}}` →
     the exact current line string.
  3. Construct the new line with `hidden` flipped.
  4. `documents.batchUpdate` with one `replaceAllText` (old = exact current
     line, new = modified line, `matchCase: true`).
- **Optimistic overlay:** `localStorage["montreal_overlay"]` = `{ "<id>":
  {hidden: bool}, ... }`. Rendering merges the overlay over `events.json`.
  On successful write, keep the entry. On failed write, drop it and revert the
  UI. On load, if `events.json` already matches an overlay entry (rebuild
  caught up), prune that entry.
- **Filtering:** events resolving to `hidden: true` (committed or overlay) are
  omitted from all views; a small "N hidden — show" affordance reveals them so
  a hide is reversible.

## Error handling

- Not signed in when a write is attempted → trigger the sign-in flow, then retry.
- Docs API 403 (account lacks edit access) → revert the optimistic change, show
  "You don't have edit access to the events doc."
- Network/API error → revert, show a transient error; the overlay entry is not
  persisted.
- `documents.get` returns no matching `{{tool <id>` line (doc drift / not yet
  backfilled) → no write, show "Couldn't find this event in the doc."

## One-time setup (user, documented step-by-step in the plan)

Google Cloud console, ~10–15 min, free, no billing account:
1. Create a project.
2. Enable the Google Docs API.
3. Configure the OAuth consent screen: "External", publishing status
   **Testing**, add Nick + wife as test users.
4. Create an OAuth **Web** client ID; authorized JavaScript origins:
   `https://nicholastacik.github.io` and `http://localhost:<port>` for dev.
5. Share the events doc with the wife's Google account as **Editor** (Nick
   already owns it).
The client ID is public (safe to commit); there is no client secret in the
browser flow.

## Testing

- **Unit (pytest / node):** machine-line parsing (txt line → field values,
  incl. missing-line defaults); overlay merge (committed × overlay →
  displayed); new-line construction (current line + toggle → correct new line
  string, values other than `hidden` preserved).
- **Manual e2e checklist:** sign in as an editor → hide an event → confirm the
  `{{tool}}` line in the doc now reads `hidden=yes` → reload, event stays
  hidden via overlay → run the pipeline → `events.json` shows `hidden:true`,
  overlay self-prunes. Sign in as a non-editor Google account → hide fails
  cleanly with the access message.

## Out of scope (later sub-projects)

- Calendar add/remove (E2 — direct Calendar API, deterministic ids).
- Verify + recurrence writes and recurrence-driven views (E3).
- Auto-images (E4 — pipeline fills `image`, page renders).
E1 carries `calendar`, `recurrence`, and `image` through the pipeline but adds
no UI or behavior for them.

## Build phases

1. Machine-line parsing: schema + extraction rules + `validate.py` + tests;
   one pipeline run producing an `events.json` with the four fields.
2. GCP/OAuth setup (manual, documented) + "Sign in to edit" in the page.
3. Hide/unhide: `replaceAllText` write, optimistic overlay, filtering + the
   "show hidden" affordance.
4. Manual e2e verification against the checklist.
