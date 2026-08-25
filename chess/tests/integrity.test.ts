import { describe, it, expect } from "vitest";
import { loadStudies } from "../src/study";
import { normalize, validateLegality } from "../src/tree";

describe("study integrity", () => {
  const studies = loadStudies();

  it("discovers at least one study", () => {
    expect(studies.length).toBeGreaterThan(0);
  });

  it("every study id matches its own slug rule and is unique", () => {
    const ids = studies.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const id of ids) expect(id).toMatch(/^[a-z0-9-]+$/);
  });

  it("every move in every study is legal", () => {
    for (const study of studies) {
      const errors = validateLegality(normalize(study));
      expect(errors, `${study.id}: ${errors.join("; ")}`).toEqual([]);
    }
  });
});
