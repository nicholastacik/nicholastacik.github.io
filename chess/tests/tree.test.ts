import { describe, it, expect } from "vitest";
import type { Study } from "../src/study";
import {
  normalize,
  pathSans,
  replay,
  positionAt,
  validateLegality,
  stepForward,
  stepBack,
  siblings,
  switchSibling,
  enumerateLines,
  type Path,
} from "../src/tree";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR";
const AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR";

const study: Study = {
  id: "t",
  name: "T",
  side: "white",
  intro: "intro",
  line: [
    { san: "e4" },
    { san: "e5" },
    {
      san: "Nf3",
      alts: [[{ san: "Bc4" }]], // alternative to Nf3 at White's 2nd move
    },
    { san: "Nc6" },
  ],
};

describe("normalize", () => {
  it("builds a root with null san and mainline at children[0]", () => {
    const root = normalize(study);
    expect(root.san).toBeNull();
    expect(root.children[0]!.san).toBe("e4");
    expect(root.children[0]!.children[0]!.san).toBe("e5");
  });

  it("places alts as siblings of the mainline node under the same parent", () => {
    const root = normalize(study);
    const afterE5 = root.children[0]!.children[0]!; // node reached after 1.e4 e5
    expect(afterE5.children.map((c) => c.san)).toEqual(["Nf3", "Bc4"]);
  });
});

describe("replay", () => {
  it("returns the start position for no moves", () => {
    expect(replay([]).fen.split(" ")[0]).toBe(START);
  });

  it("computes position and lastMove after e4", () => {
    const r = replay(["e4"]);
    expect(r.fen.split(" ")[0]).toBe(AFTER_E4);
    expect(r.lastMove).toEqual(["e2", "e4"]);
  });

  it("throws on an illegal move", () => {
    expect(() => replay(["e5"])).toThrow();
  });

  it("throws on a null move token (chess.js otherwise accepts '--')", () => {
    expect(() => replay(["e4", "--", "d4"])).toThrow();
  });

  it("throws on an annotated null move (chess.js strips +/#/?/! before matching)", () => {
    expect(() => replay(["e4", "--+"])).toThrow();
    expect(() => replay(["e4", "--!?"])).toThrow();
  });
});

describe("navigation", () => {
  it("pathSans skips the root", () => {
    const root = normalize(study);
    const path: Path = [root, root.children[0]!]; // root -> e4
    expect(pathSans(path)).toEqual(["e4"]);
  });

  it("positionAt replays the path", () => {
    const root = normalize(study);
    const path: Path = [root, root.children[0]!];
    expect(positionAt(path).lastMove).toEqual(["e2", "e4"]);
  });

  it("stepForward follows the mainline; stepBack reverses it", () => {
    const root = normalize(study);
    let path: Path | null = [root];
    path = stepForward(path!);
    expect(path![path!.length - 1]!.san).toBe("e4");
    path = stepBack(path!);
    expect(path!.length).toBe(1);
    expect(stepBack(path!)).toBeNull();
  });

  it("siblings returns alternatives at the branch point; switchSibling swaps line", () => {
    const root = normalize(study);
    // path root -> e4 -> e5 -> Nf3
    const e4 = root.children[0]!;
    const e5 = e4.children[0]!;
    const nf3 = e5.children[0]!;
    const path: Path = [root, e4, e5, nf3];
    expect(siblings(path).map((n) => n.san)).toEqual(["Nf3", "Bc4"]);
    const bc4 = e5.children[1]!;
    const swapped = switchSibling(path, bc4);
    expect(swapped[swapped.length - 1]!.san).toBe("Bc4");
    expect(pathSans(swapped)).toEqual(["e4", "e5", "Bc4"]);
  });
});

describe("validateLegality", () => {
  it("returns [] when all moves are legal", () => {
    expect(validateLegality(normalize(study))).toEqual([]);
  });

  it("reports an illegal move", () => {
    const bad: Study = { ...study, line: [{ san: "e4" }, { san: "e4" }] };
    const errs = validateLegality(normalize(bad));
    expect(errs.length).toBe(1);
    expect(errs[0]).toContain("e4");
  });

  it("reports a null move as illegal", () => {
    const bad: Study = { ...study, line: [{ san: "e4" }, { san: "--" }, { san: "d4" }] };
    const errs = validateLegality(normalize(bad));
    expect(errs.length).toBeGreaterThan(0);
    expect(errs.some((e) => e.includes("--"))).toBe(true);
  });
});

describe("enumerateLines", () => {
  // study: e4 e5 { Nf3, alt Bc4 } Nc6 ; i.e. after 1.e4 e5, White plays Nf3
  // (mainline) or Bc4 (alt). Two root-to-leaf paths.
  const s: Study = {
    id: "t", name: "T", side: "white", intro: "i",
    line: [
      { san: "e4" },
      { san: "e5" },
      { san: "Nf3", alts: [[{ san: "Bc4" }, { san: "Bc5" }]] },
      { san: "Nc6" },
    ],
  };

  it("yields one entry per root-to-leaf path, mainline first", () => {
    const lines = enumerateLines(normalize(s));
    expect(lines.length).toBe(2);
    expect(lines[0]!.label).toBe("Mainline");
    expect(pathSans(lines[0]!.path)).toEqual(["e4", "e5", "Nf3", "Nc6"]);
    expect(pathSans(lines[1]!.path)).toEqual(["e4", "e5", "Bc4", "Bc5"]);
  });

  it("gives each path a stable id from its canonical SAN", () => {
    const lines = enumerateLines(normalize(s));
    expect(lines[0]!.id).toBe("e4 e5 Nf3 Nc6");
    expect(lines[1]!.id).toBe("e4 e5 Bc4 Bc5");
    expect(lines[0]!.id).not.toBe(lines[1]!.id);
  });

  it("distinguishes two paths that would collide on a first-divergence label", () => {
    // Two alts that both start with the same move Bc4 but then diverge, so a
    // 'first divergence' label alone would collide; ids must differ.
    const s2: Study = {
      id: "t2", name: "T2", side: "white", intro: "i",
      line: [
        { san: "e4" },
        { san: "e5", alts: [
          [{ san: "d5" }, { san: "exd5" }, { san: "Qxd5" }],
          [{ san: "d5" }, { san: "Nc3" }, { san: "dxe4" }],
        ] },
      ],
    };
    const ids = enumerateLines(normalize(s2)).map((l) => l.id);
    expect(new Set(ids).size).toBe(ids.length); // all unique
  });
});
