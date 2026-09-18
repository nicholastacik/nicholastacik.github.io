import { test, before } from "node:test";
import assert from "node:assert/strict";
import { renderFixtureHtml, makeDom, clickId, setChecked, PKEY } from "./harness.js";

let html;
before(() => { html = renderFixtureHtml(); });

// ---- shared driver helpers ----
function selectOnlyAlpha(document) {
  const beta = document.querySelector('.ptopic-cb[value="2"]');
  setChecked(beta, false);
}
function setSize(document, n) {
  const radio = document.querySelector(`input[name=psize][value="${n}"]`);
  setChecked(radio, true);
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

test("flow 1: full single-topic session -> summary (dedupe + era filter)", () => {
  const { document, dom, errors } = makeDom(html);
  try {
    clickId(document, "practice-open");
    selectOnlyAlpha(document);
    setSize(document, 10);
    clickId(document, "practice-start");
    const seen = runToSummary(document, () => "knew");
    // Alpha refs = {g1,g2,dup,a1,a2,old}; 'old' era-excluded, 'dup' deduped -> 5 distinct cards
    assert.equal(seen.length, 5, "deck is 5 distinct eligible cards");
    assert.ok(!seen.includes("old"), "pre-2010 clue excluded");
    assert.equal(seen.filter((x) => x === "dup").length, 1, "duplicate ref deduped");
    assert.ok(!seen.some((x) => ["b1", "b2"].includes(x)), "Topic Beta excluded");
    assert.deepEqual(seen.slice().sort(), ["a1", "a2", "dup", "g1", "g2"], "exact deck identity");
    // summary
    const again = document.getElementById("practice-again");
    assert.ok(again, "summary shown");
    assert.match(document.getElementById("practice-tally").textContent, /✓5/);
    assert.match(document.getElementById("practice-body").textContent, /5 cards scheduled to come back later/);
    assert.equal(document.activeElement, again, "focus on Practice again");
    assert.equal(errors.length, 0, errors.map(String).join(" | "));
  } finally { dom.window.close(); }
});

test("flow 2: a missed card resurfaces once after three intervening cards", () => {
  const { document, dom } = makeDom(html);
  try {
    clickId(document, "practice-open");
    selectOnlyAlpha(document);
    clickId(document, "practice-start");
    // Miss the first card and its single retry; know everything else.
    const firstId = cardId(document);
    const seen = runToSummary(document, (id) => (id === firstId ? "missed" : "knew"));
    const positions = seen.map((x, i) => (x === firstId ? i : -1)).filter((i) => i >= 0);
    assert.equal(positions.length, 2, "missed card seen exactly twice (one retry)");
    assert.equal(positions[1] - positions[0], 4, "retry is after 3 intervening cards (min(3, remaining))");
  } finally { dom.window.close(); }
});

test("flow 3: progress persists across a reload (missed cards come back due)", () => {
  // Session 1: miss two cards (and their retries), know the rest; capture storage.
  let saved;
  let missedIds;
  {
    const { document, dom, window } = makeDom(html);
    const missed = new Set();
    clickId(document, "practice-open");
    selectOnlyAlpha(document);
    clickId(document, "practice-start");
    // miss the first two distinct cards (and any retry of them), know the rest
    const firstTwo = [];
    runToSummary(document, (id) => {
      if (firstTwo.length < 2 && !firstTwo.includes(id)) firstTwo.push(id);
      if (firstTwo.includes(id)) { missed.add(id); return "missed"; }
      return "knew";
    });
    saved = window.localStorage.getItem(PKEY);
    missedIds = [...missed];
    dom.window.close();
  }
  // Session 2: fresh DOM seeded with saved progress; only the due (missed) cards appear.
  {
    const { document, dom } = makeDom(html, { seedStorage: saved });
    clickId(document, "practice-open");
    selectOnlyAlpha(document);
    clickId(document, "practice-start");
    const seen = runToSummary(document, () => "knew");
    assert.deepEqual(seen.slice().sort(), missedIds.slice().sort(),
      "reload surfaces exactly the previously-missed (now-due) cards");
    dom.window.close();
  }
});
