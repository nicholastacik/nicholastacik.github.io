import { z } from "zod";
import type { GameState } from "./types";
import { remainingWords } from "./engine";

export const ClueSchema = z.object({
  reasoning: z.string(),
  clue: z.string(),
  number: z.number().int(),
  targets: z.array(z.string()),
});
export type ClueResponse = z.infer<typeof ClueSchema>;

export const GuessSchema = z.object({
  reasoning: z.string(),
  guesses: z.array(z.string()),
});
export type GuessResponse = z.infer<typeof GuessSchema>;

const norm = (w: string) => w.trim().toUpperCase();

export function validateClue(resp: ClueResponse, state: GameState): { ok: boolean; violations: string[] } {
  const violations: string[] = [];
  const clue = resp.clue.trim();
  if (clue.length === 0 || /\s|-/.test(clue)) violations.push("clue must be exactly one word");

  const board = new Set(state.words.map(norm));
  if (board.has(norm(clue))) violations.push("clue must not be a word on the board");

  if (resp.number !== resp.targets.length) violations.push("number must equal the count of targets");

  const aiGreens = new Set(
    state.words.filter((_, i) => state.keys.ai[i] === "green" && !state.revealed[i]).map(norm),
  );
  for (const t of resp.targets) {
    if (!aiGreens.has(norm(t))) violations.push(`target "${t}" is not one of your remaining agents`);
  }
  return { ok: violations.length === 0, violations };
}

// Validate a clue the HUMAN typed against the same rules the AI's clues obey:
// exactly one word, not a word on the board, and a positive whole number.
// (No target check — the human doesn't declare targets.)
export function validateHumanClue(
  clue: string,
  num: number,
  state: GameState,
): { ok: boolean; violations: string[] } {
  const violations: string[] = [];
  const c = clue.trim();
  if (c.length === 0 || /\s|-/.test(c)) violations.push("the clue must be exactly one word");
  if (new Set(state.words.map(norm)).has(norm(c))) violations.push("the clue can't be a word on the board");
  if (!Number.isInteger(num) || num < 1) violations.push("the number must be a whole number of at least 1");
  return { ok: violations.length === 0, violations };
}

export function filterGuesses(guesses: string[], state: GameState): string[] {
  const canonical = new Map(remainingWords(state).map((w) => [norm(w), w]));
  const out: string[] = [];
  const seen = new Set<string>();
  for (const g of guesses) {
    const key = norm(g);
    const word = canonical.get(key);
    if (word && !seen.has(key)) { out.push(word); seen.add(key); }
  }
  return out;
}
