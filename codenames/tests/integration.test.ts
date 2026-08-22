import { describe, it, expect, vi } from "vitest";
import { createController } from "../src/main";
import { createGame } from "../src/engine";
import { LLMError, type LLMCaller, type LLMResult } from "../src/ai";
import type { ClueResponse, GuessResponse } from "../src/validate";
import type { GameState } from "../src/types";

function rng(seed: number) {
  return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed>>>15),1|seed); t=(t+Math.imul(t ^ (t>>>7),61|t))^t; return ((t ^ (t>>>14))>>>0)/4294967296; };
}
const ok = <T>(p: T): LLMResult<T> => ({ parsed: p, refusal: null, finishReason: "stop" });

function fakeUi() {
  const logs: string[] = [];
  return {
    ui: {
      render: vi.fn(), log: (l: string) => logs.push(l),
      getKey: () => "sk-x", getModel: () => "gpt-5.6", setError: vi.fn(),
    },
    logs,
  };
}

function lastRendered(render: any): GameState {
  return render.mock.calls.at(-1)[0] as GameState;
}

describe("controller", () => {
  it("human clue → AI guesses are applied and logged", async () => {
    const { ui, logs } = fakeUi();
    // AI guesser returns the first remaining board word
    const caller: LLMCaller = { call: vi.fn(async (): Promise<LLMResult<any>> => ok<GuessResponse>({ reasoning: "", guesses: [] })) };
    const c = createController({ ui, makeCaller: () => caller, rng: rng(3), firstClueGiver: "human" });
    await c.newGame();
    await c.submitClue("OCEAN", 1);
    expect(ui.render).toHaveBeenCalled();
    expect((caller.call as any)).toHaveBeenCalled();
    // the human clue is logged; the AI's intended guess list is NOT (leak-free)
    expect(logs.some((l) => l.includes('You clued "OCEAN" for 1'))).toBe(true);
    expect(logs.some((l) => l.startsWith("AI will guess"))).toBe(false);
  });

  it("AI clue turn: a legal AI clue is applied and rendered", async () => {
    const { ui } = fakeUi();
    const ref = createGame({ rng: rng(3), firstClueGiver: "ai" });
    const greens = ref.words.filter((_, i) => ref.keys.ai[i] === "green");
    const clueResp: ClueResponse = { reasoning: "", clue: "OCEAN", number: 1, targets: greens.slice(0, 1) };
    const caller: LLMCaller = { call: vi.fn(async (): Promise<LLMResult<any>> => ok<ClueResponse>(clueResp)) };
    const c = createController({ ui, makeCaller: () => caller, rng: rng(3), firstClueGiver: "ai" });

    await c.newGame();

    expect(caller.call).toHaveBeenCalled();
    const state = lastRendered(ui.render);
    expect(state.clueGiver).toBe("ai");
    expect(state.phase).toBe("awaitGuess");
    expect(state.currentClue?.word).toBe("OCEAN");
  });

  it("AI passes: the turn advances back to the human without a clue", async () => {
    const { ui } = fakeUi();
    const caller: LLMCaller = {
      call: vi.fn(async (): Promise<LLMResult<any>> => ({ parsed: null, refusal: "no", finishReason: "stop" })),
    };
    const c = createController({ ui, makeCaller: () => caller, rng: rng(3), firstClueGiver: "ai" });

    await c.newGame();

    expect(ui.render).toHaveBeenCalled();
    const state = lastRendered(ui.render);
    expect(state.clueGiver).toBe("human");
    expect(state.turnsRemaining).toBe(8);
    expect(state.currentClue).toBeNull();
  });

  it("LLMError during the AI's clue fetch surfaces via ui.setError", async () => {
    const { ui } = fakeUi();
    const caller: LLMCaller = {
      call: vi.fn(async () => { throw new LLMError("Invalid API key.", "auth"); }),
    };
    const c = createController({ ui, makeCaller: () => caller, rng: rng(3), firstClueGiver: "ai" });

    await c.newGame();

    expect(ui.setError).toHaveBeenCalledWith("Invalid API key.");
  });

  it("retryAITurn re-attempts the AI clue turn after a prior LLMError", async () => {
    const { ui } = fakeUi();
    const ref = createGame({ rng: rng(3), firstClueGiver: "ai" });
    const greens = ref.words.filter((_, i) => ref.keys.ai[i] === "green");
    const clueResp: ClueResponse = { reasoning: "", clue: "OCEAN", number: 1, targets: greens.slice(0, 1) };
    let shouldFail = true;
    const call = vi.fn(async (): Promise<LLMResult<any>> => {
      if (shouldFail) { shouldFail = false; throw new LLMError("Rate limited — wait and retry.", "rate_limit"); }
      return ok<ClueResponse>(clueResp);
    });
    const caller: LLMCaller = { call };
    const c = createController({ ui, makeCaller: () => caller, rng: rng(3), firstClueGiver: "ai" });

    await c.newGame();
    expect(ui.setError).toHaveBeenCalledWith("Rate limited — wait and retry.");

    await c.retryAITurn();

    expect(call).toHaveBeenCalledTimes(2);
    const state = lastRendered(ui.render);
    expect(state.currentClue?.word).toBe("OCEAN");
  });

  it("retryAITurn resumes a pending AI guess turn after an LLMError from getAIGuess", async () => {
    const { ui } = fakeUi();
    let shouldFail = true;
    const call = vi.fn(async (): Promise<LLMResult<any>> => {
      if (shouldFail) { shouldFail = false; throw new LLMError("Rate limited — wait and retry.", "rate_limit"); }
      return ok<GuessResponse>({ reasoning: "", guesses: [] });
    });
    const caller: LLMCaller = { call };
    // human clues first, the AI guesses
    const c = createController({ ui, makeCaller: () => caller, rng: rng(3), firstClueGiver: "human" });

    await c.newGame();
    await c.submitClue("OCEAN", 1);

    expect(ui.setError).toHaveBeenCalledWith("Rate limited — wait and retry.");
    const stateAfterFailure = lastRendered(ui.render);
    expect(stateAfterFailure.phase).toBe("awaitGuess");
    expect(stateAfterFailure.clueGiver).toBe("human"); // human's turn's controls are still up — no forced forfeit

    await c.retryAITurn();

    expect(call).toHaveBeenCalledTimes(2);
    expect(ui.setError).toHaveBeenLastCalledWith(null); // error cleared once the retry succeeds
  });

  it("re-entrancy: concurrent triggers while an AI clue call is pending invoke the caller only once", async () => {
    const { ui } = fakeUi();
    const ref = createGame({ rng: rng(3), firstClueGiver: "ai" });
    const greens = ref.words.filter((_, i) => ref.keys.ai[i] === "green");
    const clueResp: ClueResponse = { reasoning: "", clue: "OCEAN", number: 1, targets: greens.slice(0, 1) };

    let resolveCall!: (v: LLMResult<any>) => void;
    const pending = new Promise<LLMResult<any>>((res) => { resolveCall = res; });
    const call = vi.fn(() => pending);
    const caller: LLMCaller = { call: call as any };
    const c = createController({ ui, makeCaller: () => caller, rng: rng(3), firstClueGiver: "ai" });

    const gamePromise = c.newGame(); // kicks off the AI clue turn; caller.call is now pending
    // fire several human-triggered entry points while the call is in flight
    const p1 = c.clickCell("WHATEVER");
    const p2 = c.endGuessing();
    const p3 = c.submitClue("X", 1);
    await Promise.all([p1, p2, p3]);

    expect(call).toHaveBeenCalledTimes(1); // still just the one in-flight call

    resolveCall(ok<ClueResponse>(clueResp));
    await gamePromise;

    expect(call).toHaveBeenCalledTimes(1); // resolving didn't trigger any queued-up duplicate
  });

  it("a stale AI result from a previous game is discarded once a new game has started", async () => {
    const { ui } = fakeUi();
    let resolveFirst!: (v: LLMResult<any>) => void;
    const firstPending = new Promise<LLMResult<any>>((res) => { resolveFirst = res; });
    let invocation = 0;
    // Game #1's clue fetch hangs (firstPending); game #2's clue fetch (any
    // later invocation) resolves immediately as a refusal, so the AI simply
    // passes — no board-specific "legal clue" bookkeeping needed for this test.
    const call = vi.fn(async (): Promise<LLMResult<any>> => {
      invocation++;
      if (invocation === 1) return firstPending;
      return { parsed: null, refusal: "no", finishReason: "stop" };
    });
    const caller: LLMCaller = { call: call as any };
    const c = createController({ ui, makeCaller: () => caller, rng: rng(3), firstClueGiver: "ai" });

    const firstGamePromise = c.newGame(); // game #1's AI clue turn: caller.call is now pending on firstPending
    await c.newGame(); // starts game #2; its own AI clue turn resolves immediately (refusal -> pass)

    const stateAfterGame2 = lastRendered(ui.render);
    expect(stateAfterGame2.clueGiver).toBe("human"); // game #2's AI already passed
    const turnsAfterGame2 = stateAfterGame2.turnsRemaining;

    // now let game #1's stale call resolve
    resolveFirst({ parsed: null, refusal: "also stale", finishReason: "stop" });
    await firstGamePromise;

    const finalState = lastRendered(ui.render);
    // without the generation guard, this would apply a second, spurious
    // passTurn() on top of game #2's already-passed state (decrementing the
    // timer again and flipping clueGiver back to "ai")
    expect(finalState.clueGiver).toBe("human");
    expect(finalState.turnsRemaining).toBe(turnsAfterGame2);
  });
});

