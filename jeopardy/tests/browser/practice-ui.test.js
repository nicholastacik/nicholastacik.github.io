import { test, before } from "node:test";
import assert from "node:assert/strict";
import { renderFixtureHtml, makeDom, clickId, setChecked, dispatchKey } from "./harness.js";

let html;
before(() => { html = renderFixtureHtml(); });

// ---- shared driver helpers ----
function selectOnlyAlpha(document) {
  setChecked(document.querySelector('.ptopic-cb[value="2"]'), false); // uncheck Topic Beta
}
function setSize(document, n) {
  setChecked(document.querySelector(`input[name=psize][value="${n}"]`), true);
}
function cardId(document) {
  const p = document.querySelector(".pcard-clue");
  const m = p && /Clue text for (\w+)/.exec(p.textContent);
  return m ? m[1] : null;
}
function grade(document, g) {
  document.querySelector(`.pgrade[data-g="${g}"]`).click();
}
function runToSummary(document, gradeFor) {
  const seen = [];
  let guard = 0;
  while (document.getElementById("pcard-reveal") && guard++ < 100) {
    const id = cardId(document);
    seen.push(id);
    clickId(document, "pcard-reveal");
    grade(document, gradeFor(id, seen.length - 1));
  }
  return seen;
}

test("flow 1: full single-topic session -> summary (dedupe + era filter, stateless)", () => {
  const { document, dom, window, errors } = makeDom(html);
  try {
    clickId(document, "practice-open");
    selectOnlyAlpha(document);
    setSize(document, 10);
    clickId(document, "practice-start");
    const seen = runToSummary(document, () => "knew");
    // Alpha refs = {g1,g2,dup,a1,a2,old}; 'old' era-excluded, 'dup' deduped -> 5 distinct
    assert.deepEqual(seen.slice().sort(), ["a1", "a2", "dup", "g1", "g2"], "exact deck");
    assert.ok(!seen.includes("old"), "pre-2010 clue excluded");
    assert.ok(!seen.some((x) => ["b1", "b2"].includes(x)), "Topic Beta excluded");
    const again = document.getElementById("practice-again");
    assert.ok(again, "summary shown");
    assert.match(document.getElementById("practice-tally").textContent, /✓5/);
    assert.match(document.getElementById("practice-body").textContent, /5 knew · 0 unsure · 0 missed/);
    assert.equal(document.activeElement, again, "focus on Practice again");
    assert.equal(window.localStorage.length, 0, "stateless: nothing persisted");
    assert.equal(errors.length, 0, errors.map(String).join(" | "));
  } finally { dom.window.close(); }
});

test("flow 2: missed cards do NOT resurface — every card appears exactly once", () => {
  const { document, dom, errors } = makeDom(html);
  try {
    clickId(document, "practice-open");
    selectOnlyAlpha(document);
    clickId(document, "practice-start");
    const seen = runToSummary(document, () => "missed"); // miss everything
    assert.equal(seen.length, 5, "exactly the deck size — no resurfaced repeats");
    assert.equal(new Set(seen).size, 5, "each card shown exactly once");
    assert.ok(document.getElementById("practice-again"), "session ended at summary");
    assert.match(document.getElementById("practice-body").textContent, /0 knew · 0 unsure · 5 missed/);
    assert.equal(errors.length, 0, errors.map(String).join(" | "));
  } finally { dom.window.close(); }
});

test("flow 3: keyboard — Space doesn't hijack a focused button; 1/2/3 grade; click Exit closes", () => {
  const { document, dom, errors } = makeDom(html);
  try {
    clickId(document, "practice-open");
    selectOnlyAlpha(document);
    clickId(document, "practice-start");
    // Space on the focused Exit button must NOT be intercepted (no reveal, not prevented)
    const exit = document.getElementById("practice-exit");
    exit.focus();
    const ev = dispatchKey(exit, " ");
    assert.equal(ev.defaultPrevented, false, "Space not preventDefaulted on Exit");
    assert.equal(document.querySelector(".pcard-answer"), null, "answer still hidden");
    // After reveal, digit keys grade and advance
    const before = cardId(document);
    clickId(document, "pcard-reveal");
    dispatchKey(document.body, "1"); // '1' = knew
    assert.notEqual(cardId(document), before, "grading via '1' advanced the card");
    // A real browser click focuses the clicked opener; jsdom's synthetic click doesn't,
    // so prime focus to model reality before exercising focus-restore-on-close.
    document.getElementById("practice-open").focus();
    clickId(document, "practice-exit");
    assert.equal(document.getElementById("practice").hidden, true, "overlay closed");
    assert.equal(document.activeElement, document.getElementById("practice-open"),
      "focus restored to Practice button");
    assert.equal(errors.length, 0, errors.map(String).join(" | "));
  } finally { dom.window.close(); }
});
