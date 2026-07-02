---
name: cryptic-crossword
description: >-
  Turn a photo or PNG of a cryptic crossword into a self-contained, interactive HTML puzzle
  you can solve in the browser — typeable grid, keyboard + mobile support, clue navigation,
  a full answer key (Check / Reveal), and progressive wordplay hints. Use this whenever the
  user shares an image of a cryptic crossword (or any blocked crossword) and wants to play
  it, make it interactive/editable, digitize it, "turn it into a webpage", or post it to a
  blog/site (e.g. nicholastacik.github.io). The skill solves the puzzle and writes the hints,
  and is careful never to print spoilers (answers, solution grid, or hint text) to the terminal.
---

# Cryptic Crossword → Interactive HTML

This skill converts an image of a cryptic crossword into one self-contained HTML file: a
grid you can type into (auto-sizing cells, arrow-key nav, mobile clue strip pinned above
the keyboard), the Across/Down clue lists, an answer key behind Check/Reveal buttons, and
per-clue progressive hints that teach the wordplay without giving the answer away.

The heavy lifting — the UI — lives in a bundled template; each puzzle is just data. Your
job is to read the puzzle from the image, solve it, write the hints, and let the build
script assemble the page.

## The one rule that shapes everything: no spoilers in the terminal

The person who opens this HTML wants to *solve* the crossword. If the answers or hints
show up in the chat/terminal while you build it, that's ruined. So:

- **Do all solving and hint-writing inside a subagent.** Its context holds the spoilers;
  it writes the files and returns only a spoiler-free summary. Your main-thread messages
  never contain answers, the solution grid, or hint text.
- Reading the grid and clues is fine to discuss (that's the puzzle, visible in the image).
  The **solution** and the **hints** are the spoilers to protect.

## Workflow

### 1. Find the image and confirm where to save

You need the crossword image as a **file on disk** (the subagent reads it by path). Users
usually paste a PNG that has a source path, or give you one. If you only have an inline
attachment with no path, ask the user for the file path (or save it) before continuing.

Ask where to save the HTML. Default directory: `~/Work/nicholastacik.github.io/posts/cryptic_crossword`.
Default filename: `cryptic_{date}.html`, where `{date}` is today's date as `YYYY-MM-DD`
(get it with `date +%F`) — e.g. `~/Work/nicholastacik.github.io/posts/cryptic_crossword/cryptic_2026-07-02.html`.
Confirm the directory and filename with the user, offering that default.

### 2. Dispatch the worker subagent

Spawn a subagent to do the entire build in isolation. Give it:

- the **skill directory path** (so it can find `scripts/` and `references/pipeline.md`),
- the **image path**,
- the **output HTML path** you confirmed.

Tell it to read `references/pipeline.md` and follow it exactly, and to return **only** a
spoiler-free summary (grid size, clue counts, "crossings consistent", output path) — no
answers, no solution grid, no hint text.

A prompt like:

> Build an interactive HTML cryptic crossword. Skill dir: `<SKILL>`. Image: `<IMAGE>`.
> Output: `<TARGET>`. Read `<SKILL>/references/pipeline.md` and follow every step:
> detect the grid from pixels, transcribe the clues (zoom in on the enumerations),
> solve the whole puzzle using the crossings as verification, write two-tier hints,
> assemble `puzzle.json`, and run `scripts/build.py` to produce the HTML. These answers
> and hints are spoilers: keep them in files only, and in your final message report ONLY
> the grid size, number of across/down clues, that all crossings and enumerations are
> consistent, and the output path — never any answer letters, the solution grid, or hint text.

### 3. Report back

Relay the subagent's spoiler-free summary and the output path. If the save directory is a
blog post, mention they may want an accompanying `.qmd`/index or a link — but don't add one
unless asked. Offer to open the file in a browser.

## What's in this skill

- `scripts/detect_grid.py` — samples the image to get the black/white pattern (with a
  symmetry check and ASCII rendering to verify). Reading a blocked grid by eye misplaces
  squares; sampling pixels is reliable.
- `scripts/build.py` — fills the template from a `puzzle.json` and **validates** the puzzle
  (black/solution alignment, every entry has a clue, enumerations match entry lengths). It
  prints only structure, never answers.
- `assets/template.html` — the full interactive player (do not hand-edit per puzzle; it's
  filled by `build.py`). Edit it only to change the UI for *all* future puzzles.
- `references/pipeline.md` — the detailed, ordered build steps the worker follows.

## Dependencies

The scripts use `pillow`, `numpy`, and `scipy` (for grid auto-detection); run them with
`uv run --with pillow --with numpy --with scipy ...` so no global install is needed.
Rendering to verify (optional) needs a headless browser (e.g. Google Chrome with
`--headless=new --screenshot`).