describe("controller.loadModels", () => {
  it("populates models from the account", async () => {
    const setModels = vi.fn();
    const ui = { render: vi.fn(), log: vi.fn(), getKey: () => "sk-x", getModel: () => "gpt-4o", setError: vi.fn(), setModels };
    const listModels = vi.fn(async () => ["gpt-4o", "o3"]);
    const c = createController({ ui, makeCaller: () => ({ call: vi.fn() }), listModels, rng: rng(3) });
    await c.loadModels();
    expect(listModels).toHaveBeenCalledWith("sk-x");
    expect(setModels).toHaveBeenCalledWith(["gpt-4o", "o3"]);
  });

  it("asks for a key when none is entered (no network call)", async () => {
    const ui = { render: vi.fn(), log: vi.fn(), getKey: () => "", getModel: () => "gpt-4o", setError: vi.fn(), setModels: vi.fn() };
    const listModels = vi.fn(async () => [] as string[]);
    const c = createController({ ui, makeCaller: () => ({ call: vi.fn() }), listModels, rng: rng(3) });
    await c.loadModels();
    expect(listModels).not.toHaveBeenCalled();
    expect(ui.setError).toHaveBeenCalled();
  });

  it("surfaces an LLMError (e.g. bad key) via setError", async () => {
    const ui = { render: vi.fn(), log: vi.fn(), getKey: () => "sk-bad", getModel: () => "gpt-4o", setError: vi.fn(), setModels: vi.fn() };
    const listModels = vi.fn(async () => { throw new LLMError("Invalid API key.", "auth"); });
    const c = createController({ ui, makeCaller: () => ({ call: vi.fn() }), listModels, rng: rng(3) });
    await c.loadModels();
    expect(ui.setError).toHaveBeenCalledWith("Invalid API key.");
  });
});

