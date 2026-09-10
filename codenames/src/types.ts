export type Category = "green" | "bystander" | "assassin";
export type KeyCard = Category[]; // length 25, indexed by board position
export interface KeyCardPair { human: KeyCard; ai: KeyCard; }
export type Player = "human" | "ai";

export interface HistoryTurn {
  clueGiver: Player;
  clue: string;
  number: number;
  guesses: string[];       // canonical board words, in guess order
  outcomes: Category[];    // category on the clue-giver's card for each guess
}

export interface SuddenDeathGuess {
  word: string;
  by: Player;
  outcome: Category;
}

export interface GameState {
  words: string[];                 // 25 canonical (uppercase) words
  keys: KeyCardPair;
  revealed: boolean[];             // 25; true once a word is covered
  agentsFound: number;             // 0..15
  turnsRemaining: number;          // starts at 9; exhausting it with <15 agents found enters sudden death
  clueGiver: Player;               // who gives the next clue
  phase: "awaitClue" | "awaitGuess";
  currentClue: { word: string; number: number; guessesMade: number } | null;
  status: "playing" | "won" | "lost";
  history: HistoryTurn[];
  suddenDeath: boolean;            // true once the timer runs out with agents left
  suddenDeathGuesses: SuddenDeathGuess[]; // guesses made during sudden death
}

export const TOTAL_AGENTS = 15;
export const START_TURNS = 9;
