import type { Category, KeyCard, KeyCardPair } from "./types";

// rows = human card, cols = ai card
export const CONTINGENCY: Record<string, number> = {
  GG: 3, GB: 5, GA: 1,
  BG: 5, BB: 7, BA: 1,
  AG: 1, AB: 1, AA: 1,
};

const CODE: Record<string, Category> = { G: "green", B: "bystander", A: "assassin" };

function shuffle<T>(arr: T[], rng: () => number): T[] {
  const a = arr.slice();
  for (let i = a.length - 1; i > 0; i--) {
    const j = Math.floor(rng() * (i + 1));
    [a[i], a[j]] = [a[j]!, a[i]!];
  }
  return a;
}

export function generateKeyCardPair(rng: () => number = Math.random): KeyCardPair {
  const cells: Array<[Category, Category]> = [];
  for (const [pair, n] of Object.entries(CONTINGENCY)) {
    const h = CODE[pair[0]!]!;
    const a = CODE[pair[1]!]!;
    for (let i = 0; i < n; i++) cells.push([h, a]);
  }
  const shuffled = shuffle(cells, rng); // 25 cells to 25 positions
  const human: KeyCard = shuffled.map((c) => c[0]);
  const ai: KeyCard = shuffled.map((c) => c[1]);
  return { human, ai };
}

export function validateKeyCardPair(pair: KeyCardPair): { valid: boolean; errors: string[] } {
  const errors: string[] = [];
  const { human, ai } = pair;
  if (human.length !== 25 || ai.length !== 25) errors.push("cards must be length 25");
  const tally: Record<string, number> = {};
  const enc = (c: Category) => (c === "green" ? "G" : c === "bystander" ? "B" : "A");
  for (let i = 0; i < 25; i++) {
    const key = `${enc(human[i]!)}${enc(ai[i]!)}`;
    tally[key] = (tally[key] ?? 0) + 1;
  }
  for (const [key, n] of Object.entries(CONTINGENCY)) {
    if ((tally[key] ?? 0) !== n) errors.push(`expected ${n} of ${key}, got ${tally[key] ?? 0}`);
  }
  return { valid: errors.length === 0, errors };
}
