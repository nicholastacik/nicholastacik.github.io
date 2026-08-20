import type { GameState } from "./types";
import { createGame, giveClue, guess, endGuessing as engineEndGuessing } from "./engine";
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
}

export function createController(deps: ControllerDeps) {
  const { ui } = deps;
  let state: GameState;

  const log: Logger = (line: string) => ui.log(line);

  function caller(): LLMCaller {
    return deps.makeCaller(ui.getKey(), ui.getModel());
  }

  function render(): void {
    ui.render(state);
  }

  // Runs the AI's clue-giving turn: request a clue, give it (or pass), render.
  // Waits for the human to click cells afterward — does not itself guess.
  async function runAIClueTurn(): Promise<void> {
    try {
      ui.setError(null);
      const clue = await getAIClue(caller(), state, log);
      if (clue === null) {
        // AI passed without giving a clue: advance the turn directly (the
        // engine has no exported "pass" — endGuessing() only fires from
        // phase "awaitGuess", which is never reached here).
        state = passAITurn(state);
        render();
        return;
      }
      state = giveClue(state, clue.clue, clue.number);
      render();
    } catch (e) {
      if (e instanceof LLMError) ui.setError(e.message);
      else throw e;
    }
  }

  // Advance past the AI's turn when it passes (gives no clue), without
  // requiring a fake clue/guess round-trip through the engine.
  function passAITurn(s: GameState): GameState {
    if (s.status !== "playing") return s;
    const next = structuredClone(s);
    next.phase = "awaitClue";
    next.currentClue = null;
    next.clueGiver = next.clueGiver === "human" ? "ai" : "human";
    next.turnsRemaining -= 1;
    if (next.turnsRemaining <= 0 && next.status === "playing") next.suddenDeath = true;
    return next;
  }

  function isAIsClueTurn(): boolean {
    return state.clueGiver === "ai" && state.phase === "awaitClue" && state.status === "playing";
  }

  async function maybeRunAIClueTurn(): Promise<void> {
    if (isAIsClueTurn()) await runAIClueTurn();
  }

  function newGame(): void {
    state = createGame({ rng: deps.rng });
    render();
    void maybeRunAIClueTurn();
  }

  async function submitClue(w: string, n: number): Promise<void> {
    state = giveClue(state, w, n);
    render();

    try {
      ui.setError(null);
      const words = await getAIGuess(caller(), state, log);
      for (const word of words) {
        if (state.phase !== "awaitGuess" || state.status !== "playing") break;
        state = guess(state, word);
        render();
      }
    } catch (e) {
      if (e instanceof LLMError) { ui.setError(e.message); return; }
      throw e;
    }

    await maybeRunAIClueTurn();
  }

  async function clickCell(w: string): Promise<void> {
    state = guess(state, w);
    render();
    await maybeRunAIClueTurn();
  }

  async function endGuessing(): Promise<void> {
    state = engineEndGuessing(state);
    render();
    await maybeRunAIClueTurn();
  }

  return { newGame, submitClue, clickCell, endGuessing };
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
  });
  controller = createController({
    ui,
    makeCaller: (key, model) => new OpenAICaller({ apiKey: key, model }),
  });
  controller.newGame();
}
