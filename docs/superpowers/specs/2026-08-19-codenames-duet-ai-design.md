# Codenames Duet vs. an AI Partner — Design

**Date:** 2026-08-19
**Status:** Approved pending user review

## Overview

Build a browser-playable game of **Codenames Duet** (the cooperative two-player
variant) where the second player is an LLM, and ship an interactive Quarto post
about how it was made. The human and the AI alternate roles: one gives a
one-word clue, the other guesses, then they swap. Both sit on the same
cooperative team and race to find all 15 agents before the timer runs out or an
assassin is hit.

The framing is a **"use AI in production" learning exercise**. The interesting
engineering is not the game — it is **getting the model to play well** (good
clues, safe guesses) and the reliability loop around each call
(**interpret → validate → repair**). Clue/guess quality is the intellectual
center; the plumbing is supporting material.

### Deliverables

- An interactive static page where a visitor plays Codenames Duet against an
  LLM partner, running entirely **client-side in the browser**.
- A blog post (`posts/codenames/index.qmd`) narrating the build: clue/guess
  quality as the headline, backed by the static + BYOK architecture and the
  interpret/validate/repair loop with real examples.
- A dev-only offline eval harness that measures clue/guess quality.

### Learning goals (the "why")

- Use an LLM in a real, shipped product.
- **Get *good* clues and guesses out of the model — the intellectual center.**
  Prompt engineering, steering away from the assassin, and measuring quality.
- Interpret model responses reliably.
- Handle invalid or failed responses gracefully.

## The load-bearing constraints

1. **The site is a static Quarto build on GitHub Pages — no server.** There is
   nowhere to hold a secret API key or run a backend. Every LLM call must
   originate in the visitor's browser.
2. **Bring-your-own-key (BYOK).** The visitor pastes their own OpenAI API key;
   the browser calls OpenAI directly. This gives us zero backend, zero cost, and
   zero abuse exposure. The tradeoff — `dangerouslyAllowBrowser: true` and a key
   living in the page — is real and is explained honestly to the player and in
   the post.

Together these two facts mean: **no Python, no proxy, no CI secrets.** All game
logic, response parsing, and validation is client-side TypeScript.

## Provider & model

