import { describe, it, expect } from "vitest";
import { aggregate, type GameResult } from "../eval/metrics";

describe("aggregate", () => {
  it("computes rates over results", () => {
    const rs: GameResult[] = [
      { won: true, agentsFound: 15, hitAssassin: false, reachedSuddenDeath: false, clues: 6, illegalClues: 1, turnsUsed: 6 },
      { won: false, agentsFound: 8, hitAssassin: true, reachedSuddenDeath: true, clues: 4, illegalClues: 0, turnsUsed: 4 },
    ];
    const a = aggregate(rs);
    expect(a.games).toBe(2);
    expect(a.winRate).toBeCloseTo(0.5);
    expect(a.assassinRate).toBeCloseTo(0.5);
    expect(a.suddenDeathRate).toBeCloseTo(0.5);
    expect(a.avgAgents).toBeCloseTo(11.5);
    expect(a.avgTurnsUsed).toBeCloseTo(5);
    // 1 illegal attempt out of (10 delivered + 1 illegal) = 11 attempts
    expect(a.illegalClueRate).toBeCloseTo(1 / 11);
  });
});
