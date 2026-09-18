import { describe, it, expect, vi } from "vitest";
import { renderPractice, type PracticeDeps } from "../src/ui";
import type { Study } from "../src/study";
import type { EngineEval } from "../src/evalProvider";

const study: Study = {
  id: "t", name: "T", side: "white", intro: "i",
  line: [{ san: "e4" }, { san: "e5" }, { san: "Nf3" }, { san: "Nc6" }],
};

function fakeBoard() {
  const calls: string[] = [];
  const handle = {
    setPosition: () => calls.push("setPosition"),
    setMovable: () => calls.push("setMovable"),
    destroy: () => calls.push("destroy"),
  };
  return { make: (_el: HTMLElement, _o: unknown) => handle as never, handle, calls };
}

// Provider whose promises we resolve manually, to drive race tests.
function deferredProvider() {
  const pending: Array<(e: EngineEval) => void> = [];
  const provider = { evaluate: vi.fn(() => new Promise<EngineEval>((res) => pending.push(res))) };
  return { provider, resolveNext: (e: EngineEval) => pending.shift()!(e) };
}

function mount(): HTMLElement {
  const root = document.createElement("div");
  document.body.appendChild(root);
  return root;
}

describe("renderPractice", () => {
  it("renders a line picker with one choice per line", () => {
    const fb = fakeBoard();
    const root = mount();
    renderPractice(root, study, { makeMovableBoard: fb.make, evalProvider: { evaluate: vi.fn() } });
    expect(root.querySelectorAll(".line-choice").length).toBe(1); // mainline only
  });

  it("a correct move advances; the opponent replies automatically", () => {
    const fb = fakeBoard();
    const root = mount();
    const onMove = captureOnMove(fb);
    renderPractice(root, study, { makeMovableBoard: fb.make, evalProvider: { evaluate: vi.fn() } });
    root.querySelector<HTMLElement>(".line-choice")!.click();
    onMove.current("e2", "e4"); // play e4
    expect(root.querySelector(".practice-status")!.textContent).not.toContain("mismatch");
    // board received the opponent's reply position
    expect(fb.calls.filter((c) => c === "setPosition").length).toBeGreaterThan(1);
  });

  it("a mismatch calls the engine and renders the verdict", async () => {
    const dp = deferredProvider();
    const fb = fakeBoard();
    const root = mount();
    const onMove = captureOnMove(fb);
    renderPractice(root, study, { makeMovableBoard: fb.make, evalProvider: dp.provider });
    root.querySelector<HTMLElement>(".line-choice")!.click();
    onMove.current("d2", "d4"); // wrong: book is e4
    expect(root.querySelector(".practice-feedback")!.textContent).toContain("e4"); // book shown immediately
    // two evals requested (baseline + played); resolve them
    dp.resolveNext({ bestMove: "e2e4", cp: 30, mate: null, depth: 12 });
    dp.resolveNext({ bestMove: "e2e4", cp: -230, mate: null, depth: 12 });
    await Promise.resolve(); await Promise.resolve();
    expect(root.querySelector(".practice-feedback")!.textContent).toMatch(/loses/i);
  });

  it("drops a stale engine result that resolves after Exit", async () => {
    const dp = deferredProvider();
    const fb = fakeBoard();
    const root = mount();
    const onMove = captureOnMove(fb);
    renderPractice(root, study, { makeMovableBoard: fb.make, evalProvider: dp.provider });
    root.querySelector<HTMLElement>(".line-choice")!.click();
    onMove.current("d2", "d4");
    root.querySelector<HTMLElement>(".btn-exit")!.click(); // leave before results arrive
    expect(fb.calls).toContain("destroy");
    dp.resolveNext({ bestMove: "e2e4", cp: 30, mate: null, depth: 12 });
    dp.resolveNext({ bestMove: "e2e4", cp: -230, mate: null, depth: 12 });
    await Promise.resolve(); await Promise.resolve();
    // feedback from the abandoned drill must not reappear
    expect(root.querySelector(".practice-feedback")).toBeNull();
  });

  it("degrades gracefully when the engine rejects", async () => {
    const provider = { evaluate: vi.fn(async () => { throw new Error("network"); }) };
    const fb = fakeBoard();
    const root = mount();
    const onMove = captureOnMove(fb);
    renderPractice(root, study, { makeMovableBoard: fb.make, evalProvider: provider });
    root.querySelector<HTMLElement>(".line-choice")!.click();
    onMove.current("d2", "d4");
    await Promise.resolve(); await Promise.resolve();
    const fb2 = root.querySelector(".practice-feedback")!;
    expect(fb2.textContent).toContain("e4"); // still shows the book move
    expect(fb2.textContent).toMatch(/couldn.t reach the engine/i);
  });

  it("persists the completed line id to storage, and the picker marks it next time", () => {
    const fb = fakeBoard();
    const root = mount();
    const onMove = captureOnMove(fb);
    const store = fakeStorage();
    renderPractice(root, study, { makeMovableBoard: fb.make, evalProvider: { evaluate: vi.fn() }, storage: store });
    root.querySelector<HTMLElement>(".line-choice")!.click();
    onMove.current("e2", "e4"); // correct: opponent replies e5
    onMove.current("g1", "f3"); // correct: opponent replies Nc6 -> line done
    const saved = JSON.parse(store.getItem("chess:practice:t")!);
    expect(saved).toContain("e4 e5 Nf3 Nc6");

    // Re-rendering the picker (e.g. re-entering practice) reflects completion.
    const root2 = mount();
    renderPractice(root2, study, { makeMovableBoard: fb.make, evalProvider: { evaluate: vi.fn() }, storage: store });
    expect(root2.querySelector(".line-choice")!.classList.contains("completed")).toBe(true);
  });

  it("does not let a stale wrong-move analysis overwrite feedback at a new ply after a correct retry", async () => {
    const dp = deferredProvider();
    const fb = fakeBoard();
    const root = mount();
    const onMove = captureOnMove(fb);
    renderPractice(root, study, { makeMovableBoard: fb.make, evalProvider: dp.provider });
    root.querySelector<HTMLElement>(".line-choice")!.click();
    onMove.current("d2", "d4"); // wrong at ply 0 (book is e4); analysis kicked off in the background
    onMove.current("e2", "e4"); // retry correctly: ply -> 1, opponent auto-replies e5 -> ply 2
    const feedback = root.querySelector(".practice-feedback")!;
    expect(feedback.textContent).toBe(""); // cleared by the correct move; nothing stale shown yet
    // The abandoned wrong-move analysis (baseline + played) resolves late, after the drill
    // has moved on to a new decision point. `mistakes` hasn't changed since the wrong move,
    // so only a ply check (not just session + mistakes) can catch this.
    dp.resolveNext({ bestMove: "e2e4", cp: 30, mate: null, depth: 12 });
    dp.resolveNext({ bestMove: "e2e4", cp: -230, mate: null, depth: 12 });
    await Promise.resolve(); await Promise.resolve();
    expect(feedback.textContent).toBe("");
    expect(feedback.textContent).not.toMatch(/loses/i);
  });

  it("disables Reveal once the drill is done; clicking it then is a no-op", () => {
    const fb = fakeBoard();
    const root = mount();
    const onMove = captureOnMove(fb);
    renderPractice(root, study, { makeMovableBoard: fb.make, evalProvider: { evaluate: vi.fn() } });
    root.querySelector<HTMLElement>(".line-choice")!.click();
    const revealBtn = root.querySelector<HTMLButtonElement>(".btn-reveal")!;
    expect(revealBtn.disabled).toBe(false); // it's the user's turn at the start
    onMove.current("e2", "e4"); // correct -> opponent replies e5
    onMove.current("g1", "f3"); // correct -> opponent replies Nc6 -> line done
    expect(revealBtn.disabled).toBe(true);
    expect(() => revealBtn.click()).not.toThrow();
  });

  it("Restart destroys the previous movable board before creating a new one", () => {
    const fb = fakeBoard();
    const root = mount();
    renderPractice(root, study, { makeMovableBoard: fb.make, evalProvider: { evaluate: vi.fn() } });
    root.querySelector<HTMLElement>(".line-choice")!.click();
    const destroysBeforeRestart = fb.calls.filter((c) => c === "destroy").length;
    root.querySelector<HTMLElement>(".btn-restart")!.click();
    const destroysAfterRestart = fb.calls.filter((c) => c === "destroy").length;
    expect(destroysAfterRestart).toBe(destroysBeforeRestart + 1);
  });

  it("tolerates a corrupt storage value without throwing", () => {
    const fb = fakeBoard();
    const root = mount();
    const store = fakeStorage();
    store.setItem("chess:practice:t", "{not json");
    expect(() =>
      renderPractice(root, study, { makeMovableBoard: fb.make, evalProvider: { evaluate: vi.fn() }, storage: store }),
    ).not.toThrow();
    expect(root.querySelectorAll(".line-choice").length).toBe(1);
  });
});

// Minimal in-memory Storage fake.
function fakeStorage(): Storage {
  const data = new Map<string, string>();
  return {
    getItem: (k: string) => (data.has(k) ? data.get(k)! : null),
    setItem: (k: string, v: string) => { data.set(k, v); },
    removeItem: (k: string) => { data.delete(k); },
    clear: () => { data.clear(); },
    key: (i: number) => [...data.keys()][i] ?? null,
    get length() { return data.size; },
  };
}

// Helper: renderPractice passes an onMove callback into makeMovableBoard; capture it.
function captureOnMove(fb: ReturnType<typeof fakeBoard>) {
  const ref: { current: (from: string, to: string, promo?: string) => void } = { current: () => {} };
  const orig = fb.make;
  (fb as { make: PracticeDeps["makeMovableBoard"] }).make = (el, opts) => {
    ref.current = (opts as { onMove: typeof ref.current }).onMove;
    return orig(el, opts as never);
  };
  return ref;
}
