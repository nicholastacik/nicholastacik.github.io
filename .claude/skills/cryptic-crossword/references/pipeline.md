# Build pipeline (worker instructions)

You are building an interactive HTML crossword from an image. Everything here happens
in your context only — the answers and hints you produce are **spoilers** and must never
appear in your final message back to the caller. Return only structure (see the end).

Work from the skill directory: `<SKILL>` = the cryptic-crossword skill folder.

## 1. Detect the grid (pixels, not eyeballing)

Run the detector on the image:

```
uv run --with pillow --with numpy --with scipy python3 <SKILL>/scripts/detect_grid.py <IMAGE>
```

It prints JSON (`{"n","bbox","black","symmetric"}`) on stdout and an ASCII rendering on
stderr. Trust two checks: `symmetric` should be `true` (nearly all published cryptics have
180° rotational symmetry), and the ASCII should match the image's black squares.

If it looks off, the auto-detected bounding box or size is wrong. Re-run with explicit
values you read from the image — `--bbox L,T,R,B` (pixel coords of the grid's outer edges)
and `--size N` (grid is N×N; default 15, but 13×13 and others exist). Iterate until the
ASCII matches the image and it's symmetric.

## 2. Read the clues (zoom in — small print misleads)

Read every clue's **number, text, and enumeration** from the image. The parenthetical
enumeration `(4,6)` is easy to misread at thumbnail scale (6 vs 8, 4 vs 6), so crop and
upscale the clue columns before transcribing — e.g. with Pillow, crop the Across/Down
regions and resize ~4–8×, then read those crops. Preserve any italics in clue text as
`<i>...</i>` (setters italicize foreign words, etc.).

You'll cross-check these enumerations against the grid in step 5 — mismatches there almost
always mean a misread enumeration or a misread grid cell.

## 3. Solve the puzzle (crossings are the proof)

Solve every clue. The interlock is your correctness guarantee: build the full solution
grid so that **every white cell agrees between its across and down entry**. When wordplay
and a crossing disagree, re-examine — a confident cryptic solve (e.g. an unambiguous
anagram or charade) usually settles it, and a length that doesn't match the enumeration
means the answer or the grid is wrong.

Produce a `solution` grid: N strings, `#` for black cells, uppercase A–Z for letters,
exactly aligned with the `black` grid.

## 4. Write the hints (teach the mechanism, don't give the word)

For each clue, write two escalating nudges:

- **t1** — name the device(s) and where the definition sits. Point at the indicator
  words. Don't decode yet.
- **t2** — the full wordplay breakdown, but stop just short of stating the answer.

Keep them one or two sentences. The goal is to help someone *see* the clue, not hand them
the solution — t2 should make the answer derivable without printing it.

**Example** (for an imaginary clue "Retreat that's found in a bunker (3)", answer DEN):
- t1: `Definition: "Retreat". A hidden word — it's concealed in the clue.`
- t2: `Hidden inside "bunKER"... look again — it's spanning "a bunker".`

Match the device vocabulary to what's actually there: reversal, anagram, hidden word,
homophone, charade, container/insertion, Spoonerism, deletion, Roman numerals, initial/
final letters, double definition, &lit.

## 5. Assemble puzzle.json and build

Write a `puzzle.json` (UTF-8) with this shape:

```json
{
  "title": "Cryptic Crossword",
  "n": 15,
  "black":    ["#.#...", "...", "..."],
  "solution": ["#A#...", "...", "..."],
  "across": { "7": ["Love <i>città</i> to the west", "(4)"], "8": ["...", "(4,6)"] },
  "down":   { "1": ["...", "(10)"] },
  "hints": {
    "across": { "7": {"t1": "...", "t2": "..."} },
    "down":   { "1": {"t1": "...", "t2": "..."} }
  }
}
```

Notes:
- `across`/`down` keys are clue numbers (as strings); values are `[clue_text, enumeration]`.
- `title` shows in the page header and browser tab. A date or source is nice, e.g.
  `"Cryptic Crossword — The Observer, 2026-06-20"`. Keep it spoiler-free.
- Then build:

```
uv run --with pillow python3 <SKILL>/scripts/build.py --puzzle puzzle.json --out <TARGET_HTML>
```

`build.py` validates before writing: black/solution alignment, every entry has a clue,
every enumeration matches its entry length, every clue maps to an entry. If it reports a
mismatch (e.g. "13 across: grid length 8 != enumeration (6)"), fix the underlying cause —
usually a misread grid cell (rerun step 1 with a better bbox) or a misread enumeration
(recheck step 2). It prints only structure, never answers.

## 6. (Optional) sanity-render

If a headless browser is available you can screenshot the output to confirm it renders,
but don't spend long — `build.py`'s validation already guarantees structural correctness.

## 7. Return a spoiler-free summary

Report back ONLY: grid size, number of across/down clues, that all crossings/enumerations
are consistent, and the output path. Never include answer letters, the solution grid, or
hint text — the whole point is that the person opening the HTML gets to solve it.
