import { describe, it, expect } from "vitest";
import { parseStudy } from "../src/study";

const good = {
  id: "italian-game",
  name: "Italian Game",
  eco: "C50",
  side: "white",
  intro: "Quick development and pressure on f7.",
  line: [
    { san: "e4", comment: "Stake the center." },
    { san: "e5" },
    { san: "Nf3", comment: "Attacks e5." },
    {
      san: "Nc6",
      alts: [
        [{ san: "Nf6", comment: "The Petrov." }],
      ],
    },
  ],
};

describe("parseStudy", () => {
  it("accepts a valid study", () => {
    const s = parseStudy(good);
    expect(s.id).toBe("italian-game");
    expect(s.line[3]!.alts![0]![0]!.san).toBe("Nf6");
  });

  it("rejects a bad id slug", () => {
    expect(() => parseStudy({ ...good, id: "Italian Game" })).toThrow();
  });

  it("rejects a bad side", () => {
    expect(() => parseStudy({ ...good, side: "grey" })).toThrow();
  });

  it("rejects an empty line", () => {
    expect(() => parseStudy({ ...good, line: [] })).toThrow();
  });

  it("rejects a node missing san", () => {
    expect(() => parseStudy({ ...good, line: [{ comment: "no move" }] })).toThrow();
  });
});
