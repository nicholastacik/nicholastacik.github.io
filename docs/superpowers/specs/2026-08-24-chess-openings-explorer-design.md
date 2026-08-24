# Chess Openings Explorer — Design

**Date:** 2026-08-24
**Status:** Approved (design), pending implementation plan

## Purpose

Nick is learning chess and wants to study opening theory. Openings are
usually written as bare move sequences, which are hard to follow and
visualize. This project makes them **walkable**: an interactive web page
where you step through an opening move-by-move on a real board, read a
short explanation at each step, and branch into variations via a
variation tree.

Three outcomes:
1. An interactive web page hosting many openings with explanations.
2. A Claude skill to add a new opening to the page.
3. A blog post describing why and how it was built.

## Scope

**In scope (v1):**
- Guided step-through of an opening on a board (Next/Prev + arrow keys).
- Variation tree sidebar; click any node to jump the board there.
- Per-move prose annotations; per-study intro.
- A landing page listing all studies with search/filter.
- A Claude skill that drafts a new opening study from Claude's own
  opening knowledge, given a name (+ optional focus).
- Test suite that guarantees every shipped study is legal chess.
- A blog post.

**Out of scope (v1), deliberately:**
- Drill / "test me" mode (user plays the moves from memory). Natural
  future extension.
- Engine evaluation bars / Stockfish integration.
- PGN import UI.
- User accounts / persistence.
- Custom board arrows/circles UI (an optional schema field is reserved
  for annotations but no authoring/rendering UI is built for it in v1).

## Key decisions

- **Stack: Vite + TypeScript SPA**, mirroring the existing `codenames/`
  project. Chosen over a no-build single-file app for type safety,
  tests, and consistency with the site's heavier interactive project.
- **Studies stored as moves + prose only** (no precomputed FENs). Under
  a bundled app, `chess.js` is available for free, so the app replays
  SAN at load time to derive positions. This keeps study files
  human-readable and eliminates an enrich/precompute build step. (Under
  a no-build app the opposite call — precompute FENs at author time —
  would have been better; the bundle flips the calculus.)
- **Self-contained studies.** Each opening is one independent JSON file
  with its own move tree. Shared early moves are duplicated across
  studies; that is accepted in exchange for simple, independent
  authoring and a trivial skill (drop in one file).
- **Validation lives in the test suite.** Illegal moves fail
  `npm test`, not the browser. This is what makes the "Claude drafts
  the theory" skill trustworthy: legality is guaranteed even though the
  theory *choices* are Claude's.
- **Skill drafts from Claude's knowledge.** User provides a name and
  optional focus; Claude generates the tree + annotations; user
  reviews. Legality is machine-checked; correctness of theory is the
  user's review responsibility.

## Architecture & layout

A Vite/TS single-page app in `chess/`, built to a static bundle that
Quarto copies into the site — exactly the `codenames/` pattern:

- `vite build` outputs to `../posts/chess/app` (via
  `build.outDir` in `vite.config.ts`, `base: "./"`).
- `_quarto.yml` gains `posts/chess/app/**` under `resources:`.
- `posts/chess/index.qmd` is the blog post; it links to `app/`.
- Pushing to `main` triggers the existing GitHub Action that renders
  and publishes the site.

```
chess/
  index.html
  package.json          # scripts: dev, build (tsc --noEmit && vite build), test
  vite.config.ts        # base "./", outDir ../posts/chess/app, vitest jsdom
  tsconfig.json         # strict, noUncheckedIndexedAccess (match codenames)
  src/
    main.ts             # hash router: #/ (landing) vs #/study/<id>
    studies/            # one JSON per opening (moves + prose only)
    study.ts            # zod schema + load/parse; replay SAN via chess.js
    tree.ts             # tree navigation: next/prev/mainline/flatten/path
    board.ts            # chessground wrapper (set position, flip, last-move)
    ui.ts               # landing list + study view rendering
    style.css
  tests/
    schema.test.ts
    integrity.test.ts
    tree.test.ts
```

**Dependencies:** `chessground` (Lichess board renderer — rendering
only, no chess logic), `chess.js` (move legality + SAN → position).
**Dev:** `typescript`, `vite`, `vitest`, `jsdom`, `zod`.

## Data model

Studies are authored as moves + prose. The app replays them to derive
positions; no FENs are stored.

