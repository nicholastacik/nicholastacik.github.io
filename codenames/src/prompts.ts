import type { GameState } from "./types";
import { remainingWords, aiGreenWordsRemaining } from "./engine";

export type ChatMessage = { role: "system" | "user" | "assistant"; content: string };

const RULES = `You are an expert cooperative partner in Codenames Duet.
Your team wins by contacting all 15 agents together before the timer runs out.
Two dangers: guessing a BYSTANDER ends the turn; guessing an ASSASSIN loses the game instantly.`;

export const CLUE_SYSTEM = `${RULES}

Your job now: give ONE single-word clue and a NUMBER for the agents you want your
partner to guess. Rules for a legal clue:
- exactly one word, no spaces or hyphens;
- must NOT be any word currently on the board;
- the NUMBER must equal how many target words you list.

Strategy: prefer a SAFE clue that connects a few of your agents over an ambitious
clue that could point at the assassin or a bystander. Think before you answer;
put your thinking in "reasoning" first, then commit to "clue", "number", "targets".

Example — board has APPLE, ORANGE, KING, QUEEN; your agents are APPLE, ORANGE.
Good answer: reasoning "APPLE and ORANGE are both fruit and neither royal word is my agent",
clue "FRUIT", number 2, targets ["APPLE","ORANGE"].`;

export const GUESS_SYSTEM = `${RULES}

Your job now: your partner gave a one-word clue and a number. Choose which words on
the board they most likely mean, RANKED best-first, at most number+1 guesses. You do
NOT know the key card — infer from the clue. Put your thinking in "reasoning" first,
then list "guesses" (exact board words). Stop early rather than risk a wild guess.`;

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

export function buildClueMessages(state: GameState): ChatMessage[] {
  const green = aiGreenWordsRemaining(state).join(", ");
  const user = `${boardBlock(state)}

Your agents (words your partner must find from YOUR clues): ${green}
Turns remaining: ${state.turnsRemaining}${state.suddenDeath ? " (SUDDEN DEATH)" : ""}

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
Turns remaining: ${state.turnsRemaining}${state.suddenDeath ? " (SUDDEN DEATH)" : ""}

Game so far:
${formatHistory(state)}

Make your guesses now (best first, at most ${clue.number + 1}).`;
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
