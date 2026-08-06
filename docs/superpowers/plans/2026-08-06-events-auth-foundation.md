# Events Page Auth & Write Foundation (E1) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prove the browser → Google sign-in → write-to-doc → survives-weekly-rebuild chain on the simplest action (hide/unhide an event), and lay the plumbing E2–E4 reuse.

**Architecture:** The static page gains client-side Google OAuth (Google Identity Services) and writes a single `{{tool <id> ...}}` machine line back to the source Doc via the Docs API `replaceAllText`. Viewing stays public and auth-free; only writing prompts sign-in, and Google's doc-permission model gates it. Pure logic (parse/build the machine line, overlay merge) lives in a DOM-free ES module with unit tests; auth + DOM + network wiring live in `app.js` and are manually verified.

**Tech Stack:** Vanilla ES modules (no framework, no build step), Google Identity Services (`accounts.google.com/gsi/client`), Google Docs REST API via `fetch`, Node's built-in `node:test` for JS unit tests, existing Python pipeline (`uv`, jsonschema, pytest).

**Spec:** `docs/superpowers/specs/2026-08-06-events-auth-foundation-design.md`

## Global Constraints

- Branch is `main`. **Do NOT push** — `main` carries ~24 unrelated unpushed commits (PTCG + Jeopardy) and the site auto-deploys on push; pushing is the user's decision.
- The page stays a static, no-build-step site on GitHub Pages. External scripts are allowed (this is a normal site, not a sandboxed Artifact) — GIS is loaded from `accounts.google.com`.
- The OAuth **client ID is public** and safe to commit. There is **no client secret** in the browser flow — never add one.
- Managed machine-line format (verbatim): `{{tool <id> | hidden=<no|yes> | calendar=<no|yes> | recurrence=<none|schedule> | image=<auto|url>}}`, `<id>` lowercased.
- Managed-field semantics: `hidden`/`calendar` booleans (`yes`/`no`); `recurrence` `none`→null; `image` `auto`→null.
- Google Doc ID (verbatim): `15o4_PIve4R0K3Wgle58lUCxQwmDLBCiMn6f4M0FVOV4`
- Docs OAuth scope (verbatim): `https://www.googleapis.com/auth/documents`
- Local dev server port is `8899` (used by existing verification commands and the OAuth localhost origin).
- Node 18+ required for `node --test` and ESM (already used in the repo for `node --check`).
- Commit style: `feat(montreal): ...` (code), `docs(montreal): ...` (setup notes). End every commit message with `Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>`.
- Task 3 has a **manual prerequisite** (Google Cloud console) only the user can do; the plan documents the exact clicks. Tasks 3–5 involve OAuth/live-doc behavior that cannot be unit-tested — they carry a manual verification checklist instead.

## File structure

- `montreal_events/events.schema.json` — add the four managed fields to the event schema (optional, typed). *Modify.*
- `montreal_events/tests/test_schema.py` — accept/reject cases for the managed fields. *Modify.*
- `.claude/skills/update-montreal-events/SKILL.md` — extraction rule: parse the machine line into the four fields. *Modify.*
- `posts/montreal_events/events/events-core.js` — DOM-free pure helpers (`parseToolLine`, `buildToolLine`, `mergeOverlay`). *Create.*
- `posts/montreal_events/events/events-core.test.js` — `node:test` unit tests. *Create.*
- `posts/montreal_events/events/config.js` — public `GOOGLE_CLIENT_ID` + `DOC_ID`. *Create.*
- `posts/montreal_events/events/index.html` — load GIS, make `app.js` a module, add auth button + hidden-toggle. *Modify.*
- `posts/montreal_events/events/styles.css` — styles for auth button, hide button, dimmed hidden card, hidden-toggle. *Modify.*
- `posts/montreal_events/events/app.js` — import core+config; auth, overlay, hide/unhide write, filtering. *Modify (full rewrite in Task 4).*
- `posts/montreal_events/notes/BUILD_NOTES.md` — E1 setup + e2e results. *Modify.*

---

### Task 1: Schema + extraction rule for the managed machine line

**Files:**
- Modify: `montreal_events/events.schema.json`
- Modify: `montreal_events/tests/test_schema.py`
- Modify: `.claude/skills/update-montreal-events/SKILL.md`

