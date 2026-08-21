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
    const c = createController({ ui, makeCaller: () => caller, rng: rng(3) });
    await c.newGame();
    await c.submitClue("OCEAN", 1);
    expect(ui.render).toHaveBeenCalled();
    expect((caller.call as any)).toHaveBeenCalled();
    // getAIGuess always logs a summary line, even for an empty guess list
    expect(logs).toContain("AI will guess: (nothing).");
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
    // default firstClueGiver ("human"): the human gives the clue, the AI guesses
    const c = createController({ ui, makeCaller: () => caller, rng: rng(3) });

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
