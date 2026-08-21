import { describe, it, expect } from "vitest";
import { generateKeyCardPair, validateKeyCardPair } from "../src/keycards";
import type { Category, KeyCard } from "../src/types";

const count = (k: KeyCard, c: Category) => k.filter((x) => x === c).length;

// deterministic PRNG (mulberry32) so tests are reproducible
function rng(seed: number) {
  return () => {
    seed |= 0; seed = (seed + 0x6d2b79f5) | 0;
    let t = Math.imul(seed ^ (seed >>> 15), 1 | seed);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

describe("generateKeyCardPair", () => {
  it("produces two 25-cell cards with the Duet distribution", () => {
    for (let s = 0; s < 25; s++) {
      const { human, ai } = generateKeyCardPair(rng(s));
      expect(human.length).toBe(25);
      expect(ai.length).toBe(25);
      expect(count(human, "green")).toBe(9);
      expect(count(human, "assassin")).toBe(3);
      expect(count(ai, "green")).toBe(9);
      expect(count(ai, "assassin")).toBe(3);
    }
  });

  it("has exactly 15 unique agents and 1 mutual assassin", () => {
    const { human, ai } = generateKeyCardPair(rng(7));
    let unique = 0, mutualAssassin = 0;
    for (let i = 0; i < 25; i++) {
      if (human[i] === "green" || ai[i] === "green") unique++;
      if (human[i] === "assassin" && ai[i] === "assassin") mutualAssassin++;
    }
    expect(unique).toBe(15);
    expect(mutualAssassin).toBe(1);
  });

  it("validateKeyCardPair accepts generated pairs and rejects a broken one", () => {
    expect(validateKeyCardPair(generateKeyCardPair(rng(1))).valid).toBe(true);
    const broken = generateKeyCardPair(rng(1));
    broken.human[0] = broken.human[0] === "green" ? "bystander" : "green";
    expect(validateKeyCardPair(broken).valid).toBe(false);
  });
});