**Interfaces:**
- Consumes: nothing.
- Produces: `events.json` events MAY carry `hidden` (boolean), `calendar` (boolean), `recurrence` (string|null), `image` (string|null). Absent = treated as defaults downstream. The page (Task 4) reads `hidden`.

- [ ] **Step 1: Write the failing tests**

Add to `montreal_events/tests/test_schema.py`:

```python
def test_schema_accepts_managed_fields():
    schema = json.loads(SCHEMA_PATH.read_text())
    doc = {
        "last_updated": "2026-08-06",
        "source_doc": "https://docs.google.com/document/d/x/",
        "events": [{
            "id": "evt-003", "title": "A", "category": "festival",
            "status": "date-specific", "start_date": None, "end_date": None,
            "location": None, "url": None, "url_ok": None, "description": "d",
            "hidden": True, "calendar": False, "recurrence": "weekly, Tuesdays",
            "image": "https://example.com/x.png",
        }],
    }
    assert list(Draft202012Validator(schema).iter_errors(doc)) == []


def test_schema_rejects_hidden_as_string():
    schema = json.loads(SCHEMA_PATH.read_text())
    doc = {
        "last_updated": "2026-08-06",
        "source_doc": "x",
        "events": [{
            "id": "evt-003", "title": "A", "category": "festival",
            "status": "evergreen", "start_date": None, "end_date": None,
            "location": None, "url": None, "url_ok": None, "description": "d",
            "hidden": "yes",
        }],
    }
    assert list(Draft202012Validator(schema).iter_errors(doc)) != []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --group montreal pytest montreal_events/tests/test_schema.py -v`
Expected: the two new tests FAIL — `test_schema_accepts_managed_fields` fails because `additionalProperties: false` rejects the unknown `hidden`/`calendar`/`recurrence`/`image` keys.

- [ ] **Step 3: Add the four fields to the schema**

In `montreal_events/events.schema.json`, inside `$defs.event.properties` (after the `notes` property), add:

```json
        "hidden": { "type": "boolean" },
        "calendar": { "type": "boolean" },
        "recurrence": { "type": ["string", "null"] },
        "image": { "type": ["string", "null"] }
```

Leave `required` unchanged (the fields are optional so pre-existing `events.json` still validates).

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --group montreal pytest montreal_events/tests/ -v`
Expected: all pass (existing schema/validate/fetch/links tests + the two new ones).

- [ ] **Step 5: Add the extraction rule to SKILL.md**

In `.claude/skills/update-montreal-events/SKILL.md`, in the `## 2. Extract to JSON` section, add a bullet immediately after the `id = the card's ID, lowercased` bullet:

```markdown
- Managed fields — read the entry's `{{tool <id> | hidden=.. | calendar=.. |
  recurrence=.. | image=..}}` line and emit them onto the event:
  `hidden`/`calendar` → booleans (`yes`→true, `no`→false); `recurrence` →
  the string, or null when `none`; `image` → the URL, or null when `auto`.
  If the line is missing, default to `hidden:false, calendar:false,
  recurrence:null, image:null` and note it in the run log.
```

- [ ] **Step 6: Commit**

