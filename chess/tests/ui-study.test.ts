import { describe, it, expect } from "vitest";
import { renderStudyView, type BoardHandle } from "../src/ui";
import type { Study } from "../src/study";

const study: Study = {
  id: "t",
  name: "T",
  side: "white",
  intro: "INTRO TEXT",
  line: [
    { san: "e4", comment: "first move" },
    { san: "e5", comment: "reply" },
    { san: "Nf3", comment: "mainline", alts: [[{ san: "Bc4", comment: "alt line" }]] },
  ],
};

interface Recorded { fen: string; lastMove?: [string, string]; orientation: string }

function fakeBoardFactory() {
  const calls: Recorded[] = [];
  const make = (_el: HTMLElement, orientation: "white" | "black"): BoardHandle => ({
    setPosition(fen, lastMove, o) {
      calls.push({ fen, lastMove, orientation: o });
    },
  });
  return { make, calls };
}

function mount(): HTMLElement {
  const root = document.createElement("div");
  document.body.appendChild(root);
  return root;
}

describe("renderStudyView", () => {
  it("starts at the root: shows the intro and the start position", () => {
    const root = mount();
    const fb = fakeBoardFactory();
    renderStudyView(root, study, { makeBoard: fb.make });
    expect(root.querySelector(".annotation")!.textContent).toContain("INTRO TEXT");
    const last = fb.calls[fb.calls.length - 1]!;
    expect(last.fen.split(" ")[0]).toBe("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR");
  });

  it("Next advances the mainline and updates the annotation + board", () => {
    const root = mount();
    const fb = fakeBoardFactory();
    renderStudyView(root, study, { makeBoard: fb.make });
    root.querySelector<HTMLElement>(".btn-next")!.click();
    expect(root.querySelector(".annotation")!.textContent).toContain("first move");
    const last = fb.calls[fb.calls.length - 1]!;
    expect(last.lastMove).toEqual(["e2", "e4"]);
  });

  it("clicking a variation move jumps the board to that line", () => {
    const root = mount();
    const fb = fakeBoardFactory();
    renderStudyView(root, study, { makeBoard: fb.make });
    // Find the alt move Bc4 and click it.
    const moves = [...root.querySelectorAll<HTMLElement>(".variation-tree .move")];
    const bc4 = moves.find((m) => m.textContent!.includes("Bc4"))!;
    bc4.click();
    expect(root.querySelector(".annotation")!.textContent).toContain("alt line");
    const last = fb.calls[fb.calls.length - 1]!;
    expect(last.lastMove).toEqual(["f1", "c4"]);
    expect(bc4.classList.contains("current")).toBe(true);
  });

  it("defaults orientation to black for a black-side study", () => {
    const root = mount();
    const fb = fakeBoardFactory();
    renderStudyView(root, { ...study, side: "black" }, { makeBoard: fb.make });
    expect(fb.calls[fb.calls.length - 1]!.orientation).toBe("black");
  });
});
