# Codenames Duet — Sudden Death — Design

**Date:** 2026-09-10
**Status:** Approved pending user review

## Overview

Re-introduce the **sudden-death** endgame we cut at launch, in a form that works
with a human + AI partner. When the 9-turn timer runs out with agents still
hidden, instead of an immediate loss the game enters sudden death: no more clues,
both sides make one last clue-less attempt using only the clues already given,
and **any wrong guess — bystander or assassin — ends the game.**

The design centres on a **co-pilot** interaction: the AI surfaces a
**confidence meter** for its next guess, and the human orchestrates the endgame
by either firing the AI's pick ("AI guess") or making their own guess (clicking a
cell), in any order.

## Why this needs a specific design (the load-bearing constraint)

In real Duet both players still see their own key card in sudden death, but are
**"not allowed to discuss a guessing strategy."** That rule exists because each
player, seeing their own card, knows the answers to the *partner's* guesses.

With an AI partner this becomes a concrete exploit: **the AI's guesses are judged
against the human's key card, which the human can see.** If the human both sees
their card and controls when the AI guesses, they'd only ever fire the AI on a
word they can see is safe — the AI would never miss, trivialising half the
endgame.

**Resolution: hide the human's key-card shading during sudden death.** The human
never needs it for their *own* guesses (those target the AI's agents, inferred
from the AI's clues, not the human's card) — its only sudden-death use is to
oracle the AI. Hiding it makes every guess a genuine gamble. Symmetrically, the
AI's confidence is derived **only from the clue history**, never from its own
card, so it can't oracle the human either.

## Sudden-death rules (as implemented)

- **Trigger:** the moment the timer would otherwise cause a loss — the last timer
  token is spent (`turnsRemaining` reaches 0) with `agentsFound < 15`. Instead of
  `status = "lost"`, set `suddenDeath = true` and keep `status = "playing"`.
- **No clues.** Neither side gives clues in sudden death.
- **Both are guessers, any order, no turns.** A guess is judged against the
  **non-guesser's** card (matching Duet: "when your partner touches a word, *your*
  side of the key card determines whether the guess is correct"):
  - a **human** guess (cell click) is judged against the **AI's** card,
  - an **AI** guess is judged against the **human's** card.
- **A green guess** covers the word and counts toward the 15; guessing continues.
- **Any non-green guess** (bystander *or* assassin, by either side) → **both lose
  immediately.**
- **Win** when `agentsFound` reaches 15. There is **no pass** — you guess until
  you win or miss.

## The AI's sudden-death guessing (the meter)

On entering sudden death, a single AI call produces the AI's ranked reading of
which unrevealed words are the **human's** agents, from the accumulated clue
history only:

- New prompt (`prompts.ts`): a sudden-death system prompt explaining "no clues
  left; from ALL clues so far, rank the remaining words by how confident you are
  each is one of your partner's agents; any wrong guess loses, so lead with your
  most confident."
- New schema (`validate.ts`): `SuddenDeathSchema = { reasoning: string; guesses:
  Array<{ word: string; confidence: number }> }` (confidence in `[0, 1]`).
- New function (`ai.ts`): `getSuddenDeathGuesses(caller, state, log)` → returns a
  validated, board-filtered, ranked `Array<{ word, confidence }>` (only words
  currently on the board and unrevealed; deduped; order preserved).