```bash
git add montreal_events/events.schema.json montreal_events/tests/test_schema.py .claude/skills/update-montreal-events/SKILL.md
git commit -m "feat(montreal): carry managed machine-line fields through the pipeline

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Pure core module + unit tests

**Files:**
- Create: `posts/montreal_events/events/events-core.js`
- Create: `posts/montreal_events/events/events-core.test.js`

**Interfaces:**
- Consumes: nothing.
- Produces (ES module exports, imported by `app.js` in Task 4):
  - `parseToolLine(line: string) -> {id, hidden:boolean, calendar:boolean, recurrence:string|null, image:string|null} | null`
  - `buildToolLine(id: string, fields: {hidden,calendar,recurrence,image}) -> string`
  - `mergeOverlay(events: object[], overlay: {[id]: {hidden?:boolean}}) -> object[]`

- [ ] **Step 1: Write the failing tests**

Create `posts/montreal_events/events/events-core.test.js`:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { parseToolLine, buildToolLine, mergeOverlay } from "./events-core.js";

test("parseToolLine reads all fields", () => {
  const r = parseToolLine(
    "{{tool evt-003 | hidden=yes | calendar=no | recurrence=weekly, Tuesdays | image=https://x/y.png}}");
  assert.deepEqual(r, {
    id: "evt-003", hidden: true, calendar: false,
    recurrence: "weekly, Tuesdays", image: "https://x/y.png",
  });
});

test("parseToolLine maps none/auto to null", () => {
  const r = parseToolLine(
    "{{tool mus-007 | hidden=no | calendar=no | recurrence=none | image=auto}}");
  assert.deepEqual(r, {
    id: "mus-007", hidden: false, calendar: false, recurrence: null, image: null,
  });
});

test("parseToolLine returns null on non-tool text", () => {
  assert.equal(parseToolLine("Just For Laughs, downtown"), null);
});

test("buildToolLine round-trips with parseToolLine", () => {
  const line =
    "{{tool evt-010 | hidden=yes | calendar=yes | recurrence=none | image=auto}}";
  assert.equal(buildToolLine("evt-010", parseToolLine(line)), line);
});

test("buildToolLine defaults null recurrence/image to none/auto", () => {
  assert.equal(
    buildToolLine("brd-001", { hidden: false, calendar: false, recurrence: null, image: null }),
    "{{tool brd-001 | hidden=no | calendar=no | recurrence=none | image=auto}}");
});

test("mergeOverlay overrides hidden by id, leaves others untouched", () => {
  const events = [{ id: "a", hidden: false }, { id: "b", hidden: false }];
  const merged = mergeOverlay(events, { a: { hidden: true } });
  assert.equal(merged[0].hidden, true);
  assert.equal(merged[1].hidden, false);
  assert.equal(events[0].hidden, false); // input not mutated
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `node --test posts/montreal_events/events/events-core.test.js`
Expected: FAIL — `Cannot find module './events-core.js'`.

- [ ] **Step 3: Implement the core module**

Create `posts/montreal_events/events/events-core.js`:

```javascript
// Pure, DOM-free helpers for the events page. Imported by app.js and the tests.

// Parse a machine line "{{tool evt-003 | hidden=no | calendar=no | recurrence=none | image=auto}}".
// Returns null if the text is not a tool line.
export function parseToolLine(line) {
  const m = /\{\{tool\s+([a-z0-9-]+)\s*\|(.*?)\}\}/.exec(line);
  if (!m) return null;
  const fields = { id: m[1], hidden: false, calendar: false, recurrence: null, image: null };
  for (const part of m[2].split("|")) {
    const idx = part.indexOf("=");
    if (idx === -1) continue;
    const k = part.slice(0, idx).trim();
    const v = part.slice(idx + 1).trim();
    if (k === "hidden") fields.hidden = v === "yes";
    else if (k === "calendar") fields.calendar = v === "yes";
    else if (k === "recurrence") fields.recurrence = v && v !== "none" ? v : null;
    else if (k === "image") fields.image = v && v !== "auto" ? v : null;
  }
  return fields;
}

// Inverse of parseToolLine — canonical formatting.
export function buildToolLine(id, fields) {
  const yn = (b) => (b ? "yes" : "no");
  return `{{tool ${id} | hidden=${yn(fields.hidden)} | calendar=${yn(fields.calendar)}` +
    ` | recurrence=${fields.recurrence ?? "none"} | image=${fields.image ?? "auto"}}}`;
}

