import type { GameState, Player } from "./types";
import { createGame, giveClue, guess, endGuessing as engineEndGuessing, passTurn } from "./engine";
import { getAIClue, getAIGuess, LLMError, type LLMCaller, type Logger } from "./ai";

export interface ControllerUI {
  render(state: GameState): void;
  log(line: string): void;
  getKey(): string;
  getModel(): string;
  setError(msg: string | null): void;
}

export interface ControllerDeps {
  ui: ControllerUI;
  makeCaller: (key: string, model: string) => LLMCaller;
  rng?: () => number;
  firstClueGiver?: Player;
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

  const log: Logger = (line: string) => ui.log(line);

  function caller(): LLMCaller {
    return deps.makeCaller(ui.getKey(), ui.getModel());
  }

  function render(): void {
    ui.render(state);
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
      const clue = await getAIClue(caller(), state, log);
      if (gen !== generation) return; // stale: a new game started meanwhile
      if (clue === null) {
        // AI passed without giving a clue: advance the turn via the engine's
        // exported passTurn primitive (no duplicated turn-advance logic here).
        state = passTurn(state);
        render();
        return;
      }
      state = giveClue(state, clue.clue, clue.number);
      render();
    } catch (e) {
      if (gen !== generation) return; // stale: don't surface a dead game's error
      if (e instanceof LLMError) ui.setError(e.message);
      else throw e;
    } finally {
      busy = false;
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
      const words = await getAIGuess(caller(), state, log);
      if (gen !== generation) return; // stale: a new game started meanwhile
      for (const word of words) {
        if (state.phase !== "awaitGuess" || state.status !== "playing") break;
        state = guess(state, word);
        render();
      }
    } catch (e) {
      if (gen !== generation) return; // stale: don't surface a dead game's error
      if (e instanceof LLMError) { ui.setError(e.message); return; }
      throw e;
    } finally {
      busy = false;
    }
  }

  async function maybeRunAIClueTurn(): Promise<void> {
    if (isAIsClueTurn()) await runAIClueTurn();
  }

  async function newGame(): Promise<void> {
    generation += 1;
    state = createGame({ rng: deps.rng, firstClueGiver: deps.firstClueGiver });
    render();
    await maybeRunAIClueTurn();
  }

  async function submitClue(w: string, n: number): Promise<void> {
    if (busy) return;
    state = giveClue(state, w, n);
    render();

    await runAIGuessTurn();
    await maybeRunAIClueTurn();
  }

  async function clickCell(w: string): Promise<void> {
    if (busy) return;
    // Ownership guard: a cell click is only meaningful while the human is
    // guessing against the AI's active clue — this also prevents a stray
    // click from accidentally re-kicking the AI's clue turn (the old
    // accidental click-to-retry side effect).
    if (!(state.clueGiver === "ai" && state.phase === "awaitGuess")) return;
    state = guess(state, w);
    render();
    await maybeRunAIClueTurn();
  }

  async function endGuessing(): Promise<void> {
    if (busy) return;
    state = engineEndGuessing(state);
    render();
    await maybeRunAIClueTurn();
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
    } else {
      return;
    }
    await maybeRunAIClueTurn();
  }

  return { newGame, submitClue, clickCell, endGuessing, retryAITurn };
}

// at bottom of main.ts — real app wiring (not exercised by jsdom tests)
import { GameUI } from "./ui";
import { OpenAICaller } from "./ai";
import "./style.css";

if (typeof document !== "undefined" && document.getElementById("app")) {
  const root = document.getElementById("app")!;
  let controller: ReturnType<typeof createController>;
  const ui = new GameUI(root, {
    onClueSubmit: (w, n) => controller.submitClue(w, n),
    onCellClick: (w) => controller.clickCell(w),
    onEndGuessing: () => controller.endGuessing(),
    onSaveKey: () => {},
    onNewGame: () => controller.newGame(),
    onRetry: () => controller.retryAITurn(),
  });
  controller = createController({
    ui,
    makeCaller: (key, model) => new OpenAICaller({ apiKey: key, model }),
  });
  controller.newGame();
}
