import { describe, it, expect } from "vitest";
import { legalDests } from "../src/board";

describe("legalDests", () => {
  it("returns 20 origin→dest moves for the start position (16 pawn + 4 knight sources)", () => {
    const d = legalDests("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1");
    // 8 pawns each with 2 dests, 2 knights each with 2 dests → sources: a2..h2, b1, g1
    expect(d.get("e2")).toEqual(expect.arrayContaining(["e3", "e4"]));
    expect(d.get("g1")).toEqual(expect.arrayContaining(["f3", "h3"]));
    const totalMoves = [...d.values()].reduce((n, arr) => n + arr.length, 0);
    expect(totalMoves).toBe(20);
  });
});
