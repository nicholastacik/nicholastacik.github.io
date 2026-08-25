import { describe, it, expect } from "vitest";

describe("scaffold", () => {
  it("runs the vitest + jsdom environment", () => {
    const el = document.createElement("div");
    el.textContent = "ok";
    expect(el.textContent).toBe("ok");
  });
});
