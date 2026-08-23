import { describe, it, expect, vi, beforeEach } from "vitest";
import { GameUI, saveKey } from "../src/ui";
import { createGame } from "../src/engine";

function rng(seed: number) {
  return () => { seed |= 0; seed = (seed + 0x6d2b79f5) | 0; let t = Math.imul(seed ^ (seed>>>15),1|seed); t=(t+Math.imul(t ^ (t>>>7),61|t))^t; return ((t ^ (t>>>14))>>>0)/4294967296; };
}
const cb = () => ({ onClueSubmit: vi.fn(), onCellClick: vi.fn(), onEndGuessing: vi.fn(), onSaveKey: vi.fn(), onNewGame: vi.fn(), onRetry: vi.fn(), onGetClue: vi.fn(), onLoadModels: vi.fn() });

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

  it("shades by the human key card (never the AI's); guessing shows it only when opted in", () => {
    const ui = new GameUI(root, cb());
    const s = createGame({ rng: rng(3) });
    // a cell where the two cards differ, to prove we shade the HUMAN's card
    const i = s.keys.human.findIndex((c, idx) => c !== s.keys.ai[idx]);
    expect(i).toBeGreaterThanOrEqual(0);

    // giving a clue: always shaded by the human card
    ui.render({ ...s, clueGiver: "human" });
    let cells = root.querySelectorAll("[data-cell]");
    expect((cells[i] as HTMLElement).classList.contains(`shade-${s.keys.human[i]}`)).toBe(true);

    // guessing with "Show my key card" ON (default): shaded by the HUMAN card, not the AI's
    ui.render({ ...s, clueGiver: "ai" });
    cells = root.querySelectorAll("[data-cell]");
    expect((cells[i] as HTMLElement).classList.contains(`shade-${s.keys.human[i]}`)).toBe(true);
    expect((cells[i] as HTMLElement).classList.contains(`shade-${s.keys.ai[i]}`)).toBe(false);

    // guessing with the toggle OFF: no shading at all
    const toggle = root.querySelector(".cn-showkey") as HTMLInputElement;
    toggle.checked = false;
    toggle.dispatchEvent(new Event("change")); // re-renders the last state (clueGiver "ai")
    const shaded = root.querySelectorAll(".shade-green, .shade-bystander, .shade-assassin");
    expect(shaded.length).toBe(0);
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

  it("setModels populates the dropdown and getModel returns the selected model", () => {
    const ui = new GameUI(root, cb());
    ui.render(createGame({ rng: rng(3) }));
    ui.setModels(["gpt-4o", "gpt-4o-mini", "o3"]);
    const select = root.querySelector(".cn-model-select") as HTMLSelectElement;
    const values = Array.from(select.options).map((o) => o.value);
    expect(values).toContain("gpt-4o");
    expect(values).toContain("o3");
    expect(values).toContain("__custom__"); // Custom escape hatch always present
    select.value = "o3";
    expect(ui.getModel()).toBe("o3");
  });

  it("selecting Custom reveals a text box and getModel returns the typed value", () => {
    const ui = new GameUI(root, cb());
    ui.render(createGame({ rng: rng(3) }));
    ui.setModels(["gpt-4o"]);
    const select = root.querySelector(".cn-model-select") as HTMLSelectElement;
    const custom = root.querySelector(".cn-model-custom") as HTMLInputElement;
    expect(custom.hidden).toBe(true);
    select.value = "__custom__";
    select.dispatchEvent(new Event("change"));
    expect(custom.hidden).toBe(false);
    custom.value = "gpt-5.9-preview";
    expect(ui.getModel()).toBe("gpt-5.9-preview");
  });

  it("the Load-models button fires onLoadModels", () => {
    const callbacks = cb();
    const ui = new GameUI(root, callbacks);
    ui.render(createGame({ rng: rng(3) }));
    (root.querySelector(".cn-load-models") as HTMLElement).click();
    expect(callbacks.onLoadModels).toHaveBeenCalled();
  });

  it("shows 'Get the AI's clue' only on the AI's clue turn, and it fires onGetClue", () => {
    const callbacks = cb();
    const ui = new GameUI(root, callbacks);
    const s = createGame({ rng: rng(3) });

    // human's clue turn → button hidden
    ui.render({ ...s, clueGiver: "human", phase: "awaitClue" });
    let btn = root.querySelector(".cn-get-clue") as HTMLButtonElement;
    expect(btn.hidden).toBe(true);

    // AI's clue turn → button shown, and clicking it requests the clue
    ui.render({ ...s, clueGiver: "ai", phase: "awaitClue" });
    btn = root.querySelector(".cn-get-clue") as HTMLButtonElement;
    expect(btn.hidden).toBe(false);
    btn.click();
    expect(callbacks.onGetClue).toHaveBeenCalled();
  });

  it("shows 'End guessing' only while YOU are guessing (the AI gave the clue)", () => {
    const ui = new GameUI(root, cb());
    const s = createGame({ rng: rng(3) });
    const btn = () => root.querySelector(".cn-end-guessing") as HTMLButtonElement;

    ui.render({ ...s, clueGiver: "ai", phase: "awaitGuess", currentClue: { word: "X", number: 1, guessesMade: 0 } });
    expect(btn().hidden).toBe(false); // your guessing turn

    ui.render({ ...s, clueGiver: "human", phase: "awaitGuess" }); // AI is guessing — not your control
    expect(btn().hidden).toBe(true);
    ui.render({ ...s, clueGiver: "human", phase: "awaitClue" }); // your clue turn
    expect(btn().hidden).toBe(true);
  });

  it("labels the log 'Game log' and clearLog empties it", () => {
    const ui = new GameUI(root, cb());
    ui.render(createGame({ rng: rng(3) }));
    expect(root.querySelector(".cn-log-panel h3")!.textContent).toBe("Game log");
    ui.log("one");
    ui.log("two");
    expect(root.querySelectorAll(".cn-log-line").length).toBe(2);
    ui.clearLog();
    expect(root.querySelectorAll(".cn-log-line").length).toBe(0);
  });

  it("isDebug reflects the debug checkbox (off by default)", () => {
    const ui = new GameUI(root, cb());
    ui.render(createGame({ rng: rng(3) }));
    expect(ui.isDebug()).toBe(false);
    (root.querySelector(".cn-debug") as HTMLInputElement).checked = true;
    expect(ui.isDebug()).toBe(true);
  });

  it("shows a collapsible rules panel covering the key mechanics", () => {
    const ui = new GameUI(root, cb());
    ui.render(createGame({ rng: rng(3) }));
    const panel = root.querySelector("details.cn-rules") as HTMLDetailsElement;
    expect(panel).not.toBeNull();
    expect(panel.open).toBe(false); // collapsed by default
    expect(panel.querySelector("summary")!.textContent).toMatch(/how to play/i);
    const text = panel.textContent!.toLowerCase();
    expect(text).toContain("15 agents");
    expect(text).toContain("assassin");
    expect(text).toContain("number + 1");
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
