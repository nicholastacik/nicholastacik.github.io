import type { GameState } from "./types";
import { remainingWords, giverWordsRemaining } from "./engine";

export type ChatMessage = { role: "system" | "user" | "assistant"; content: string };

const RULES = `You are an expert cooperative partner in Codenames Duet.
You and your human partner each hold a DIFFERENT key card. You win together by
contacting all 15 agents (the union of both cards) before the shared turn timer runs out.
Two dangers: guessing a BYSTANDER ends the turn; guessing an ASSASSIN loses the game instantly.
If the timer runs out with agents still hidden, no more clues can be given — you both
make final guesses from the clues already given (sudden death), where a single wrong
guess loses. So use each clue turn to convey as much as you safely can while it lasts.`;

export const CLUE_SYSTEM = `${RULES}

Your job now: give ONE single-word clue and a NUMBER for the agents you want your
partner to guess. Rules for a legal clue:
- exactly one word, no spaces or hyphens;
- must NOT be any word on the board, nor contained in one, nor contain one
  (e.g. do NOT clue "HERO" if SUPERHERO is on the board);
- the NUMBER must equal how many target words you list.

Strategy: you will be told which remaining words are your AGENTS, your ASSASSINS,
and your BYSTANDERS. Prefer familiar meanings and direct associations your partner
can recognise from the clue alone — not elaborate links that only make sense once
explained. Before committing, weigh every assassin and bystander against your clue:
if your partner could plausibly read the clue as pointing at one of them, or it fits
one as well as your agents, choose a safer clue. An assassin match is fatal and
outweighs any number of agents, so when a clue is even somewhat risky, cluing fewer
agents — or a different pair — is usually better. In "reasoning", briefly note the
main associations and any competing dangerous words, then commit to "clue", "number",
"targets".

Example — board has APPLE, ORANGE, BANANA, KING; your agents are APPLE and ORANGE, and
BANANA is your ASSASSIN. "FRUIT" for 2 is tempting, but BANANA is just as much a fruit — a
fatal match. Better: find a clue that fits BOTH agents yet clearly not BANANA — APPLE and
ORANGE are round while a banana is long and curved, so "SPHERICAL" for 2 keeps both agents
and dodges the assassin. Only if no such separating clue exists should you retreat to a
safe single like "CIDER" for 1 (APPLE alone) — cluing fewer still beats risking the
assassin. Good answer: reasoning "SPHERICAL fits round APPLE and ORANGE, and a banana is
plainly not round, so my partner won't reach for BANANA", clue "SPHERICAL", number 2,
targets ["APPLE","ORANGE"].`;

export const GUESS_SYSTEM = `${RULES}

Your job now: your partner gave a one-word clue and a number. Choose which words on
the board they most likely mean, RANKED best-first. You do NOT see any key card —
infer from the clues.

Reading the history: each player has a different key card, and every outcome shown
refers to the card of whoever GAVE that clue. Your guesses this turn are judged
against your PARTNER's card — so look for leftover agents among your PARTNER's earlier
clues, never your own (your own clues described YOUR card). A word that ended a turn
as a bystander for one of you may still be an agent on the other card. Only 9 of the
25 words are agents on your partner's card; the other 16 are bystanders or assassins
(3 of them fatal), so an unclued word is far more likely to be a miss — guess only
what the clues actually support.

In "reasoning", briefly explain the main associations and any competing words, then
list "guesses" (exact board words).

How many to guess:
- The number is how many words THIS clue points to. Guess those, most-confident first.
- You may make ONE extra "bonus" guess (number+1 total), but ONLY for an agent you are
  confident your PARTNER pointed at in an EARLIER clue and left unfound — never to
  gamble on a loose association with the current clue.
- If you have no such confident leftover, STOP after the clue's number.
- A wrong guess ends the turn, and the assassin loses the game outright — so caution
  beats greed. When unsure, guess fewer.`;

export function formatHistory(state: GameState): string {
  if (state.history.length === 0) return "(no turns yet)";
  return state.history
    .map((t) => {
      const res = t.guesses.map((g, i) => `${g}=${t.outcomes[i]}`).join(", ") || "(no guesses)";
      return `${t.clueGiver} clued "${t.clue}" ${t.number} -> ${res}`;
    })
    .join("\n");
}

function boardBlock(state: GameState): string {
  return `Words still in play: ${remainingWords(state).join(", ")}`;
}

// English ordinal suffix: 1st, 2nd, 3rd, 4th … 11th/12th/13th, 21st, …
function ordinal(n: number): string {
  const rem100 = n % 100;
  if (rem100 >= 11 && rem100 <= 13) return `${n}th`;
  const suffix = ["th", "st", "nd", "rd"][n % 10] ?? "th";
  return `${n}${suffix}`;
}

export function buildClueMessages(state: GameState): ChatMessage[] {
  const green = giverWordsRemaining(state, "green").join(", ");
  const assassins = giverWordsRemaining(state, "assassin").join(", ") || "(none remaining)";
  const bystanders = giverWordsRemaining(state, "bystander").join(", ") || "(none remaining)";
  const user = `${boardBlock(state)}

Your agents — steer your partner toward these (each is +1 toward the 15): ${green}
ASSASSINS on YOUR key card — ${assassins}. A touch here loses the game instantly; reject any clue your partner could plausibly read as pointing at one.
BYSTANDERS on YOUR key card — ${bystanders}. A touch here ends the turn with nothing found; avoid clues that fit one as well as your agents.
Turns remaining: ${state.turnsRemaining}

Game so far:
${formatHistory(state)}

Give your clue now.`;
  return [
    { role: "system", content: CLUE_SYSTEM },
    { role: "user", content: user },
  ];
}

export function buildGuessMessages(state: GameState): ChatMessage[] {
  const clue = state.currentClue!;
  const user = `${boardBlock(state)}

Your partner's clue: "${clue.word}" for ${clue.number}.
Turns remaining: ${state.turnsRemaining}

Game so far:
${formatHistory(state)}

Make your guesses now: up to ${clue.number} for this clue, best-first — plus a ${ordinal(clue.number + 1)} bonus guess ONLY if you're confident about an agent left over from an earlier clue.`;
  return [
    { role: "system", content: GUESS_SYSTEM },
    { role: "user", content: user },
  ];
}

export function repairMessage(violations: string[]): ChatMessage {
  return {
    role: "user",
    content: `That response was illegal: ${violations.join("; ")}. Try again and obey every rule.`,
  };
}

export const SUDDEN_DEATH_SYSTEM = `${RULES}

SUDDEN DEATH: no more clues will be given. From the clues already given during the
game, decide which of the remaining words are your partner's agents. Return a list
RANKED most-confident first, each with a confidence from 0 to 1. A single wrong
guess loses the game — lead with the words you would actually risk, and be honest
about your confidence. In "reasoning", briefly note which earlier clues point to which
words. Remember these are your PARTNER's clues about your PARTNER's agents. Only 9 of
the 25 words are your partner's agents (3 are assassins that lose instantly), so most
words are unsafe — rank conservatively and lead only with words the clues genuinely support.`;

export function buildSuddenDeathMessages(state: GameState): ChatMessage[] {
  const user = `${boardBlock(state)}

Game so far (all clues given):
${formatHistory(state)}

Rank the remaining words now — best first, each with a confidence from 0 to 1.`;
  return [
    { role: "system", content: SUDDEN_DEATH_SYSTEM },
    { role: "user", content: user },
  ];
}
