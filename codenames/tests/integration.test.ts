import { describe, it, expect, vi } from "vitest";
import { createController } from "../src/main";
import type { LLMCaller, LLMResult } from "../src/ai";
import type { GuessResponse } from "../src/validate";

function rng(seed: number) {
  return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed>>>15),1|seed); t=(t+Math.imul(t ^ (t>>>7),61|t))^t; return ((t ^ (t>>>14))>>>0)/4294967296; };
}
const ok = <T>(p: T): LLMResult<T> => ({ parsed: p, refusal: null, finishReason: "stop" });

describe("controller", () => {
  it("human clue → AI guesses are applied and logged", async () => {
    const logs: string[] = [];
    const ui = {
      render: vi.fn(), log: (l: string) => logs.push(l),
      getKey: () => "sk-x", getModel: () => "gpt-5.6", setError: vi.fn(),
    };
    // AI guesser returns the first remaining board word
    const caller: LLMCaller = { call: vi.fn(async (): Promise<LLMResult<any>> => ok<GuessResponse>({ reasoning: "", guesses: [] })) };
    const c = createController({ ui, makeCaller: () => caller, rng: rng(3) });
    c.newGame();
    await c.submitClue("OCEAN", 1);
    expect(ui.render).toHaveBeenCalled();
    expect((caller.call as any)).toHaveBeenCalled();
  });
});