describe("controller logging (play-by-play)", () => {
  it("logs the human's clue", async () => {
    const { ui, logs } = fakeUi();
    const caller: LLMCaller = { call: vi.fn(async (): Promise<LLMResult<any>> => ok<GuessResponse>({ reasoning: "", guesses: [] })) };
    const c = createController({ ui, makeCaller: () => caller, rng: rng(3), firstClueGiver: "human" });
    await c.newGame();
    await c.submitClue("OCEAN", 2);
    expect(logs.some((l) => l.includes('You clued "OCEAN" for 2'))).toBe(true);
  });

  it("logs the human's guess and its result", async () => {
    const { ui, logs } = fakeUi();
    // replicate the controller's game (same seed) to find a valid AI clue target
    const g = createGame({ rng: rng(3), firstClueGiver: "ai" });
    const aiGreen = g.words.find((_, i) => g.keys.ai[i] === "green")!;
    const clue: ClueResponse = { reasoning: "", clue: "ZZZCLUE", number: 1, targets: [aiGreen] };
    const caller: LLMCaller = {
      call: vi.fn(async (_m: any, _s: any, name: string): Promise<LLMResult<any>> =>
        name === "clue" ? ok<ClueResponse>(clue) : ok<GuessResponse>({ reasoning: "", guesses: [] })),
    };
    const c = createController({ ui, makeCaller: () => caller, rng: rng(3), firstClueGiver: "ai" });
    await c.newGame();          // AI gives its clue → now the human guesses
    await c.clickCell(aiGreen); // human guesses the AI's agent
    expect(logs.some((l) => l.startsWith(`You guessed ${aiGreen} →`))).toBe(true);
  });
});

