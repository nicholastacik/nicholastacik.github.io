import { describe, it, expect } from "vitest";
import { validateClue, filterGuesses, validateHumanClue, SuddenDeathSchema, filterSuddenDeathGuesses } from "../src/validate";
import { createGame } from "../src/engine";

function rng(seed: number) {
  return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed>>>15),1|seed); t=(t+Math.imul(t ^ (t>>>7),61|t))^t; return ((t ^ (t>>>14))>>>0)/4294967296; };
}

describe("validateClue", () => {
  const s = createGame({ rng: rng(3), firstClueGiver: "ai" });
  const aiGreens = s.words.filter((_, i) => s.keys.ai[i] === "green");

  it("accepts a legal clue targeting the AI's greens", () => {
    const r = validateClue({ reasoning: "", clue: "OCEAN", number: 2, targets: aiGreens.slice(0, 2) }, s);
    expect(r.ok).toBe(true);
  });
  it("rejects a multi-word clue", () => {
    const r = validateClue({ reasoning: "", clue: "DEEP SEA", number: 1, targets: aiGreens.slice(0, 1) }, s);
    expect(r.ok).toBe(false);
  });
  it("rejects a clue equal to a board word", () => {
    const r = validateClue({ reasoning: "", clue: s.words[0]!.toLowerCase(), number: 1, targets: aiGreens.slice(0, 1) }, s);
    expect(r.ok).toBe(false);
  });
  it("rejects number != targets length", () => {
    const r = validateClue({ reasoning: "", clue: "OCEAN", number: 3, targets: aiGreens.slice(0, 1) }, s);
    expect(r.ok).toBe(false);
  });
  it("rejects duplicate targets (length check alone would pass)", () => {
    const g = aiGreens[0]!;
    const r = validateClue({ reasoning: "", clue: "OCEAN", number: 2, targets: [g, g] }, s);
    expect(r.ok).toBe(false);
    expect(r.violations.some((v) => /distinct/.test(v))).toBe(true);
  });
  it("rejects a target that is not one of the AI's greens", () => {
    const notGreen = s.words.find((_, i) => s.keys.ai[i] !== "green")!;
    const r = validateClue({ reasoning: "", clue: "OCEAN", number: 1, targets: [notGreen] }, s);
    expect(r.ok).toBe(false);
  });
  it("rejects a clue equal to a revealed board word", () => {
    const s2 = createGame({ rng: rng(3), firstClueGiver: "ai" });
    const w = s2.words[0]!;
    s2.revealed[0] = true;
    const r = validateClue({ reasoning: "", clue: w, number: 1, targets: aiGreens.slice(0, 1) }, s2);
    expect(r.ok).toBe(false);
  });
  it("judges targets against the clue-giver's card (human's greens when the human clues)", () => {
    const hs = createGame({ rng: rng(3), firstClueGiver: "human" });
    const humanGreen = hs.words.find((_, i) => hs.keys.human[i] === "green")!;
    const aiOnlyGreen = hs.words.find((_, i) => hs.keys.ai[i] === "green" && hs.keys.human[i] !== "green")!;
    expect(validateClue({ reasoning: "", clue: "OCEAN", number: 1, targets: [humanGreen] }, hs).ok).toBe(true);
    expect(validateClue({ reasoning: "", clue: "OCEAN", number: 1, targets: [aiOnlyGreen] }, hs).ok).toBe(false);
  });
  it("rejects a target that is an AI green but revealed", () => {
    const s2 = createGame({ rng: rng(3), firstClueGiver: "ai" });
    const greenIdx = s2.words.findIndex((_, i) => s2.keys.ai[i] === "green");
    const greenWord = s2.words[greenIdx]!;
    s2.revealed[greenIdx] = true;
    const r = validateClue({ reasoning: "", clue: "OCEAN", number: 1, targets: [greenWord] }, s2);
    expect(r.ok).toBe(false);
  });
});

describe("filterGuesses", () => {
  const s = createGame({ rng: rng(3) });
  it("keeps board words (case-insensitive), drops junk + dupes", () => {
    const w0 = s.words[0]!;
    const out = filterGuesses([w0.toLowerCase(), "NOTAWORD"], s);
    expect(out).toEqual([w0]);
  });
  it("drops revealed words", () => {
    const s2 = createGame({ rng: rng(3) });
    const w0 = s2.words[0]!;
    s2.revealed[0] = true;
    const out = filterGuesses([w0], s2);
    expect(out).toEqual([]);
  });
});

describe("validateHumanClue", () => {
  const s = createGame({ rng: rng(3) });
  it("accepts a legal one-word, positive-number clue", () => {
    expect(validateHumanClue("OCEAN", 2, s).ok).toBe(true);
  });
  it("rejects a multi-word clue", () => {
    expect(validateHumanClue("DEEP SEA", 1, s).ok).toBe(false);
  });
  it("rejects a clue that is a board word", () => {
    expect(validateHumanClue(s.words[0]!.toLowerCase(), 1, s).ok).toBe(false);
  });
  it("rejects a non-positive or non-integer number", () => {
    expect(validateHumanClue("OCEAN", 0, s).ok).toBe(false);
    expect(validateHumanClue("OCEAN", -3, s).ok).toBe(false);
    expect(validateHumanClue("OCEAN", 1.5, s).ok).toBe(false);
  });
});

describe("clue vs board-word substring rule", () => {
  const s = createGame({ rng: rng(3), firstClueGiver: "ai" });
  const longWord = s.words.find((w) => w.length >= 5)!;
  const aiGreen = s.words.find((_, i) => s.keys.ai[i] === "green")!;

  it("validateClue rejects a clue contained in a board word (HERO/SUPERHERO case)", () => {
    const sub = longWord.slice(0, 4); // a proper substring of a board word
    expect(validateClue({ reasoning: "", clue: sub, number: 1, targets: [aiGreen] }, s).ok).toBe(false);
  });

  it("validateHumanClue rejects a substring AND a superstring of a board word", () => {
    expect(validateHumanClue(longWord.slice(0, 4), 1, s).ok).toBe(false); // clue inside a board word
    expect(validateHumanClue(`${s.words[0]}ING`, 1, s).ok).toBe(false);   // clue contains a board word
  });

  it("still accepts a clue unrelated to any board word", () => {
    expect(validateHumanClue("OCEAN", 2, s).ok).toBe(true);
  });
});

describe("filterSuddenDeathGuesses", () => {
  const s = createGame({ rng: rng(3) });
  it("keeps canonical board words, clamps confidence, dedupes", () => {
    const w0 = s.words[0]!;
    const out = filterSuddenDeathGuesses(
      [{ word: w0.toLowerCase(), confidence: 1.4 }, { word: "NOTAWORD", confidence: 0.5 }, { word: w0, confidence: 0.9 }],
      s,
    );
    expect(out).toEqual([{ word: w0, confidence: 1 }]);
  });
  it("drops revealed words", () => {
    const s2 = { ...s, revealed: s.revealed.map((_, i) => i === 0) };
    expect(filterSuddenDeathGuesses([{ word: s.words[0]!, confidence: 0.9 }], s2)).toEqual([]);
  });
  it("clamps negative confidence to 0", () => {
    expect(filterSuddenDeathGuesses([{ word: s.words[0]!, confidence: -0.5 }], s)).toEqual([{ word: s.words[0], confidence: 0 }]);
  });
});
