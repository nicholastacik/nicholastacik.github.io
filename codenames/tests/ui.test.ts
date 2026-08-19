import { describe, it, expect, vi, beforeEach } from "vitest";
import { GameUI, saveKey } from "../src/ui";
import { createGame } from "../src/engine";

function rng(seed: number) {
  return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed>>>15),1|seed); t=(t+Math.imul(t ^ (t>>>7),61|t))^t; return ((t ^ (t>>>14))>>>0)/4294967296; };
}
const cb = () => ({ onClueSubmit: vi.fn(), onCellClick: vi.fn(), onEndGuessing: vi.fn(), onSaveKey: vi.fn(), onNewGame: vi.fn() });

describe("GameUI", () => {
  let root: HTMLElement;
  beforeEach(() => { root = document.createElement("div"); document.body.appendChild(root); });

  it("renders 25 cells", () => {
    const ui = new GameUI(root, cb());
    ui.render(createGame({ rng: rng(3) }));
    expect(root.querySelectorAll("[data-cell]").length).toBe(25);
  });

  it("clicking a cell fires onCellClick with its word", () => {
    const callbacks = cb();
    const ui = new GameUI(root, callbacks);
    const s = createGame({ rng: rng(3) });
    ui.render({ ...s, phase: "awaitGuess", currentClue: { word: "X", number: 1, guessesMade: 0 }, clueGiver: "human" });
    (root.querySelector("[data-cell]") as HTMLElement).click();
    expect(callbacks.onCellClick).toHaveBeenCalledWith(s.words[0]);
  });

  it("log appends a line", () => {
    const ui = new GameUI(root, cb());
    ui.render(createGame({ rng: rng(3) }));
    ui.log("hello");
    expect(root.textContent).toContain("hello");
  });

  it("never writes the key to localStorage", () => {
    const ui = new GameUI(root, cb());
    ui.render(createGame({ rng: rng(3) }));
    // save with remember=false uses sessionStorage; localStorage stays empty
    // (deviation from brief: call the exported saveKey directly rather than
    // the optional-chained (ui as any).saveKeyForTest?.(...), which would
    // pass vacuously if that method were absent)
    saveKey("sk-secret", false);
    expect(localStorage.getItem("openai_key")).toBeNull();
    expect(sessionStorage.getItem("openai_key")).toBeNull();
  });
});
