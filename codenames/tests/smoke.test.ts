import { describe, it, expect } from "vitest";
import { hello } from "../src/smoke";

describe("scaffold", () => {
  it("runs vitest", () => {
    expect(hello()).toBe("codenames");
  });
});