**One call for the whole phase.** The ranked list is over the AI's target pool
(the human's agents), which is independent of the human's own guessing, so it
does not need re-fetching as words fall — the UI just skips any candidate that
has since been revealed. The AI-turn **busy guard** applies to this fetch.

## The co-pilot UI (`ui.ts`)

When `state.suddenDeath` is true:

- **Turn header:** "SUDDEN DEATH — no clues left. Any wrong guess loses."
- **Key-card shading is hidden** (force off regardless of the "Show my key card"
  toggle) — the oracle fix above.
- **Remaining-agent counts** (identity-free, so no oracle): "You still need X of
  the AI's agents · the AI still needs Y of yours", where X = unrevealed greens on
  the AI's card and Y = unrevealed greens on the human's card. These are values a
  Duet player legitimately knows (their own card + the running total); we surface
  the counts without revealing *which* words.
- **The confidence meter:** shows the AI's top unrevealed candidate and its
  confidence (e.g. a bar + "AI wants to guess **CRANE** — 85%"), with an **"AI
  guess"** button that fires that pick. Showing the target word is safe (the human
  can't verify it — their card is hidden — and it targets the human's agents, not
  the AI's, so it doesn't help the human's own clicks).
- **Two ways to guess, any order:** click a cell (your own read of the AI's
  clues, judged against the AI's card) or press "AI guess" (the AI's top pick,
  judged against your card). You sequence them — highest-confidence first.
- **Game log:** each sudden-death guess is logged with its result (✅ agent / 💥
  loss), attributed to you or the AI.
- **Rules panel:** add a sudden-death bullet.

Normal-turn controls (clue bar, "Get the AI's clue", "End guessing", "Pass") are
hidden in sudden death.

## Engine changes (`engine.ts`, `types.ts`)

- `GameState` gains `suddenDeath: boolean` (re-added); `createGame` initialises it
  `false`.
- **Entering sudden death:** where `endTurn`/`passTurn` currently set
  `status = "lost"` at `turnsRemaining === 0`, instead set `suddenDeath = true`
  (leaving `status = "playing"`) when `agentsFound < 15`.
- **Sudden-death guess:** a guesser-aware entry point, e.g.
  `suddenDeathGuess(state, word, guesser: Player): GameState`:
  - no-op unless `status === "playing" && suddenDeath` and the word is on the
    board and not revealed;
  - judge against the **non-guesser's** card (`guesser === "human"` → `keys.ai`;
    `guesser === "ai"` → `keys.human`);
  - **green** → `revealed = true`, `agentsFound += 1`, win at 15;
  - **bystander or assassin** → `status = "lost"`.
  - Each sudden-death guess is recorded (word, guesser, outcome) so the board can
    render found agents (✅) and the AI's sudden-death prompt knows what's already
    been tried. (Exact storage — a dedicated field vs. history entries — is a
    plan-level decision; it must not pollute `formatHistory` used for clue prompts
    with fake clues.)
- Pure and immutable as with the rest of the engine (`structuredClone`, no
  mutation of the input).

## Controller (`main.ts`)

- On any transition into `suddenDeath` (after an `endTurn`/`passTurn` that trips
  it), fetch the AI's ranked list once via `getSuddenDeathGuesses` (busy-guarded,
  `LLMError` → `ui.setError`), and hand it to the UI for the meter.
- New action `aiSuddenDeathGuess()` — apply `suddenDeathGuess(state, topWord,
  "ai")` for the current top unrevealed candidate; log the result; win/loss.
- `clickCell` in sudden death routes to `suddenDeathGuess(state, word, "human")`
  (instead of the normal clue-based `guess`); log; win/loss.
- The generation guard and busy guard behave as in normal play.

## Testing

- **Engine:** timer-out with agents remaining enters sudden death (not loss);
  win-at-15 still works to end the game before sudden death; a sudden-death human
  guess is judged against the AI's card and an AI guess against the human's card;
  a green sudden-death guess counts an agent and continues; a bystander *and* an
  assassin each lose in sudden death; reaching 15 in sudden death wins.
- **AI layer:** `getSuddenDeathGuesses` returns a ranked, board-filtered list with
  valid confidences (fake caller; no network).
- **Controller:** entering sudden death triggers one ranked fetch; "AI guess"
  applies the top candidate; a human click in sudden death applies against the AI
  card; a wrong guess loses; 15 wins. Re-entrancy / stale guards hold.
- **UI:** sudden-death header text; shading hidden even with the toggle on; the
  remaining-agent counts render; the meter shows the top candidate + confidence
  and "AI guess" fires `onAiGuess`; normal-turn controls hidden.

All AI is mocked in tests; no live API.

## Decisions made (easy to revisit)

- **Hide the human's card in sudden death** (vs. keep it) — required to prevent
  the oracle exploit; costs the human nothing legitimate.
- **One ranked AI call** for the whole phase (vs. per-guess re-eval) — cheaper and
  fast; the target pool is independent of the human's guesses.
- **"AI guess" fires only on the human's press** (vs. the AI auto-playing) — the
  human orchestrates order to manage risk, which is the co-pilot experience.
- **Show the AI's target word + confidence** (vs. confidence only) — richer, and
  safe because the card is hidden.

## Out of scope

- True simultaneous/real-time guessing (we keep it turn-free but one guess at a
  time, driven by button presses).
- Any change to the normal-play turn loop beyond the trigger and control-hiding.
- Multiplayer beyond the single human + AI.