- **Provider:** OpenAI (`openai` npm SDK, instantiated with
  `dangerouslyAllowBrowser: true` and the visitor's key).
- **Structured Outputs:** every model call uses
  `response_format: { type: "json_schema", strict: true }` (via the SDK's typed
  `.parse()` helper with a zod schema). Grammar-constrained decoding guarantees
  schema-valid JSON — we never write a tolerant text parser.
- **Model:** UI-configurable text field, defaulting to a current
  Structured-Outputs-capable model. The exact default id is verified at
  implementation time (model ids drift); the field lets the player override it.

## Architecture & file layout

Vanilla **TypeScript** built with **Vite**, no UI framework. TypeScript is
chosen deliberately: typed game state and typed AI-response schemas are the
backbone of the "interpret responses" goal, and Vite gives TS for free.

- `codenames/` (repo root) — the Vite project and source of truth, mirroring the
  existing `jeopardy/` / `ptcg/` root-folder convention:
  - `src/engine.ts` — pure Duet rules + board/key-card/turn state. No DOM, no
    network.
  - `src/keycards.ts` — generates a valid Duet key-card pair.
  - `src/ai.ts` — OpenAI interaction layer: prompt construction, SDK calls,
    typed response parsing.
  - `src/prompts.ts` — versioned role-specific system prompts + few-shot
    examples (the clue/guess-quality levers).
  - `src/validate.ts` — rule-legality checks + the bounded repair loop.
  - `src/ui.ts` — DOM rendering + event wiring (the *only* file that touches the
    DOM).
  - `src/main.ts` — wires engine ↔ ai ↔ ui together.
  - `src/words.ts` — curated word list (~400 words).
  - `tests/` — Vitest specs (mocked AI, no live API).
  - `eval/` — dev-only offline eval harness (`npm run eval`, developer's key).
  - `package.json`, `vite.config.ts`, `tsconfig.json`.
- `posts/codenames/index.qmd` — the blog write-up.
- `posts/codenames/app/` — committed Vite `dist/` output, copied into the site
  verbatim via a new `resources:` entry in `_quarto.yml`.

Each unit has one purpose and a clear boundary: `engine.ts` knows nothing about
the network or DOM; `ai.ts` knows nothing about the DOM; `ui.ts` is the only
DOM consumer. This keeps the engine and validation layers fully unit-testable
without a browser or a live API.

## Game engine (`engine.ts` + `keycards.ts`)

Faithful Duet. 25 words drawn from `words.ts`. Two key cards — the human's and
the AI's — modeled as a 25×2 category grid where each cell is one of
`green | bystander | assassin` per player. The key-card pair must satisfy the
official Duet contingency table (rows = your card, cols = partner's card):

| your card ↓ / partner → | green | bystander | assassin |
|---|---|---|---|
| **green**     | 3 | 5 | 1 |
| **bystander** | 5 | 7 | 1 |
| **assassin**  | 1 | 1 | 1 |

This yields **9 greens and 3 assassins per card**, **15 unique agents to find**
(3 + 5 + 1 + 5 + 1), and **5 words that are an assassin to at least one player**
(with 1 mutual assassin). The exact mutual-assassin cell value is verified
against the official Duet rules during implementation and locked with a test;
if the official distribution differs, the table and the test move together.

State the engine tracks:
- The 25 words and the two key cards.
- Which cells have been revealed (and by which guess).
- Whose turn it is (clue-giver vs. guesser alternates).
- The **9-turn timer track** and the **sudden-death** phase when it runs out.
- Terminal state: **win** (all 15 agents found) or **loss** (an assassin is
  revealed, or the timer + sudden death end with agents remaining).

The engine is pure: given a state and a move, it returns the next state. No
randomness beyond board/key-card setup (seedable for tests).

## AI interaction layer (`ai.ts`)

Two operations, each a single Structured-Outputs call:

- **AI guesses** (the human gave a clue). Input: the remaining board words, the
  clue word, the number, and game history. Output schema:
  `{ guesses: string[] /* ranked */, reasoning: string }`. The engine reveals
  the guesses in order against the **human's** key card, stopping at the first
  non-agent (Duet's turn-ending rule).
- **AI gives a clue** (its turn). Input: the AI's own key card, the remaining
  board, and history. Output schema:
  `{ clue: string, number: number, targets: string[], reasoning: string }`. The
  human then guesses against the **AI's** key card.

The guesser deliberately is *not* given a key card — in Duet the guesser only
sees the board and infers meaning, exactly as a human partner would.

### Context & history

Every call includes the **game history**, not just current state — a clue-giver
must avoid re-cluing already-found agents and remember what previously failed;
a guesser needs prior clues to disambiguate. History is kept **compact**: only
the structured facts per turn (who, clue word, number, guesses made, outcomes),
**never** the verbose `reasoning` strings. A full 9-turn history is a few hundred
tokens, so it does not need summarizing.

Prompts are structured **cache-first**: the invariant rules + schema + few-shot
examples come first (a stable prefix OpenAI can auto-cache), with the dynamic
board / key-card / history appended last.

### Token cost (BYOK reassurance)

A typical full game is ~12 AI calls (~one per turn + sudden-death/repair extras),
~1,600 input + ~300 output tokens per call → **~19K input + ~3.6K output per
game**. At early-2026 pricing that is roughly **$0.005/game on a mini-class model
(~200 games/$1)** to **~$0.08/game on a flagship model (~12 games/$1)**; prompt
caching lowers the input side further. The dominant cost is the re-sent rules
prompt, not history — which is why the cache-first structure above matters. (Model
ids and exact prices are verified at build time; the token counts are stable.)

## Validation & invalid-response handling — the centerpiece

Structured Outputs guarantees *schema*-valid JSON, so the malformed-text problem
is gone. The real handling splits into two honest categories:

### A. Rule-illegal content (semantic validation, deterministic JS)

Schema-valid responses can still break the game. `validate.ts` checks:

- **Guesser:** every guess is a word currently on the board and not already
  revealed → illegal guesses are filtered out.
- **Clue-giver:** the clue is exactly one word; the clue is not equal to a board
  word; `number` equals `targets.length`; every target is one of the AI's own
  green agents.

On a clue-giver violation → a **bounded repair loop**: re-prompt with the
specific violation appended to the messages (max 2 retries), then fall back to a
deterministic safe move (the AI passes its turn, or emits a minimal legal clue).

**Legality policy: lenient by design.** Validate hard on the things that break
the game — off-board or already-revealed guesses, `number`/`targets` mismatch,
clue-equals-a-board-word. Do **not** attempt perfect linguistic judgment of
"illegal derivative" clues (board `NIGHT`, clue `KNIGHT`/`NIGHTS`): apply at most
a light lowercase + strip + substring heuristic, and let subtle cases slide.
Perfect judgment is hard in any language and is not needed for a fun demo; a
second "referee" LLM call is explicitly out of scope.

### B. API-level failures (the real reliability work)

These are the failure modes that actually occur with Structured Outputs, and
each is handled with ordinary `try/catch` + response inspection in JS:

- **Truncation** (`finish_reason: "length"`): incomplete object. Set a generous
  `max_tokens`; on truncation, retry once, then surface a clear error.
- **Refusal** (the response's `refusal` field is populated): treat as an invalid
  turn; surface it.
- **HTTP errors:** `401` (bad/missing key) and `429` (rate limit) get specific,
  actionable messages; network errors get a generic retry prompt.

Every rejection, repair attempt, and fallback is surfaced in an on-page "AI
reasoning / log" panel so the interpret → validate → repair loop is fully
inspectable — this panel is also the source of the blog post's concrete
examples.

## Clue & guess quality — the intellectual center

The hardest, most interesting problem is not plumbing — it is getting the model
to *play well*: give clues that connect its own agents without pointing at the
assassin, and guess sensibly. This is the primary "use AI in production" lesson
and the headline of the blog post.

Levers (kept in `src/prompts.ts`, versioned so changes are diffable):
- **Role-specific system prompts** stating the objective and the danger (the
  assassin is a hard loss; a bystander merely ends the turn).
- **Few-shot examples** of good clues/guesses on sample boards.
- **Reasoning-before-answer** in the schema (the `reasoning` field precedes the
  `clue`/`guesses`) so the model "thinks" before committing — cheap quality win.
- **Explicit risk framing** for the clue-giver: prefer covering fewer agents
  safely over an ambitious clue that risks the assassin.

These are iterated against the eval harness below rather than by vibes.

## Offline eval harness

A **dev-only** script (not shipped in the bundle, not run in CI) that measures
clue/guess quality so prompt changes are judged by numbers, not vibes.

- Location: `codenames/eval/`, run via `npm run eval`, using the developer's own
  key from an env var (never committed).
- Plays N full self-play games (AI in both roles) and/or scores clue-giving on a
  set of fixture boards.
- Metrics: win rate, agents found per game, **assassin-hit rate**, average
  correct guesses per clue, illegal-clue rate, and repair-loop invocation rate.
- Output: a small summary table feeding the blog post's quality discussion.

## UI / UX & key handling (`ui.ts`)

- Standard 5×5 grid; the human's key card is visible only to the human (green /
  assassin / bystander shading on the human's own view).
- Clue input (word + number) for the human's clue-giving turns.
- An AI reasoning / event log panel (see above).
- A timer track showing turns remaining and the sudden-death state.

**Key handling:** the API key is pasted into a field and held in memory, with an
opt-in to `sessionStorage` (cleared on tab close). It is **never** written to
`localStorage` by default and **never** logged. A visible note explains the
`dangerouslyAllowBrowser` tradeoff and that BYOK means the key stays in the
player's own browser talking directly to OpenAI.

## Build & deploy

- `npm run build` in `codenames/` outputs the bundle to `../posts/codenames/app/`.
- The `dist/` output is **committed** — consistent with the repo's existing
  practice of committing generated output (`_freeze/`). This keeps **Node out of
  CI**: the GitHub Actions workflow stays pure uv + Quarto and simply copies the
  prebuilt app.
- Add `posts/codenames/app/**` to the `resources:` block in `_quarto.yml` so
  Quarto copies the built app into `_site` verbatim (same mechanism as
  `posts/jeopardy_ds/research/**`).

## Testing (Vitest)

Live API calls are never made in tests. Coverage:

- **Engine rules:** turn alternation, sequential reveal stopping at first
  non-agent, timer/sudden-death transitions, win/loss detection.
- **Key-card validity:** the contingency table (9 greens & 3 assassins per card,
  15 unique agents, the assassin overlaps) holds for generated pairs.
- **Validation & repair layer:** fed **mocked** AI responses — legal,
  rule-illegal (recoverable), and unrecoverable (exhausts retries → fallback) —
  plus simulated API-level failures (truncation, refusal, 401, 429).

## Blog post (`posts/codenames/index.qmd`)

The **headline is clue/guess quality**: what makes the model play well, how it
was steered away from the assassin, and the eval-harness numbers showing the
improvement. Supporting material: the static + BYOK architecture and its honest
tradeoff, the token-cost reality (dozens-to-hundreds of games per dollar), and
the reframing of "handling responses" — with Structured Outputs the model always
returned valid JSON, so the real plumbing was semantic legality, truncation,
refusals, and rate limits, not text parsing.

## Decisions made (easy to revisit)

- **TypeScript** over plain JS — typed state and response schemas serve the core
  learning goal.
- **Commit `dist/`** over adding a Node CI step — matches the repo's `_freeze/`
  convention and keeps CI pure uv + Quarto.
- **Lenient clue-legality** over strict linguistic judgment — validate what
  breaks the game, let subtle derivatives slide.

## Out of scope

- Any server, proxy, or hosted key.
- A second "referee" LLM call to judge clue legality.
- Provider abstraction / non-OpenAI providers.
- Persisting games across sessions or multiplayer beyond the single human + AI.
