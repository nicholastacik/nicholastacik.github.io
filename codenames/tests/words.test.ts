import { describe, it, expect } from "vitest";
import { WORDS } from "../src/words";

describe("WORDS", () => {
  it("has enough distinct uppercase words for a board", () => {
    expect(WORDS.length).toBeGreaterThanOrEqual(40);
    expect(new Set(WORDS).size).toBe(WORDS.length);
    for (const w of WORDS) expect(w).toBe(w.toUpperCase());
  });
});
