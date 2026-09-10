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

// A clue is illegal if it's a board word, is contained in one, or contains one
// (e.g. HERO with SUPERHERO on the board). Returns the conflicting board word,
// or null. Board words are all >= 3 chars, so this won't fire on trivial overlaps.
function boardWordConflict(clue: string, state: GameState): string | null {
  const c = norm(clue);
  if (c.length === 0) return null;
  for (const w of state.words) {
    const b = norm(w);
    if (c === b || c.includes(b) || b.includes(c)) return w;
  }
  return null;
}

export function validateClue(resp: ClueResponse, state: GameState): { ok: boolean; violations: string[] } {
  const violations: string[] = [];
  const clue = resp.clue.trim();
  if (clue.length === 0 || /\s|-/.test(clue)) violations.push("clue must be exactly one word");

  const conflict = boardWordConflict(clue, state);
  if (conflict) violations.push(`clue must not be, contain, or be part of a board word (conflicts with "${conflict}")`);

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
  const conflict = boardWordConflict(c, state);
  if (conflict) violations.push(`the clue can't be, contain, or be part of a board word (conflicts with "${conflict}")`);
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

export const SuddenDeathSchema = z.object({
  reasoning: z.string(),
  guesses: z.array(z.object({ word: z.string(), confidence: z.number() })),
});
export type SuddenDeathResponse = z.infer<typeof SuddenDeathSchema>;

export function filterSuddenDeathGuesses(
  guesses: Array<{ word: string; confidence: number }>,
  state: GameState,
): Array<{ word: string; confidence: number }> {
  const canonical = new Map(remainingWords(state).map((w) => [norm(w), w]));
  const out: Array<{ word: string; confidence: number }> = [];
  const seen = new Set<string>();
  for (const g of guesses) {
    const key = norm(g.word);
    const word = canonical.get(key);
    if (word && !seen.has(key)) {
      out.push({ word, confidence: Math.max(0, Math.min(1, g.confidence)) });
      seen.add(key);
    }
  }
  return out;
}