// Return a new array with overlay decisions applied by id (does not mutate input).
export function mergeOverlay(events, overlay) {
  return events.map((ev) => {
    const o = overlay[ev.id];
    return o && "hidden" in o ? { ...ev, hidden: o.hidden } : ev;
  });
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `node --test posts/montreal_events/events/events-core.test.js`
Expected: `# pass 6`, `# fail 0`.

- [ ] **Step 5: Commit**

```bash
git add posts/montreal_events/events/events-core.js posts/montreal_events/events/events-core.test.js
git commit -m "feat(montreal): pure core helpers for machine-line parse/build + overlay merge

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Google Cloud setup + config + page auth wiring

**Files:**
- Create: `posts/montreal_events/events/config.js`
- Modify: `posts/montreal_events/events/index.html`
- Modify: `posts/montreal_events/events/styles.css`

**Interfaces:**
- Consumes: nothing (code-wise); depends on the manual GCP setup in Step 1.
- Produces: `config.js` exports `GOOGLE_CLIENT_ID` and `DOC_ID`; `index.html` loads GIS, loads `app.js` as a module, and has `#auth-btn` and `#hidden-toggle` elements for Task 4 to wire.

- [ ] **Step 1: One-time Google Cloud setup (manual — user performs, free, no billing)**

Do this once in the Google Cloud console signed in as the doc owner:
1. **Create a project** at console.cloud.google.com (name e.g. `montreal-events`).
2. **APIs & Services → Enabled APIs & services → + Enable APIs** → search **Google Docs API** → Enable. (No billing prompt; if one appears, it is not required for the Docs API — skip it.)
3. **APIs & Services → OAuth consent screen**: User type **External** → app name + your email → **Add scope** `https://www.googleapis.com/auth/documents` → **Test users**: add your Gmail and your wife's Gmail → Save. Leave **Publishing status: Testing** (no verification needed).
4. **APIs & Services → Credentials → + Create credentials → OAuth client ID** → Application type **Web application** → **Authorized JavaScript origins**: add `https://nicholastacik.github.io` and `http://localhost:8899` → Create → **copy the Client ID** (ends `.apps.googleusercontent.com`).
5. **Share the events Doc** with your wife's Google account as **Editor** (you already own it).

- [ ] **Step 2: Create config.js with the client ID**

Create `posts/montreal_events/events/config.js` (paste the real client ID from Step 1.4 — it is public and safe to commit):

```javascript
// Public OAuth config. The client ID is not a secret; there is no client secret
// in the browser flow. DOC_ID is the events Google Doc.
export const GOOGLE_CLIENT_ID = "PASTE_CLIENT_ID_HERE.apps.googleusercontent.com";
export const DOC_ID = "15o4_PIve4R0K3Wgle58lUCxQwmDLBCiMn6f4M0FVOV4";
```

- [ ] **Step 3: Wire the page for auth**

In `posts/montreal_events/events/index.html`:

(a) Add the GIS loader in `<head>`, after the stylesheet link:

```html
  <script src="https://accounts.google.com/gsi/client" async defer></script>
```

(b) In the `<header>`, after the `<p id="freshness" hidden></p>` line, add:

```html
    <button id="auth-btn" hidden>Sign in to edit</button>
```

(c) In `<nav>`, after the `<div id="chips" ...></div>` line, add:

```html
    <button id="hidden-toggle" hidden></button>
```

(d) Change the script tag at the bottom from `<script src="app.js"></script>` to:

```html
  <script type="module" src="app.js"></script>
```

- [ ] **Step 4: Add minimal styles**

Append to `posts/montreal_events/events/styles.css`:

```css
#auth-btn { margin-top: .5rem; }
#hidden-toggle { align-self: flex-start; }
.hide-btn { margin-left: .9rem; }
.card.is-hidden { opacity: .55; }
```

- [ ] **Step 5: Verify the page still loads and the button shows**

```bash
python3 -m http.server 8899 --directory posts/montreal_events/events & sleep 1
curl -s -o /dev/null -w "%{http_code}\n" http://localhost:8899/config.js
curl -s http://localhost:8899/ | grep -c 'id="auth-btn"'
kill %1
```
Expected: `200` and `1`. (Full sign-in is exercised in Task 5 after Task 4 wires the logic.)

- [ ] **Step 6: Commit**

```bash
git add posts/montreal_events/events/config.js posts/montreal_events/events/index.html posts/montreal_events/events/styles.css
git commit -m "feat(montreal): OAuth config + GIS loader + auth/hidden-toggle scaffolding

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: Hide/unhide write + optimistic overlay + filtering

**Files:**
- Modify: `posts/montreal_events/events/app.js` (full rewrite)

**Interfaces:**
- Consumes: `parseToolLine`, `buildToolLine`, `mergeOverlay` from `events-core.js`; `GOOGLE_CLIENT_ID`, `DOC_ID` from `config.js`; the `#auth-btn` / `#hidden-toggle` elements from Task 3.
- Produces: the finished E1 page behavior. No new exports.

- [ ] **Step 1: Rewrite app.js**

Replace the entire contents of `posts/montreal_events/events/app.js` with:

```javascript
// Montreal events page. Reads ./events.json (committed by the update skill).
// Signed-in editors (Google accounts with edit access to the source doc) can
// hide/unhide events; the change writes hidden=yes/no to the doc's {{tool ...}}
// line via the Docs API, with an optimistic localStorage overlay for instant feedback.
import { parseToolLine, buildToolLine, mergeOverlay } from "./events-core.js";
import { GOOGLE_CLIENT_ID, DOC_ID } from "./config.js";

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
const OVERLAY_KEY = "montreal_overlay";
const DOCS_SCOPE = "https://www.googleapis.com/auth/documents";

const state = { view: "all", categories: new Set(), showHidden: false };
let events = [];
let overlay = loadOverlay();
let accessToken = null;
let tokenClient = null;

const $ = (sel) => document.querySelector(sel);
const escapeHtml = (s) => String(s).replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const parseDate = (s) => (s ? new Date(s + "T00:00:00") : null);
const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
const addDays = (d, n) => { const c = new Date(d); c.setDate(c.getDate() + n); return c; };
const dayMs = 86400000;

// ---- overlay persistence ----
function loadOverlay() {
  try { return JSON.parse(localStorage.getItem(OVERLAY_KEY)) || {}; }
  catch { return {}; }
}
function saveOverlay() { localStorage.setItem(OVERLAY_KEY, JSON.stringify(overlay)); }
function pruneOverlay() {
  // Drop overlay entries the committed data already reflects (rebuild caught up).
  for (const ev of events) {
    const o = overlay[ev.id];
    if (o && "hidden" in o && !!(ev.hidden) === !!o.hidden) delete overlay[ev.id];
  }
  saveOverlay();
}
// events.json + hidden default + overlay applied
function resolved() {
  return mergeOverlay(events.map((ev) => ({ hidden: false, ...ev })), overlay);
}

// ---- date/window helpers ----
function weekendWindow() {
  const t = today();
  const dow = t.getDay();
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
  if (!start && !end) return false;
  return (start ?? new Date(0)) <= win[1] && (end ?? start) >= win[0];
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

// ---- card ----
function card(ev) {
  const title = escapeHtml(ev.title);
  const description = escapeHtml(ev.description);
  const notes = ev.notes ? escapeHtml(ev.notes) : null;
  const location = ev.location ? escapeHtml(ev.location) : null;
  const url = ev.url ? escapeHtml(ev.url) : null;
  const meta = [CATEGORY_LABELS[ev.category], fmtRange(ev), location]
    .filter(Boolean).join(" · ");
  const links = [];
  if (url) {
    links.push(`<a href="${url}" rel="noopener">Website</a>`);
    if (ev.url_ok === false)
      links.push(`<span class="dead-link">⚠ link may be dead</span>`);
  }
  if (ev.location) {
    const q = encodeURIComponent(`${ev.location}, Montréal, QC`);
    links.push(`<a href="https://www.google.com/maps/search/?api=1&query=${q}" rel="noopener">Map</a>`);
  }
  const hideBtn = accessToken
    ? `<button class="hide-btn" data-id="${ev.id}">${ev.hidden ? "Unhide" : "Hide"}</button>`
    : "";
  const inner = links.join(" ") + hideBtn;
  return `<article class="card${ev.hidden ? " is-hidden" : ""}">
    <h2>${title}${badges(ev)}</h2>
    <p class="meta">${meta}</p>
    <p>${description}${notes ? ` <em>${notes}</em>` : ""}</p>
    ${inner ? `<div class="links">${inner}</div>` : ""}
  </article>`;
}

// ---- render ----
function render() {
  const win = windowFor(state.view);
  const all = resolved();
  const hiddenCount = all.filter((ev) => ev.hidden).length;
  const visible = all
    .filter((ev) => state.showHidden || !ev.hidden)
    .filter((ev) => inView(ev, win))
    .filter((ev) => !state.categories.size || state.categories.has(ev.category))
    .sort((a, b) =>
      STATUS_ORDER[a.status] - STATUS_ORDER[b.status] ||
      (a.end_date ?? "9999").localeCompare(b.end_date ?? "9999") ||
      a.title.localeCompare(b.title));
  $("#list").innerHTML = visible.length
    ? visible.map(card).join("")
    : `<p class="meta">Nothing matches — try widening the filters.</p>`;
  const toggle = $("#hidden-toggle");
  if (!hiddenCount) { toggle.hidden = true; }
  else { toggle.hidden = false; toggle.textContent = state.showHidden ? `Hide ${hiddenCount} hidden` : `Show ${hiddenCount} hidden`; }
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
  if (days > STALE_DAYS) { el.classList.add("stale"); el.textContent += ` — this data is ${days} days old.`; }
}

// ---- hide / unhide ----
async function toggleHide(id) {
  const ev = resolved().find((e) => e.id === id);
  if (!ev) return;
  const next = !ev.hidden;
  overlay[id] = { ...(overlay[id] || {}), hidden: next }; // optimistic
  saveOverlay(); render();
  try {
    await writeHidden(id, next);
  } catch (err) {
    overlay[id] = { ...(overlay[id] || {}), hidden: !next }; // revert
    saveOverlay(); render();
    alert(err.message || "Couldn't save the change.");
  }
}

async function writeHidden(id, hidden) {
  const token = await ensureToken();
  const auth = { Authorization: `Bearer ${token}` };
  const getRes = await fetch(`https://docs.googleapis.com/v1/documents/${DOC_ID}`, { headers: auth });
  if (getRes.status === 403) throw new Error("You don't have edit access to the events doc.");
  if (!getRes.ok) throw new Error(`Docs read failed (${getRes.status}).`);
  const doc = await getRes.json();
  const text = docPlainText(doc);
  const m = new RegExp(`\\{\\{tool ${id} \\|[^}]*\\}\\}`).exec(text);
  if (!m) throw new Error("Couldn't find this event in the doc.");
  const oldLine = m[0];
  const newLine = buildToolLine(id, { ...parseToolLine(oldLine), hidden });
  if (newLine === oldLine) return;
  const upd = await fetch(`https://docs.googleapis.com/v1/documents/${DOC_ID}:batchUpdate`, {
    method: "POST",
    headers: { ...auth, "Content-Type": "application/json" },
    body: JSON.stringify({ requests: [{ replaceAllText: {
      containsText: { text: oldLine, matchCase: true }, replaceText: newLine } }] }),
  });
  if (!upd.ok) throw new Error(`Docs write failed (${upd.status}).`);
  const out = await upd.json();
  if (!(out.replies?.[0]?.replaceAllText?.occurrencesChanged > 0))
    throw new Error("The event line changed in the doc — reload and retry.");
}

