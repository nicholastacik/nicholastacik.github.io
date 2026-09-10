import type { Category, GameState, Player } from "./types";
import {
  createGame, giveClue, guess, endGuessing as engineEndGuessing, passTurn, makeRng,
  suddenDeathGuess,
} from "./engine";
import { validateHumanClue } from "./validate";
import { getAIClue, getAIGuess, LLMError, type LLMCaller, type Logger } from "./ai";

export interface ControllerUI {
  render(state: GameState): void;
  log(line: string): void;
  getKey(): string;
  getModel(): string;
  setError(msg: string | null): void;
  setModels?(ids: string[]): void;
  clearLog?(): void;
  isDebug?(): boolean;
  getSeed?(): string;
  setSeed?(seed: string): void;
  setSuddenDeathMeter?(top: { word: string; confidence: number } | null): void;
}

export interface ControllerDeps {
  ui: ControllerUI;
  makeCaller: (key: string, model: string) => LLMCaller;
  listModels?: (key: string) => Promise<string[]>;
  rng?: () => number;
  // Fixed first clue-giver (overrides the coin flip). Mainly for tests.
  firstClueGiver?: Player;
  // Decides who clues first each new game when firstClueGiver is unset:
  // true → human, false → AI. Defaults to a 50/50 flip. Injectable for tests.
  coinFlip?: () => boolean;
  // Fetches the AI's ranked sudden-death guesses. Optional so tests can inject
  // a fake; the real entry passes getSuddenDeathGuesses.
  suddenDeath?: (caller: LLMCaller, state: GameState, log: Logger) => Promise<Array<{ word: string; confidence: number }>>;
}

