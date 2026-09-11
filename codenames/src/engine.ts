import type { Category, GameState, KeyCard, Player } from "./types";
import { TOTAL_AGENTS, START_TURNS } from "./types";
import { WORDS } from "./words";
import { generateKeyCardPair } from "./keycards";

// Deterministic PRNG from a string or number seed (mulberry32 over an FNV-1a
// hash). Same seed → same board + key cards, so games are reproducible for
// comparing agents.
export function makeRng(seed: string | number): () => number {
  let s = typeof seed === "number" ? seed | 0 : hashString(seed);
  return () => {
    s = (s + 0x6d2b79f5) | 0;
    let t = Math.imul(s ^ (s >>> 15), 1 | s);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function hashString(str: string): number {
  let h = 2166136261;
  for (let i = 0; i < str.length; i++) {
    h ^= str.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

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
    revealed: Array(words.length).fill(false),
    agentsFound: 0,
    turnsRemaining: START_TURNS,
    clueGiver: opts.firstClueGiver ?? "human",
    phase: "awaitClue",
    currentClue: null,
    status: "playing",
    history: [],
    suddenDeath: false,
    suddenDeathGuesses: [],
  };
}

export function giverKey(state: GameState): KeyCard {
  return state.clueGiver === "human" ? state.keys.human : state.keys.ai;
}

export function remainingWords(state: GameState): string[] {
  return state.words.filter((_, i) => !state.revealed[i]);
}

export function aiWordsRemaining(state: GameState, category: Category): string[] {
  return state.words.filter((_, i) => state.keys.ai[i] === category && !state.revealed[i]);
}

export function aiGreenWordsRemaining(state: GameState): string[] {
  return aiWordsRemaining(state, "green");
}

// Words of a given category on the CURRENT clue-giver's card (keys.ai when the AI
// clues, keys.human when the human clues). The clue prompt must use this so the
// clue matches the card the guesser's touches are judged against (giverKey). This
// is a no-op for the app — getAIClue only ever runs when clueGiver === "ai" — but
// it makes AI-vs-AI self-play (the eval) coherent instead of cluing one card while
// the engine judges against the other.
export function giverWordsRemaining(state: GameState, category: Category): string[] {
  const key = giverKey(state);
  return state.words.filter((_, i) => key[i] === category && !state.revealed[i]);
}

// Words already shown to be BYSTANDERS on the CURRENT clue-giver's card (from
// history — a bystander guess doesn't cover the word, so it's not "revealed").
// A bystander on a card can never be an agent on that SAME card, so the guesser
// must never re-guess it while guessing against this card. It may still be an
// agent on the OTHER card, so this list is keyed to the current clue-giver only.
export function confirmedBystanders(state: GameState): string[] {
  const out = new Set<string>();
  for (const turn of state.history) {
    if (turn.clueGiver !== state.clueGiver) continue;
    turn.guesses.forEach((w, i) => { if (turn.outcomes[i] === "bystander") out.add(w); });
  }
  return [...out];
}

export function giveClue(state: GameState, clue: string, number: number): GameState {
  if (state.status !== "playing") return state;
  const next = structuredClone(state);
  next.phase = "awaitGuess";
  next.currentClue = { word: clue, number, guessesMade: 0 };
  next.history.push({
    clueGiver: state.clueGiver, clue, number, guesses: [], outcomes: [],
  });
  return next;
}

// Unrevealed green count on a player's card — how many of that player's agents
// are still to be found (via the OTHER player guessing this player's clues).
function greensLeft(state: GameState, player: Player): number {
  const key = player === "human" ? state.keys.human : state.keys.ai;
  return key.reduce((n, cat, i) => n + (cat === "green" && !state.revealed[i] ? 1 : 0), 0);
}

function endTurn(state: GameState): GameState {
  const next = state;
  next.phase = "awaitClue";
  next.currentClue = null;
  next.turnsRemaining -= 1;
  // Alternate the clue-giver, but SKIP a player who has no agents left to clue
  // for (Duet: once one side's agents are all found, the other gives all the
  // remaining clues). Otherwise that player burns a timer token on an empty pass,
  // starving the team of productive clue turns before the clock runs out.
  const other: Player = next.clueGiver === "human" ? "ai" : "human";
  next.clueGiver = greensLeft(next, other) > 0 || greensLeft(next, next.clueGiver) === 0
    ? other
    : next.clueGiver;
  // Timer exhausted with agents still hidden → sudden death (not a loss). Win is
  // detected in guess() before endTurn is ever reached, so agentsFound < 15 here.
  if (next.turnsRemaining <= 0 && next.status === "playing" && next.agentsFound < TOTAL_AGENTS) {
    next.suddenDeath = true;
  }
  return next;
}

export function guess(state: GameState, word: string): GameState {
  if (state.status !== "playing") return state;
  if (state.currentClue === null) return state;

  const next = structuredClone(state);
  const idx = next.words.findIndex((w) => w === word);
  if (idx < 0 || next.revealed[idx]) return next;

  const cat: Category = giverKey(next)[idx]!;
  const turn = next.history[next.history.length - 1];
  if (turn) { turn.guesses.push(word); turn.outcomes.push(cat); }

  if (cat === "assassin") { next.revealed[idx] = true; next.status = "lost"; return next; }
  if (cat === "green") {
    next.revealed[idx] = true; // covered — a found agent, counts toward the 15
    next.agentsFound += 1;
    if (next.agentsFound >= TOTAL_AGENTS) { next.status = "won"; return next; }
    next.currentClue!.guessesMade += 1;
    if (next.currentClue!.guessesMade >= next.currentClue!.number + 1) return endTurn(next);
    return next;
  }
  // Bystander — Duet rule: do NOT cover the word. It's tan on the clue-giver's
  // card, but it may be an AGENT on the partner's card, so it stays in play and
  // remains guessable (findable later from the other side). The turn ends,
  // spending a timer token (via endTurn). Only `revealed` means "covered/found".
  return endTurn(next);
}

export function endGuessing(state: GameState): GameState {
  if (state.status !== "playing" || state.phase !== "awaitGuess") return state;
  return endTurn(structuredClone(state));
}

// Advances the turn when a clue-giver passes without giving a clue at all
// (only meaningful while awaiting a clue — there is nothing to "pass" once a
// clue has been given, that's what endGuessing is for).
export function passTurn(state: GameState): GameState {
  if (state.status !== "playing" || state.phase !== "awaitClue") return state;
  return endTurn(structuredClone(state));
}

export function suddenDeathGuess(state: GameState, word: string, guesser: Player): GameState {
  if (state.status !== "playing" || !state.suddenDeath) return state;
  const next = structuredClone(state);
  const idx = next.words.findIndex((w) => w === word);
  if (idx < 0 || next.revealed[idx]) return next;

  // Judged against the NON-guesser's card (Duet: your partner touches, YOUR card judges).
  const judgeKey: KeyCard = guesser === "human" ? next.keys.ai : next.keys.human;
  const cat: Category = judgeKey[idx]!;
  next.suddenDeathGuesses.push({ word, by: guesser, outcome: cat });

  if (cat === "green") {
    next.revealed[idx] = true;
    next.agentsFound += 1;
    if (next.agentsFound >= TOTAL_AGENTS) next.status = "won";
    return next;
  }
  // bystander or assassin → both lose
  next.status = "lost";
  return next;
}