describe("controller guess logging is leak-free", () => {
  it("logs only guesses actually made; a later un-made guess never appears", async () => {
    // replicate the controller's game (human clues → guesses checked vs HUMAN card)
    const g = createGame({ rng: rng(3), firstClueGiver: "human" });
    const bystander = g.words.find((_, i) => g.keys.human[i] === "bystander")!;
    const other = g.words.find((w) => w !== bystander)!; // must NOT be logged (never guessed)
    const { ui, logs } = fakeUi();
    const caller: LLMCaller = {
      // guess call → the two guesses; the follow-up AI clue call → refuse (pass)
      call: vi.fn(async (_m: any, _s: any, name: string): Promise<LLMResult<any>> =>
        name === "guess"
          ? ok<GuessResponse>({ reasoning: "", guesses: [bystander, other] })
          : { parsed: null, refusal: "pass", finishReason: "stop" }),
    };
    const c = createController({ ui, makeCaller: () => caller, rng: rng(3), firstClueGiver: "human" });
    await c.newGame();
    await c.submitClue("OCEAN", 2);
    // the bystander guess ends the turn; the second guess is never made or logged
    expect(logs.some((l) => l.startsWith(`AI guessed ${bystander} →`))).toBe(true);
    expect(logs.some((l) => l.startsWith(`AI guessed ${other}`))).toBe(false);
  });
});

describe("controller first-player coin flip", () => {
  it("uses the coin flip to pick who clues first when firstClueGiver is unset", async () => {
    // heads → human clues first (awaitClue, human)
    {
      const { ui } = fakeUi();
      const caller: LLMCaller = { call: vi.fn() };
      const c = createController({ ui, makeCaller: () => caller, rng: rng(3), coinFlip: () => true });
      await c.newGame();
      const s = lastRendered(ui.render);
      expect(s.clueGiver).toBe("human");
      expect(s.phase).toBe("awaitClue");
      expect(caller.call).not.toHaveBeenCalled(); // human's turn: no AI call yet
    }
    // tails → AI clues first (it immediately fetches a clue)
    {
      const { ui } = fakeUi();
      const caller: LLMCaller = {
        call: vi.fn(async (): Promise<LLMResult<any>> => ({ parsed: null, refusal: "pass", finishReason: "stop" })),
      };
      const c = createController({ ui, makeCaller: () => caller, rng: rng(3), coinFlip: () => false });
      await c.newGame();
      expect(caller.call).toHaveBeenCalled(); // AI's turn: it fetched a clue
    }
  });
});