function docPlainText(doc) {
  let s = "";
  for (const el of doc.body?.content || [])
    for (const pe of el.paragraph?.elements || [])
      s += pe.textRun?.content || "";
  return s;
}

// ---- auth (Google Identity Services) ----
function initAuth() {
  if (!window.google?.accounts?.oauth2) { setTimeout(initAuth, 300); return; }
  tokenClient = google.accounts.oauth2.initTokenClient({
    client_id: GOOGLE_CLIENT_ID, scope: DOCS_SCOPE, callback: () => {},
  });
  const btn = $("#auth-btn");
  btn.hidden = false;
  btn.addEventListener("click", () => { ensureToken().catch(() => {}); });
}
function ensureToken() {
  return new Promise((resolve, reject) => {
    if (accessToken) return resolve(accessToken);
    if (!tokenClient) return reject(new Error("Sign-in isn't ready yet."));
    tokenClient.callback = (resp) => {
      if (resp.error) return reject(new Error("Sign-in failed."));
      accessToken = resp.access_token;
      $("#auth-btn").textContent = "Signed in ✓";
      render();
      resolve(accessToken);
    };
    tokenClient.requestAccessToken();
  });
}

// ---- wiring ----
$("#views").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-view]");
  if (!btn) return;
  state.view = btn.dataset.view;
  document.querySelectorAll("#views button").forEach((b) => b.classList.toggle("active", b === btn));
  render();
});
$("#hidden-toggle").addEventListener("click", () => { state.showHidden = !state.showHidden; render(); });
$("#list").addEventListener("click", (e) => {
  const b = e.target.closest(".hide-btn");
  if (b) toggleHide(b.dataset.id);
});

