import { describe, it, expect } from "vitest";
import { WORDS } from "../src/words";

describe("WORDS", () => {
  it("has enough distinct uppercase words for a board", () => {
    expect(WORDS.length).toBeGreaterThanOrEqual(300); // large pool for variety
    expect(new Set(WORDS).size).toBe(WORDS.length); // all distinct
    for (const w of WORDS) {
      expect(w).toBe(w.toUpperCase()); // uppercase
      expect(w).toMatch(/^[A-Z]+$/); // single token, letters only (no spaces/hyphens)
    }
  });
});
