import { test, before } from "node:test";
import assert from "node:assert/strict";
import { renderFixtureHtml, makeDom } from "./harness.js";

let html;
before(() => { html = renderFixtureHtml(); });

test("fixture page loads in jsdom with the Practice entry and no script errors", () => {
  const { document, errors, dom } = makeDom(html);
  try {
    assert.ok(document.getElementById("practice-open"), "Practice button present");
    assert.ok(document.getElementById("practice"), "overlay present");
    assert.equal(errors.length, 0, "no page-script errors: " + errors.map(String).join(" | "));
  } finally {
    dom.window.close();
  }
});
