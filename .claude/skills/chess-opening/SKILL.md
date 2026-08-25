---
name: chess-opening
description: Add a new chess opening to the Chess Openings Explorer (the Vite app in chess/). Use when the user wants to add, create, or draft an opening / variation study for the interactive openings page — e.g. "add the Sicilian Najdorf", "create a French Defense study", "add an opening to the chess explorer". Drafts the move tree and annotations from opening theory, writes a validated study JSON, and rebuilds.
---

# Add a Chess Opening

Draft a new opening as a self-contained study for the Chess Openings Explorer
(the Vite/TS app in `chess/`). Each study is one JSON file of moves + prose;
the app replays the moves to render positions, and the test suite enforces that
every move is legal.

## Inputs

Ask the user for (or take from their request):
- The opening **name** (e.g. "Sicilian Najdorf").
- Optional **focus**: which side's repertoire (White/Black/both), and how deep
  (main lines only, or key sidelines too). Default: the mainline plus 1–2 of the
  most important variations, ~8–12 plies deep.

## Steps

1. **Choose an id.** Slugify the name to match `^[a-z0-9-]+$` (e.g.
   `sicilian-najdorf`). The file MUST be `chess/src/studies/<id>.json`.

2. **Draft the study** from your own opening knowledge. Produce this exact JSON
   shape:

   ```json
   {
     "id": "sicilian-najdorf",
     "name": "Sicilian Najdorf",
     "eco": "B90",
     "side": "black",
     "intro": "2–4 sentences: the ideas, pawn structure, and what each side wants.",
     "line": [
       { "san": "e4", "comment": "Explain the move's purpose." },
       { "san": "c5" },
       { "san": "Nf3", "comment": "…",
         "alts": [
           [ { "san": "Nc3", "comment": "A different move order or system." } ]
         ] }
     ]
   }
   ```

   Rules:
   - `line` is the mainline: an array of move nodes played in sequence.
   - A node is `{ san, comment?, nag?, alts? }`. `alts` is a list of alternative
     *lines* branching at that node's ply — each alt is itself an array of nodes
     (a continuation). Use alts for the important divergences a learner should
     see, not every sideline.
   - `nag` and `shapes` are optional and **reserved for a future annotations feature** — they are validated and stored but not rendered in the current version. Use `comment` for prose annotations.
   - `side` sets the default board orientation: use `"black"` for Black
     repertoires so the board starts from Black's view.
   - Write `comment` as short, concrete teaching notes ("controls d5", "prepares
     …", "the point of the whole system"). Not every node needs a comment;
     annotate the instructive ones.
   - **SAN dialect** (must match `chess.js`): castling `O-O` / `O-O-O` (letter O,
     not zero), promotion `e8=Q`, captures `exd5` / `Nxe5`, disambiguation
     `Nbd2`, check `+`, mate `#`. Do NOT include move numbers inside `san`.

3. **Write the file** to `chess/src/studies/<id>.json`.

4. **Validate — this is the gate.** Run:
   ```bash
   cd chess && npm test
   ```
   The integrity test replays every move with `chess.js`. If it reports an
   illegal move (e.g. "Illegal move Nf3 after e4 e5"), you made a theory or SAN
   error — fix the offending move(s) in the JSON and re-run until the suite is
   green. Never ship a study that fails the suite.

5. **Build:**
   ```bash
   cd chess && npm run build
   ```

6. **Report to the user** with this caveat, verbatim in spirit:
   > The moves are machine-verified as legal, but the *opening theory and the
   > choice of lines are my draft* — please review the variations and the prose
   > for accuracy before relying on them.

   Show the user the study id and the lines you included so they can spot-check.

## Notes

- No manifest to update — studies are auto-discovered via `import.meta.glob`.
- Keep studies focused: one opening/family per file. Shared early moves being
  duplicated across studies is fine and expected.
- Do not modify app code (`src/*.ts`) — this skill only adds a study JSON.
