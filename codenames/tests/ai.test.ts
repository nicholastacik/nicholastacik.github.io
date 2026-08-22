import { describe, it, expect, vi } from "vitest";
import { getAIClue, getAIGuess, filterChatModels, type LLMCaller, type LLMResult } from "../src/ai";
import { createGame, giveClue } from "../src/engine";
import type { ClueResponse, GuessResponse } from "../src/validate";

function rng(seed: number) {
  return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed>>>15),1|seed); t=(t+Math.imul(t ^ (t>>>7),61|t))^t; return ((t ^ (t>>>14))>>>0)/4294967296; };
}
const ok = <T>(parsed: T): LLMResult<T> => ({ parsed, refusal: null, finishReason: "stop" });

// caller that returns a scripted queue of results
function scripted(results: LLMResult<any>[]): LLMCaller {
  let i = 0;
  return { call: vi.fn(async () => results[i++]!) };
}

describe("getAIClue", () => {
  it("returns a legal clue on first try", async () => {
    const s = createGame({ rng: rng(3), firstClueGiver: "ai" });
    const greens = s.words.filter((_, i) => s.keys.ai[i] === "green");
    const caller = scripted([ok<ClueResponse>({ reasoning: "", clue: "OCEAN", number: 1, targets: greens.slice(0, 1) })]);
    const clue = await getAIClue(caller, s, () => {});
    expect(clue?.clue).toBe("OCEAN");
  });

  it("repairs an illegal clue, then succeeds", async () => {
    const s = createGame({ rng: rng(3), firstClueGiver: "ai" });
    const greens = s.words.filter((_, i) => s.keys.ai[i] === "green");
    const caller = scripted([
      ok<ClueResponse>({ reasoning: "", clue: "TWO WORDS", number: 1, targets: greens.slice(0, 1) }),
      ok<ClueResponse>({ reasoning: "", clue: "OCEAN", number: 1, targets: greens.slice(0, 1) }),
    ]);
    const clue = await getAIClue(caller, s, () => {});
    expect(clue?.clue).toBe("OCEAN");
    expect(caller.call).toHaveBeenCalledTimes(2);
  });

  it("passes (null) after exhausting retries", async () => {
    const s = createGame({ rng: rng(3), firstClueGiver: "ai" });
    const bad = ok<ClueResponse>({ reasoning: "", clue: "A B", number: 9, targets: [] });
    const caller = scripted([bad, bad, bad]);
    const clue = await getAIClue(caller, s, () => {});
    expect(clue).toBeNull();
    expect(caller.call).toHaveBeenCalledTimes(3);
  });

  it("passes (null) on refusal", async () => {
    const s = createGame({ rng: rng(3), firstClueGiver: "ai" });
    const caller = scripted([{ parsed: null, refusal: "no", finishReason: "stop" }]);
    expect(await getAIClue(caller, s, () => {})).toBeNull();
  });
});

describe("getAIGuess", () => {
  it("returns only legal board words", async () => {
    let s = createGame({ rng: rng(3), firstClueGiver: "human" });
    s = giveClue(s, "OCEAN", 2);
    const legal = s.words.slice(0, 2);
    const caller = scripted([ok<GuessResponse>({ reasoning: "", guesses: [...legal, "JUNK"] })]);
    expect(await getAIGuess(caller, s, () => {})).toEqual(legal);
  });

  it("returns [] on refusal", async () => {
    let s = createGame({ rng: rng(3), firstClueGiver: "human" });
    s = giveClue(s, "OCEAN", 2);
    const caller = scripted([{ parsed: null, refusal: "no", finishReason: "stop" }]);
    expect(await getAIGuess(caller, s, () => {})).toEqual([]);
  });

  it("returns [] when there is no parsed content", async () => {
    let s = createGame({ rng: rng(3), firstClueGiver: "human" });
    s = giveClue(s, "OCEAN", 2);
    const caller = scripted([{ parsed: null, refusal: null, finishReason: "stop" }]);
    expect(await getAIGuess(caller, s, () => {})).toEqual([]);
  });
});

describe("filterChatModels", () => {
  it("keeps chat models, drops non-chat, dedupes and sorts", () => {
    const raw = [
      "gpt-4o", "gpt-4o", "o3", "chatgpt-4o-latest", "gpt-4o-mini", "gpt-4o-search-preview",
      "text-embedding-3-small", "whisper-1", "tts-1", "dall-e-3",
      "omni-moderation-latest", "gpt-4o-realtime-preview", "gpt-3.5-turbo-instruct",
      "o3-deep-research",
    ];
    const out = filterChatModels(raw);
    // kept (incl. search-preview, which is a real chat model)
    for (const m of ["gpt-4o", "o3", "chatgpt-4o-latest", "gpt-4o-mini", "gpt-4o-search-preview"]) {
      expect(out).toContain(m);
    }
    // dropped (non-chat, realtime, instruct, async deep-research)
    for (const m of ["text-embedding-3-small", "whisper-1", "tts-1", "dall-e-3",
      "omni-moderation-latest", "gpt-4o-realtime-preview", "gpt-3.5-turbo-instruct",
      "o3-deep-research"]) {
      expect(out).not.toContain(m);
    }
    // deduped + sorted
    expect(out.filter((m) => m === "gpt-4o").length).toBe(1);
    expect([...out]).toEqual([...out].sort());
  });
});
