// Dev-only self-play harness: plays the AI against itself (both clue-giver and
// guesser roles) for N games and prints aggregate quality metrics. Never run
// in tests or CI — invoke via `npm run eval [-- N]`.
import { createGame, giveClue, guess, endGuessing, passTurn } from "../src/engine";
import { getAIClue, getAIGuess, OpenAICaller } from "../src/ai";
import type { GameState } from "../src/types";
import { aggregate, type GameResult } from "./metrics";

const DEFAULT_MODEL = "gpt-5.6";
// Each engine step (a clue, or a single guess) advances the game by at least
// one turn-relevant action; 9 turns * a generous per-turn budget is nowhere
// near this, so hitting the cap means something is stuck, not that a normal
// game ran long.
const MAX_STEPS_PER_GAME = 500;

async function playOneGame(apiKey: string, model: string): Promise<GameResult> {
  const caller = new OpenAICaller({ apiKey, model });

  let clues = 0;
  let illegalClues = 0;
  let repairs = 0;
  const log = (line: string): void => {
    if (/Illegal AI clue/.test(line)) illegalClues += 1;
    if (/asking again/.test(line)) repairs += 1;
  };

  let state: GameState = createGame();

  for (let step = 0; step < MAX_STEPS_PER_GAME && state.status === "playing"; step++) {
    if (state.phase === "awaitClue") {
      const clue = await getAIClue(caller, state, log);
      if (clue === null) {
        state = passTurn(state);
      } else {
        clues += 1;
        state = giveClue(state, clue.clue, clue.number);
      }
    } else if (state.phase === "awaitGuess") {
      const { guesses: words } = await getAIGuess(caller, state, log);
      for (const word of words) {
        if (state.phase !== "awaitGuess" || state.status !== "playing") break;
        state = guess(state, word);
      }
      // Mirror the controller: the returned list IS how many the AI chose to
      // guess. If the turn didn't already end (wrong guess / number+1 cap / win),
      // the AI has stopped — end the turn so eval matches real gameplay instead
      // of re-asking for guesses on the same clue.
      if (state.status === "playing" && state.phase === "awaitGuess") {
        state = endGuessing(state);
      }
    }
  }

  const hitAssassin = state.history.some((t) => t.outcomes.includes("assassin"));
  return {
    won: state.status === "won",
    agentsFound: state.agentsFound,
    hitAssassin,
    clues,
    illegalClues,
    repairs,
  };
}

function printTable(agg: ReturnType<typeof aggregate>): void {
  const rows: [string, string][] = [
    ["games", String(agg.games)],
    ["win rate", agg.winRate.toFixed(3)],
    ["avg agents found", agg.avgAgents.toFixed(2)],
    ["assassin rate", agg.assassinRate.toFixed(3)],
    ["illegal clue rate", agg.illegalClueRate.toFixed(3)],
    ["avg repairs / clue", agg.avgRepairsPerClue.toFixed(3)],
  ];
  const width = Math.max(...rows.map(([k]) => k.length));
  console.log("");
  for (const [k, v] of rows) console.log(`${k.padEnd(width)} : ${v}`);
  console.log("");
}

async function main(): Promise<void> {
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    console.error("OPENAI_API_KEY is not set. Export it before running `npm run eval`.");
    process.exit(1);
  }
  const model = process.env.OPENAI_EVAL_MODEL ?? DEFAULT_MODEL;
  const n = Number.parseInt(process.argv[2] ?? "10", 10) || 10;

  const results: GameResult[] = [];
  for (let i = 0; i < n; i++) {
    console.log(`Playing game ${i + 1}/${n}...`);
    results.push(await playOneGame(apiKey, model));
  }

  printTable(aggregate(results));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
