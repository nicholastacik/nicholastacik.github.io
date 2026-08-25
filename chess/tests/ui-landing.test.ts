import { describe, it, expect, vi } from "vitest";
import { renderLanding } from "../src/ui";
import type { Study } from "../src/study";

const studies: Study[] = [
  { id: "italian-game", name: "Italian Game", eco: "C50", side: "white", intro: "i", line: [{ san: "e4" }] },
  { id: "french-defense", name: "French Defense", eco: "C00", side: "black", intro: "i", line: [{ san: "e4" }] },
];

function mount(): HTMLElement {
  const root = document.createElement("div");
  document.body.appendChild(root);
  return root;
}

describe("renderLanding", () => {
  it("renders one card per study", () => {
    const root = mount();
    renderLanding(root, studies, () => {});
    expect(root.querySelectorAll(".study-card").length).toBe(2);
  });

  it("filters cards by the search box (name or eco)", () => {
    const root = mount();
    renderLanding(root, studies, () => {});
    const search = root.querySelector<HTMLInputElement>(".study-search")!;
    search.value = "french";
    search.dispatchEvent(new Event("input"));
    const visible = [...root.querySelectorAll<HTMLElement>(".study-card")].filter(
      (c) => c.style.display !== "none",
    );
    expect(visible.length).toBe(1);
    expect(visible[0]!.dataset.id).toBe("french-defense");
  });

  it("calls onOpen with the study id when a card is clicked", () => {
    const root = mount();
    const onOpen = vi.fn();
    renderLanding(root, studies, onOpen);
    root.querySelector<HTMLElement>('.study-card[data-id="italian-game"]')!.click();
    expect(onOpen).toHaveBeenCalledWith("italian-game");
  });
});