// ---- boot ----
initAuth();
fetch("./events.json")
  .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
  .then((data) => {
    events = data.events;
    pruneOverlay();
    renderFreshness(data.last_updated);
    renderChips();
    render();
  })
  .catch(() => { $("#list").innerHTML = `<p class="error">Couldn't load events data. Try refreshing.</p>`; });
```

- [ ] **Step 2: Syntax-check and re-run the core tests**

Run: `node --check posts/montreal_events/events/app.js && node --test posts/montreal_events/events/events-core.test.js`
Expected: no syntax error; `# pass 6`.

- [ ] **Step 3: Smoke-test the page loads and merges overlay (no auth needed)**

```bash
python3 -m http.server 8899 --directory posts/montreal_events/events & sleep 1
curl -s http://localhost:8899/events.json | node -e 'let s="";process.stdin.on("data",d=>s+=d).on("end",()=>{const d=JSON.parse(s);console.log("events",d.events.length)})'
kill %1
```
Expected: prints a positive event count (the page reads the same file). Open `http://localhost:8899/` in a browser and confirm: cards render, view/chip filters still work, and no console errors (the module + imports load).

- [ ] **Step 4: Commit**

```bash
git add posts/montreal_events/events/app.js
git commit -m "feat(montreal): sign-in, hide/unhide write-to-doc, optimistic overlay, hidden filter

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 5: Manual end-to-end verification

**Files:**
- Modify: `posts/montreal_events/notes/BUILD_NOTES.md`

**Interfaces:**
- Consumes: the whole E1 build + the completed Task 3 GCP setup.
- Produces: recorded verification results. No code.

- [ ] **Step 1: Precondition check**

Confirm the doc has at least one entry carrying a `{{tool <id> ...}}` line (ChatGPT's backfill). If not, wait for the backfill or add one line by hand to a single card for the test. Confirm `config.js` has the real client ID.

- [ ] **Step 2: Run the e2e checklist in a browser**

Serve locally (`python3 -m http.server 8899 --directory posts/montreal_events/events`) and open `http://localhost:8899/`. Verify, recording pass/fail for each:
1. Page loads and lists events **without** signing in (public view works).
2. Click **Sign in to edit**, complete Google sign-in as an **editor** account (click through the "unverified app" screen). Button shows **Signed in ✓**; **Hide** buttons appear on cards.
3. Click **Hide** on an event whose doc card has a `{{tool}}` line → the card dims/disappears immediately (optimistic overlay), and a **Show N hidden** toggle appears.
4. In the Google Doc, confirm that event's line now reads `hidden=yes`.
5. Reload the page → the event stays hidden (overlay persisted in localStorage); **Show N hidden** reveals it; **Unhide** returns it and flips the doc line back to `hidden=no`.
6. Run the pipeline once (`/update-montreal-events`, or just re-extract) so `events.json` reflects `hidden:true`; reload → the event is hidden from committed data and the overlay entry self-prunes (verify `localStorage.montreal_overlay` no longer lists that id).
7. Sign in with a **non-editor** Google account and click Hide → it reverts with "You don't have edit access to the events doc."

- [ ] **Step 3: Record results**

Append an E1 section to `posts/montreal_events/notes/BUILD_NOTES.md` under `## Build log`: the checklist outcomes, the client ID's project name, and anything that surprised you (useful for the eventual E2–E4 and any blog follow-up).

- [ ] **Step 4: Commit**

```bash
git add posts/montreal_events/notes/BUILD_NOTES.md
git commit -m "docs(montreal): E1 auth+write e2e verification notes

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

## Notes for the executor

- **Do not push.** All commits stay local; the user decides when/whether to push `main`.
- Tasks 1 and 2 are pure/offline and fully unit-tested — do them first regardless.
- Task 3 Step 1 (GCP console) is the one human-only step; if the executor is an agent, surface it to the user and wait for the client ID before writing `config.js`.
- Task 4 is a full `app.js` rewrite; the pure logic it relies on is already covered by Task 2's tests, so its own verification is the manual checklist in Task 5.