```json
{
  "id": "italian-game",
  "name": "Italian Game",
  "eco": "C50",
  "side": "white",
  "intro": "The Italian aims for quick development and a grip on f7...",
  "line": [
    { "san": "e4", "comment": "Stake the center." },
    { "san": "e5" },
    { "san": "Nf3", "comment": "Attacks e5, develops." },
    {
      "san": "Nc6",
      "alts": [
        {
          "san": "Nf6",
          "comment": "The Petrov — a different world.",
          "line": [ /* ...continuation... */ ]
        }
      ]
    }
  ]
}
```

**Node** = `{ san, comment?, nag?, alts?, shapes? }`.
- `line`: the mainline sequence (array of nodes).
- `alts`: sibling variations at a given node; each alt is itself a node
  that begins its own `line` continuation.
- `san`: standard algebraic notation for the move that reaches this node.
- `comment`: optional prose annotation for the position after this move.
- `nag`: optional annotation glyph (`!`, `!?`, `?!`, …). Reserved.
- `shapes`: optional board arrows/circles for annotations. Reserved for
  future; validated if present but no v1 UI.

**Study metadata:** `id` (slug, matches filename), `name`, `eco`
(optional), `side` (`"white" | "black" | "both"` — sets default board
orientation), `intro` (prose shown at the root position).

A **zod schema** in `study.ts` defines and validates this shape.
Studies are auto-discovered via `import.meta.glob` — no manifest file.

## Tree navigation (`tree.ts`)

Pure functions over the study tree, independently testable:
- Flatten a study into an addressable set of nodes, each with a path.
- `next`/`prev` along the current line.
- Enter/switch among a node's `alts` (up/down or click).
- Resolve a node path → the SAN sequence to replay for its position.

Position derivation: given a node's SAN path, replay from the start
position with `chess.js` to produce the FEN and the last-move squares.

## UI & navigation

**Landing page (`#/`):**
- Cards per study: name, ECO, side.
- Search/filter box (by name/ECO).
- Hash routing so each study has a shareable URL; browser Back works.

**Study view (`#/study/<id>`):**
- Board (chessground) on the left; **flip** button, defaulting to the
  study's `side` (flipped for Black repertoires). Last move highlighted.
- **Variation tree** sidebar: mainline bold, variations indented,
  current node highlighted, click to jump.
- **Annotation panel**: current node's `comment`; falls back to the
  study `intro` at the root.
- **Controls**: ⏮ Prev / Next ⏭ buttons **plus keyboard**: ←/→ step
  along the current line; ↑/↓ (or click) switch among a node's alts.

## The "add an opening" skill

Project skill at `.claude/skills/chess-opening/` (alongside the
existing `cryptic-crossword` skill).

Flow:
1. Invoked with an opening name + optional focus (e.g. "Najdorf,
   Black's side, main lines only").
2. Claude drafts the move tree + annotations from opening theory and
   writes a new `chess/src/studies/<id>.json`.
3. Skill runs `npm test` — the integrity test replays every move with
   `chess.js` and fails on any illegal move, so broken lines cannot
   ship silently.
4. Skill runs `npm run build` and reports the new study for the user to
   review.

No manifest to maintain (studies auto-discovered via glob).

**Caveat baked into the skill:** legality is machine-guaranteed, but the
*theory choices* are Claude's — the user must sanity-check the lines and
prose. The skill must state this in its output.

## Testing (vitest + jsdom)

- **Schema** (`schema.test.ts`): every study file parses against the
  zod schema.
- **Study integrity** (`integrity.test.ts`): load all studies, replay
  every SAN move (mainline and all alts) with `chess.js`, assert each
  is legal from its position. This is the gate that makes the skill
  trustworthy.
- **Tree navigation** (`tree.test.ts`): next/prev/branch-switching and
  path→SAN resolution over a fixture tree.

## Blog post

`posts/chess/index.qmd` with front matter (title, date, categories).
Content: the *why* (learning openings by walking them, not reading move
lists) and the *how* (the study-as-moves-plus-prose model, the tree
sidebar, the runtime-replay vs precompute decision, and the Claude skill
that drafts new openings with test-enforced legality). Prominent link
into the live app.

## Risks & mitigations

- **Claude's opening theory may be wrong or dated.** Mitigation:
  legality is test-enforced; the skill explicitly flags theory as
  needing human review; each study is small and independently
  reviewable.
- **chessground/chess.js API drift.** Mitigation: thin wrapper
  (`board.ts`) isolates chessground; `chess.js` usage confined to
  `study.ts`/replay.
- **Study count growth.** Self-contained files + glob discovery scale
  linearly; landing-page search keeps it navigable.