export function createController(deps: ControllerDeps) {
  const { ui } = deps;
  let state: GameState;
  // Guards against re-entrant AI calls: a double-click, or a human action
  // firing while an AI clue/guess request is in flight, must not trigger a
  // second concurrent AI turn (which would duplicate history / clobber
  // state). Set true before any AI async call, cleared in a finally.
  let busy = false;
  // Bumped by newGame(). Captured by each AI turn before its await; if it no
  // longer matches afterward, a new game started while the call was in
  // flight, and the (now-irrelevant) result must not be applied to the new
  // game's state.
  let generation = 0;

  // The AI's ranked sudden-death guesses, fetched once on entering sudden
  // death (null means "not fetched yet for this game"). Reset in newGame.
  let sdGuesses: Array<{ word: string; confidence: number }> | null = null;

  const log: Logger = (line: string) => ui.log(line);

  function caller(): LLMCaller {
    return deps.makeCaller(ui.getKey(), ui.getModel());
  }

  function render(): void {
    ui.render(state);
  }

  // --- play-by-play logging (bottom panel) ---
  // Emoji matches the card badge. Word kept alongside for clarity/accessibility.
  function guessLabel(cat: Category): string {
    return cat === "green"
      ? "✅ agent"
      : cat === "assassin"
        ? "❌ assassin"
        : "🟡 bystander (turn over)";
  }
  function outcomesLen(): number {
    return state.history[state.history.length - 1]?.outcomes.length ?? 0;
  }
  // Log the most recent guess's result, but only if a guess was actually
  // recorded (a no-op guess leaves history unchanged — don't re-log an old one).
  function logGuessResult(who: string, word: string, beforeLen: number): void {
    const turn = state.history[state.history.length - 1];
    if (turn && turn.outcomes.length > beforeLen) {
      log(`${who} guessed ${word} → ${guessLabel(turn.outcomes[turn.outcomes.length - 1]!)}`);
    }
  }
  function logEndState(): void {
    if (state.status === "won") log("🎉 All 15 agents found — you win!");
    else if (state.status === "lost") log("💥 Game over.");
  }

  // --- sudden death ---
  function isRevealedWord(word: string): boolean {
    const i = state.words.indexOf(word);
    return i >= 0 && !!state.revealed[i];
  }
  function topSDCandidate(): { word: string; confidence: number } | null {
    if (!sdGuesses) return null;
    return sdGuesses.find((g) => !isRevealedWord(g.word)) ?? null;
  }
  function updateSDMeter(): void {
    ui.setSuddenDeathMeter?.(topSDCandidate());
  }

  // Fires the moment the timer hits 0 with agents still hidden: fetches the
  // AI's ranked sudden-death guesses exactly once per game (guarded by
  // sdGuesses === null) and sets the meter. Called at the end of every action
  // that can advance the turn timer to 0.
  async function maybeEnterSuddenDeath(): Promise<void> {
    if (!state.suddenDeath || sdGuesses !== null || !deps.suddenDeath) return;
    const gen = generation;
    busy = true;
    try {
      ui.setError(null);
      log("⏱ Sudden death — no clues left. Any wrong guess loses.");
      const list = await deps.suddenDeath(caller(), state, log);
      if (gen !== generation) return; // stale: a new game started meanwhile
      sdGuesses = list;
      updateSDMeter();
      render();
    } catch (e) {
      if (gen !== generation) return; // stale: don't surface a dead game's error
      if (e instanceof LLMError) ui.setError(e.message);
      else throw e;
    } finally {
      if (gen === generation) busy = false;
    }
  }

  // The AI's move during sudden death: guess its top confident candidate
  // against the human's card. Called by the "AI guess" button.
  async function aiSuddenDeathGuess(): Promise<void> {
    if (busy || !state.suddenDeath || state.status !== "playing") return;
    const top = topSDCandidate();
    if (!top) {
      log("The AI has no confident sudden-death guess — your move.");
      return;
    }
    state = suddenDeathGuess(state, top.word, "ai");
    log(`AI guessed ${top.word} → ${guessLabel(state.suddenDeathGuesses[state.suddenDeathGuesses.length - 1]!.outcome)}`);
    updateSDMeter();
    render();
    logEndState();
  }

  function isAIsClueTurn(): boolean {
    return state.clueGiver === "ai" && state.phase === "awaitClue" && state.status === "playing";
  }

  function isAIsGuessPending(): boolean {
    return state.clueGiver === "human" && state.phase === "awaitGuess" && state.status === "playing";
  }

  // Runs the AI's clue-giving turn: request a clue, give it (or pass), render.
  // Waits for the human to click cells afterward — does not itself guess.
  async function runAIClueTurn(): Promise<void> {
    const gen = generation;
    busy = true;
    try {
      ui.setError(null);
      log("The AI is thinking of a clue…");
      const clue = await getAIClue(caller(), state, log);
      if (gen !== generation) return; // stale: a new game started meanwhile
      if (clue === null) {
        // AI passed without giving a clue: advance the turn via the engine's
        // exported passTurn primitive (no duplicated turn-advance logic here).
        state = passTurn(state);
        render();
        await maybeEnterSuddenDeath();
        return;
      }
      state = giveClue(state, clue.clue, clue.number);
      if (ui.isDebug?.()) log(`🐛 AI wants you to find: ${clue.targets.join(", ")}`);
      render();
    } catch (e) {
      if (gen !== generation) return; // stale: don't surface a dead game's error
      if (e instanceof LLMError) ui.setError(e.message);
      else throw e;
    } finally {
      // Only clear the guard if this call still belongs to the current game —
      // a call superseded by newGame() must not unlock the new game's turn.
      if (gen === generation) busy = false;
    }
  }

  // Runs the AI's guessing turn against the human's just-given clue, applying
  // each returned guess in order until the guessing turn ends or the game
  // does. Shared by submitClue (the normal path) and retryAITurn (resuming
  // after a failed attempt) so there's exactly one place this logic lives.
  async function runAIGuessTurn(): Promise<void> {
    const gen = generation;
    busy = true;
    try {
      ui.setError(null);
      log("The AI is thinking about your clue…");
      const words = await getAIGuess(caller(), state, log);
      if (gen !== generation) return; // stale: a new game started meanwhile
      if (ui.isDebug?.()) log(`🐛 AI intends to guess: ${words.join(", ") || "(nothing)"}`);
      for (const word of words) {
        if (state.phase !== "awaitGuess" || state.status !== "playing") break;
        const beforeLen = outcomesLen();
        state = guess(state, word);
        logGuessResult("AI", word, beforeLen);
        render();
      }
      // The AI's returned list IS how many it chose to guess. If the turn didn't
      // already end (a wrong guess / the number+1 cap / a win), the AI has
      // decided to stop — end its guessing turn so play advances (otherwise the
      // game would stall with no visible control).
      if (state.status === "playing" && state.phase === "awaitGuess") {
        log("The AI stops guessing.");
        state = engineEndGuessing(state);
        render();
      }
      logEndState();
    } catch (e) {
      if (gen !== generation) return; // stale: don't surface a dead game's error
      if (e instanceof LLMError) { ui.setError(e.message); return; }
      throw e;
    } finally {
      // Only clear the guard if this call still belongs to the current game —
      // a call superseded by newGame() must not unlock the new game's turn.
      if (gen === generation) busy = false;
    }
  }

  // The AI's clue turn is NOT run automatically — the human triggers it with the
  // "Get the AI's clue" button (requestAIClue), so the turn flow is explicit and
  // no API call fires without a click. (The AI's *guessing* stays automatic: it's
  // the direct result of the human submitting a clue.)
  async function requestAIClue(): Promise<void> {
    if (busy) return;
    if (isAIsClueTurn()) await runAIClueTurn();
  }

  async function newGame(): Promise<void> {
    generation += 1;
    busy = false; // abandon any in-flight AI call from the previous game (its result is discarded by the generation guard)
    sdGuesses = null;
    ui.clearLog?.(); // fresh log each game

    // Seed: use what's entered, else generate one and show it — so every game
    // is reproducible (same seed → same board + first player). deps.rng (tests)
    // takes precedence and skips seeding entirely.
    let seed = (ui.getSeed?.() ?? "").trim();
    if (!deps.rng && !seed) {
      seed = String(Math.floor(Math.random() * 1e9));
      ui.setSeed?.(seed);
    }
    const rng = deps.rng ?? (seed ? makeRng(seed) : undefined);

    const flip = deps.coinFlip ?? (rng ? () => rng() < 0.5 : () => Math.random() < 0.5);
    const first: Player = deps.firstClueGiver ?? (flip() ? "human" : "ai");
    state = createGame({ rng, firstClueGiver: first });
    if (seed) log(`New game (seed: ${seed}).`);
    log(
      first === "human"
        ? "You give the first clue."
        : 'The AI gives the first clue. Click "Get the AI\'s clue".',
    );
    render();
  }

  async function submitClue(w: string, n: number): Promise<void> {
    if (busy) return;
    const check = validateHumanClue(w, n, state);
    if (!check.ok) {
      ui.setError(`Illegal clue: ${check.violations.join("; ")}.`);
      return;
    }
    ui.setError(null);
    log(`You clued "${w}" for ${n}.`);
    state = giveClue(state, w, n);
    render();
    await runAIGuessTurn();
    await maybeEnterSuddenDeath();
  }

  // The human passes their clue turn (e.g. all their agents are already found, so
  // there's nothing to clue). Advances to the AI's clue turn, spending a timer
  // token — matching Duet, where a forced pass still uses the timeline.
  async function passClue(): Promise<void> {
    if (busy) return;
    if (!(state.clueGiver === "human" && state.phase === "awaitClue" && state.status === "playing")) return;
    log("You pass — no clue.");
    state = passTurn(state);
    render();
    logEndState();
    await maybeEnterSuddenDeath();
  }

  async function clickCell(w: string): Promise<void> {
    if (busy) return;
    if (state.suddenDeath) {
      if (state.status !== "playing") return;
      const before = state.suddenDeathGuesses.length;
      state = suddenDeathGuess(state, w, "human");
      if (state.suddenDeathGuesses.length > before) {
        log(`You guessed ${w} → ${guessLabel(state.suddenDeathGuesses[state.suddenDeathGuesses.length - 1]!.outcome)}`);
      }
      updateSDMeter();
      render();
      logEndState();
      return;
    }
    // Ownership guard: a cell click is only meaningful while the human is
    // guessing against the AI's active clue.
    if (!(state.clueGiver === "ai" && state.phase === "awaitGuess")) return;
    const beforeLen = outcomesLen();
    state = guess(state, w);
    logGuessResult("You", w, beforeLen);
    render();
    logEndState();
    await maybeEnterSuddenDeath();
  }

  async function endGuessing(): Promise<void> {
    if (busy) return;
    state = engineEndGuessing(state);
    render();
    await maybeEnterSuddenDeath();
  }

  // Resumes whichever AI action is currently pending after it failed with an
  // LLMError: the AI's clue fetch (clueGiver "ai", still awaitClue) or the
  // AI's guess fetch (a human clue was already given — clueGiver "human",
  // awaitGuess). A failed attempt leaves state unchanged, so this is just
  // "figure out which one is pending, and try it again."
  async function retryAITurn(): Promise<void> {
    if (busy) return;
    if (isAIsClueTurn()) {
      await runAIClueTurn();
    } else if (isAIsGuessPending()) {
      await runAIGuessTurn();
    }
    await maybeEnterSuddenDeath();
  }

  // Fetch the models this key can access and populate the picker. Independent
  // of the game turn loop (a read-only account call), so it doesn't use the
  // AI-turn busy guard.
  async function loadModels(): Promise<void> {
    if (!deps.listModels || !ui.setModels) return;
    const key = ui.getKey();
    if (!key) { ui.setError("Enter your API key first, then load models."); return; }
    try {
      ui.setError(null);
      const models = await deps.listModels(key);
      ui.setModels(models);
      if (models.length === 0) ui.setError("No compatible chat models found for this key.");
    } catch (e) {
      if (e instanceof LLMError) ui.setError(e.message);
      else throw e;
    }
  }

  return {
    newGame, submitClue, passClue, clickCell, endGuessing, retryAITurn, requestAIClue, loadModels,
    aiSuddenDeathGuess,
  };
}

// at bottom of main.ts — real app wiring (not exercised by jsdom tests)
import { GameUI } from "./ui";
import { OpenAICaller, listChatModels, getSuddenDeathGuesses } from "./ai";
import "./style.css";

if (typeof document !== "undefined" && document.getElementById("app")) {
  const root = document.getElementById("app")!;
  let controller: ReturnType<typeof createController>;
  const ui = new GameUI(root, {
    onClueSubmit: (w, n) => controller.submitClue(w, n),
    onPassClue: () => controller.passClue(),
    onCellClick: (w) => controller.clickCell(w),
    onEndGuessing: () => controller.endGuessing(),
    onNewGame: () => controller.newGame(),
    onRetry: () => controller.retryAITurn(),
    onGetClue: () => controller.requestAIClue(),
    onLoadModels: () => controller.loadModels(),
    onAiGuess: () => controller.aiSuddenDeathGuess(),
  });
  controller = createController({
    ui,
    makeCaller: (key, model) => new OpenAICaller({ apiKey: key, model }),
    listModels: (key) => listChatModels(key),
    suddenDeath: (c, s, l) => getSuddenDeathGuesses(c, s, l),
  });
  controller.newGame();
}
