// Dev-only self-play harness: plays the AI against itself (both clue-giver and
// guesser roles) for N games and prints aggregate quality metrics. Never run
// in tests or CI — invoke via `npm run eval [-- N]`.
import { createGame, giveClue, guess, endGuessing, passTurn, makeRng } from "../src/engine";
import { getAIClue, getAIGuess, OpenAICaller } from "../src/ai";
import { formatHistory } from "../src/prompts";
import { TOTAL_AGENTS, START_TURNS, type GameState } from "../src/types";
import { aggregate, type GameResult } from "./metrics";

const DEFAULT_MODEL = "gpt-5.6";
// Each engine step (a clue, or a single guess) advances the game by at least
// one turn-relevant action; 9 turns * a generous per-turn budget is nowhere
// near this, so hitting the cap means something is stuck, not that a normal
// game ran long.
const MAX_STEPS_PER_GAME = 500;

async function playOneGame(
  apiKey: string, model: string, rng: () => number, label: string, seedKey: string,
): Promise<GameResult> {
  const caller = new OpenAICaller({ apiKey, model });

  let clues = 0;        // clues successfully delivered
  let illegalClues = 0; // clue attempts rejected as illegal (each retry)
  let turnsUsed = 0;    // clue-turns + passes consumed (<= START_TURNS: we stop
                        // at timer-out / sudden death rather than playing overtime)
  let reachedSuddenDeath = false;
  const trace: string[] = []; // full per-turn record, printed under EVAL_LOG=1
  const log = (line: string): void => {
    if (/Illegal AI clue/.test(line)) illegalClues += 1;
  };

  // Live single-line progress so a long game visibly advances (no false "hung").
  const progress = (note: string): void => {
    process.stdout.write(
      `\r${label} · turn ${turnsUsed}/${START_TURNS} · agents ${state.agentsFound}/${TOTAL_AGENTS}` +
      ` · clue#${clues} · ${note}`.padEnd(72),
    );
  };

  // Seeded board so a given (seed, index) always yields the same 25 words + key
  // cards — lets two prompt versions be A/B'd on identical boards (paired).
  let state: GameState = createGame({ rng });

  for (let step = 0; step < MAX_STEPS_PER_GAME && state.status === "playing"; step++) {
    // Timer ran out with agents still hidden → real games enter sudden death
    // (no more clues). The harness doesn't model sudden-death guessing, so end
    // the game here instead of grinding out overtime clues forever.
    if (state.suddenDeath) { reachedSuddenDeath = true; break; }

    if (state.phase === "awaitClue") {
      const giver = state.clueGiver; // card this clue is about + judged against
      progress("thinking of a clue…");
      const clue = await getAIClue(caller, state, log);
      turnsUsed += 1;
      if (clue === null) {
        trace.push(`T${turnsUsed} [${giver} clue] passed / no legal clue`);
        state = passTurn(state);
        progress("passed");
      } else {
        clues += 1;
        trace.push(
          `T${turnsUsed} [${giver} clue] "${clue.clue}" ${clue.number}  ` +
          `targets=[${clue.targets.join(", ")}]  :: ${clue.reasoning}`,
        );
        state = giveClue(state, clue.clue, clue.number);
        progress(`clued "${clue.clue}" ${clue.number}`);
      }
    } else if (state.phase === "awaitGuess") {
      const giver = state.clueGiver;              // guesses judged against this card
      const num = state.currentClue?.number ?? 0; // guesses beyond this are "bonus"
      progress("guessing…");
      const { guesses: words, reasoning } = await getAIGuess(caller, state, log);
      trace.push(`   [guess vs ${giver} card] wants: [${words.join(", ")}]  :: ${reasoning}`);
      let applied = 0;
      for (const word of words) {
        if (state.phase !== "awaitGuess" || state.status !== "playing") break;
        const isBonus = applied >= num;
        state = guess(state, word);
        const cat = state.history[state.history.length - 1]?.outcomes.slice(-1)[0];
        trace.push(`      → ${word} = ${cat}${isBonus ? "  (BONUS guess)" : ""}`);
        applied += 1;
        progress(`guessed ${word}`);
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
  process.stdout.write("\r".padEnd(74) + "\r"); // clear the progress line

  const outcome = reachedSuddenDeath ? "reached sudden death (unfinished)" : state.status;
  // EVAL_LOG=1 dumps the full trace — clue, number, intended targets, and BOTH
  // sides' reasoning, plus each applied guess's actual category and bonus flag —
  // so a loss can be diagnosed (ambiguous clue vs bad read vs needless bonus).
  if (process.env.EVAL_LOG === "1") {
    const rev = process.env.EVAL_REV ? `  rev=${process.env.EVAL_REV}` : "";
    console.log(
      `\n══ ${label}  seed=${seedKey}${rev}  →  ${outcome}, ` +
      `agents ${state.agentsFound}/${TOTAL_AGENTS}\n${trace.map((l) => "   " + l).join("\n")}`,
    );
  }

  const hitAssassin = state.history.some((t) => t.outcomes.includes("assassin"));
  return {
    won: state.status === "won",
    agentsFound: state.agentsFound,
    hitAssassin,
    reachedSuddenDeath,
    clues,
    illegalClues,
    turnsUsed,
  };
}

function printTable(agg: ReturnType<typeof aggregate>): void {
  const rows: [string, string][] = [
    ["games", String(agg.games)],
    ["win rate", agg.winRate.toFixed(3)],
    ["avg agents found", agg.avgAgents.toFixed(2)],
    ["assassin rate", agg.assassinRate.toFixed(3)],
    ["sudden-death rate", agg.suddenDeathRate.toFixed(3)],
    ["avg turns used", agg.avgTurnsUsed.toFixed(2)],
    ["illegal clue rate (of attempts)", agg.illegalClueRate.toFixed(3)],
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
  // Base seed for reproducible, comparable boards. Game i uses `${seed}#${i}`,
  // so the SAME seed reproduces the SAME N boards across prompt versions —
  // run each version with the same seed to A/B on identical boards (paired).
  const seed = process.env.OPENAI_EVAL_SEED ?? "eval";

  console.log(`model=${model}  games=${n}  seed=${seed}`);
  const results: GameResult[] = [];
  for (let i = 0; i < n; i++) {
    const seedKey = `${seed}#${i}`;
    const r = await playOneGame(apiKey, model, makeRng(seedKey), `game ${i + 1}/${n}`, seedKey);
    results.push(r);
    // Per-game outcome, then the running aggregate so far — so you can watch the
    // numbers converge instead of waiting for the whole run to finish.
    const a = aggregate(results);
    const tag = r.won ? "WON " : r.reachedSuddenDeath ? "sd→ " : "lost";
    console.log(
      `${tag}  agents=${r.agentsFound}/15  turns=${r.turnsUsed}  ` +
      `assassin=${r.hitAssassin ? "YES" : "no"}  illegal=${r.illegalClues}\n` +
      `   running(${a.games}): win ${a.winRate.toFixed(2)}  agents ${a.avgAgents.toFixed(1)}  ` +
      `assassin ${a.assassinRate.toFixed(2)}  sd ${a.suddenDeathRate.toFixed(2)}  ` +
      `turns ${a.avgTurnsUsed.toFixed(1)}  illegal ${a.illegalClueRate.toFixed(3)}`,
    );
  }

  printTable(aggregate(results));
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
