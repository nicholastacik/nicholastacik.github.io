import type { Category, GameState, KeyCard, Player } from "./types";
import { TOTAL_AGENTS, START_TURNS } from "./types";
import { WORDS } from "./words";
import { generateKeyCardPair } from "./keycards";

function shuffle<T>(arr: T[], rng: () => number): T[] {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [a[i], a[j]] = [a[j]!, a[i]!];
  }
  return a;
}

export function createGame(opts: {
  rng?: () => number; words?: string[]; firstClueGiver?: Player;
} = {}): GameState {
  const rng = opts.rng ?? Math.random;
  const pool = opts.words ?? WORDS;
  const words = shuffle(pool, rng).slice(0, 25);
  return {
    words,
    keys: generateKeyCardPair(rng),
    revealed: Array(25).fill(false),
    agentsFound: 0,
    turnsRemaining: START_TURNS,
    suddenDeath: false,
    clueGiver: opts.firstClueGiver ?? "human",
    phase: "awaitClue",
    currentClue: null,
    status: "playing",
    history: [],
  };
}

export function giverKey(state: GameState): KeyCard {
  return state.clueGiver === "human" ? state.keys.human : state.keys.ai;
}

export function remainingWords(state: GameState): string[] {
  return state.words.filter((_, i) => !state.revealed[i]);
}

export function aiGreenWordsRemaining(state: GameState): string[] {
  return state.words.filter((_, i) => state.keys.ai[i] === "green" && !state.revealed[i]);
}

export function giveClue(state: GameState, clue: string, number: number): GameState {
  const next = structuredClone(state);
  next.phase = "awaitGuess";
  next.currentClue = { word: clue, number, guessesMade: 0 };
  next.history.push({
    clueGiver: state.clueGiver, clue, number, guesses: [], outcomes: [],
  });
  return next;
}

function endTurn(state: GameState): GameState {
  const next = state;
  next.phase = "awaitClue";
  next.currentClue = null;
  next.clueGiver = next.clueGiver === "human" ? "ai" : "human";
  next.turnsRemaining -= 1;
  if (next.turnsRemaining <= 0 && next.status === "playing") next.suddenDeath = true;
  return next;
}

export function guess(state: GameState, word: string): GameState {
  const next = structuredClone(state);
  const idx = next.words.findIndex((w) => w === word);
  if (idx < 0 || next.revealed[idx] || next.status !== "playing") return next;

  const cat: Category = giverKey(next)[idx]!;
  next.revealed[idx] = true;
  const turn = next.history[next.history.length - 1];
  if (turn) { turn.guesses.push(word); turn.outcomes.push(cat); }

  if (cat === "assassin") { next.status = "lost"; return next; }
  if (cat === "green") {
    next.agentsFound += 1;
    if (next.agentsFound >= TOTAL_AGENTS) { next.status = "won"; return next; }
    if (next.suddenDeath) { next.clueGiver = next.clueGiver === "human" ? "ai" : "human"; return next; }
    next.currentClue!.guessesMade += 1;
    if (next.currentClue!.guessesMade >= next.currentClue!.number + 1) return endTurn(next);
    return next;
  }
  // bystander
  if (next.suddenDeath) { next.status = "lost"; return next; }
  return endTurn(next);
}

export function endGuessing(state: GameState): GameState {
  if (state.status !== "playing" || state.phase !== "awaitGuess") return state;
  return endTurn(structuredClone(state));
}
