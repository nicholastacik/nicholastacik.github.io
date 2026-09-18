import { describe, it, expect } from "vitest";
import type { Study } from "../src/study";
import { normalize, enumerateLines } from "../src/tree";
import { createDrill } from "../src/practice";

// 1.e4 e5 2.Nf3 Nc6 — mainline only.
const study: Study = {
  id: "t", name: "T", side: "white", intro: "i",
  line: [{ san: "e4" }, { san: "e5" }, { san: "Nf3" }, { san: "Nc6" }],
};
const mainline = () => enumerateLines(normalize(study))[0]!.path;

describe("createDrill (White trainee)", () => {
  it("starts with the user to move (White) at the start position", () => {
    const d = createDrill(mainline(), "white");
    const s = d.state();
    expect(s.toMove).toBe("user");
    expect(s.ply).toBe(0);
    expect(s.fen.split(" ")[0]).toBe("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR");
    expect(d.playOpponent()).toBeNull(); // not the opponent's turn
  });

  it("grades the correct book move and advances to the opponent", () => {
    const d = createDrill(mainline(), "white");
    expect(d.submit("e4")).toEqual({ kind: "correct", expected: "e4" });
    expect(d.state().toMove).toBe("opponent");
    expect(d.playOpponent()).toEqual({ san: "e5" }); // applies + returns Black's book reply
    expect(d.state().toMove).toBe("user");
    expect(d.state().ply).toBe(2);
  });

  it("holds and counts a mismatch without advancing", () => {
    const d = createDrill(mainline(), "white");
    const g = d.submit("d4");
    expect(g).toEqual({ kind: "mismatch", expected: "e4", played: "d4" });
    expect(d.state().toMove).toBe("user");
    expect(d.state().ply).toBe(0);
    expect(d.state().mistakes).toBe(1);
  });

  it("reveal applies the book move and marks the ply non-clean", () => {
    const d = createDrill(mainline(), "white");
    expect(d.reveal()).toBe("e4");
    expect(d.state().toMove).toBe("opponent");
    d.playOpponent();
    d.submit("Nf3");
    d.playOpponent(); // Nc6, final ply (opponent)
    const sum = d.summary();
    expect(sum.revealed).toBe(1);
    expect(sum.cleanFirstTry).toBe(1); // only Nf3 was clean first try
  });

  it("reaches 'done' after the final book move (final move by opponent)", () => {
    const d = createDrill(mainline(), "white");
    d.submit("e4"); d.playOpponent(); // e5
    d.submit("Nf3"); d.playOpponent(); // Nc6 (final, opponent)
    expect(d.state().toMove).toBe("done");
    expect(d.summary()).toEqual({ plies: 4, cleanFirstTry: 2, mistakes: 0, revealed: 0 });
  });
});

describe("createDrill (Black trainee)", () => {
  // Same line, but the user plays Black: opponent (White) moves first.
  it("opponent (White) moves first, then the user answers as Black", () => {
    const d = createDrill(mainline(), "black");
    expect(d.state().toMove).toBe("opponent");
    expect(d.playOpponent()).toEqual({ san: "e4" });
    expect(d.state().toMove).toBe("user");
    expect(d.submit("e5")).toEqual({ kind: "correct", expected: "e5" });
  });

  it("the user's final move completes the drill", () => {
    const d = createDrill(mainline(), "black");
    d.playOpponent(); // e4
    d.submit("e5");
    d.playOpponent(); // Nf3
    expect(d.state().toMove).toBe("user");
    d.submit("Nc6"); // final move by the USER
    expect(d.state().toMove).toBe("done");
    expect(d.summary()).toEqual({ plies: 4, cleanFirstTry: 2, mistakes: 0, revealed: 0 });
  });
});
