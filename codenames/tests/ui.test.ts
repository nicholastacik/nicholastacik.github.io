import { describe, it, expect, vi, beforeEach } from "vitest";
import { GameUI, saveKey } from "../src/ui";
import { createGame } from "../src/engine";

function rng(seed: number) {
  return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed>>>15),1|seed); t=(t+Math.imul(t ^ (t>>>7),61|t))^t; return ((t ^ (t>>>14))>>>0)/4294967296; };
}
const cb = () => ({ onClueSubmit: vi.fn(), onCellClick: vi.fn(), onEndGuessing: vi.fn(), onSaveKey: vi.fn(), onNewGame: vi.fn(), onRetry: vi.fn() });

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

  it("shades cells by the human keycard only when clueGiver is human, never the AI's", () => {
    const ui = new GameUI(root, cb());
    const s = createGame({ rng: rng(3) });

    ui.render({ ...s, clueGiver: "human" });
    const humanShaded = root.querySelectorAll(
      ".cn-cell.shade-green, .cn-cell.shade-bystander, .cn-cell.shade-assassin"
    );
    // all 25 cells are unrevealed at game start, so all 25 get a shade class
    expect(humanShaded.length).toBe(25);
    const firstCell = root.querySelector("[data-cell]") as HTMLElement;
    expect(firstCell.classList.contains(`shade-${s.keys.human[0]}`)).toBe(true);

    ui.render({ ...s, clueGiver: "ai" });
    const aiShaded = root.querySelectorAll(
      ".shade-green, .shade-bystander, .shade-assassin"
    );
    expect(aiShaded.length).toBe(0);
  });

  it("shows a win badge when status is won", () => {
    const ui = new GameUI(root, cb());
    const s = createGame({ rng: rng(3) });
    ui.render({ ...s, status: "won" });
    expect(root.querySelector(".cn-badge-won")).not.toBeNull();
    expect(root.textContent).toContain("YOU WIN");
  });

  it("shows a loss badge when status is lost", () => {
    const ui = new GameUI(root, cb());
    const s = createGame({ rng: rng(3) });
    ui.render({ ...s, status: "lost" });
    expect(root.querySelector(".cn-badge-lost")).not.toBeNull();
    expect(root.textContent).toContain("YOU LOSE");
  });

  it("shows the retry button when setError is called with a message, hides it when cleared", () => {
    const ui = new GameUI(root, cb());
    ui.render(createGame({ rng: rng(3) }));
    ui.setError("Rate limited — wait and retry.");
    const retryBtn = root.querySelector(".cn-retry") as HTMLButtonElement;
    expect(retryBtn).not.toBeNull();
    expect(retryBtn.hidden).toBe(false);
    expect(root.textContent).toContain("Rate limited — wait and retry.");

    ui.setError(null);
    expect(retryBtn.hidden).toBe(true);
  });

  it("clicking retry fires onRetry", () => {
    const callbacks = cb();
    const ui = new GameUI(root, callbacks);
    ui.render(createGame({ rng: rng(3) }));
    ui.setError("Oops");
    (root.querySelector(".cn-retry") as HTMLElement).click();
    expect(callbacks.onRetry).toHaveBeenCalled();
  });

  it("Clear key wipes the input and removes the key from sessionStorage", () => {
    const ui = new GameUI(root, cb());
    ui.render(createGame({ rng: rng(3) }));
    const keyInput = root.querySelector(".cn-key-input") as HTMLInputElement;
    keyInput.value = "sk-secret";
    saveKey("sk-secret", true); // simulate a remembered key sitting in sessionStorage
    expect(sessionStorage.getItem("openai_key")).toBe("sk-secret");

    const clearBtn = root.querySelector(".cn-clear-key") as HTMLButtonElement;
    expect(clearBtn).not.toBeNull();
    clearBtn.click();

    expect(keyInput.value).toBe("");
    expect(sessionStorage.getItem("openai_key")).toBeNull();
    expect(localStorage.getItem("openai_key")).toBeNull();
  });

  it("shows a privacy panel explaining key handling, with a source link", () => {
    const ui = new GameUI(root, cb());
    ui.render(createGame({ rng: rng(3) }));
    const panel = root.querySelector(".cn-privacy");
    expect(panel).not.toBeNull();
    const text = panel!.textContent!.toLowerCase();
    expect(text).toContain("only to openai"); // sent only to OpenAI
    expect(text).toContain("never"); // not saved/logged claims
    const link = panel!.querySelector("a") as HTMLAnchorElement;
    expect(link).not.toBeNull();
    expect(link.getAttribute("href")).toContain("github.com");
    expect(link.getAttribute("rel")).toContain("noopener");
  });
});
