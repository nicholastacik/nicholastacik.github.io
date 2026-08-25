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
});
