// Test-only helpers for driving the real generated research page in jsdom.
// Browser-only checklist — NOT covered by jsdom (verify manually in a real browser):
//  * native Space/Enter ACTIVATION of Exit/Reveal/grade buttons (jsdom runs activation
//    only for real click events, not dispatched key events);
//  * Tab focus-trap cycling (jsdom has no layout, so offsetParent is always null);
//  * inert background non-interactivity (jsdom does not implement `inert`);
//  * visual focus rings and prefers-reduced-motion.
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { JSDOM, VirtualConsole } from "jsdom";

// This file lives at <repo>/jeopardy/tests/browser/harness.js -> repo root is three up.
const REPO_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..", "..", "..");

export function renderFixtureHtml() {
  return execFileSync(
    "uv",
    ["run", "--frozen", "--group", "analysis", "python", "-m",
     "jeopardy.tests.browser.render_fixture"],
    { cwd: REPO_ROOT, encoding: "utf8", maxBuffer: 64 * 1024 * 1024 }
  );
}

export function makeDom(html) {
  const errors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", (e) => errors.push(e));
  const dom = new JSDOM(html, {
    runScripts: "dangerously",
    url: "https://practice.test/",
    virtualConsole,
    beforeParse(window) {
      window.Math.random = () => 0; // deterministic pickSession shuffle
      window.addEventListener("error", (e) => errors.push(e.error || new Error(e.message)));
      window.addEventListener("unhandledrejection", (e) => errors.push(e.reason));
    },
  });
  return { dom, window: dom.window, document: dom.window.document, errors };
}

export function clickId(document, id) {
  const el = document.getElementById(id);
  if (!el) throw new Error("no element #" + id);
  el.click();
}

export function setChecked(el, value) {
  el.checked = value;
  el.dispatchEvent(new el.ownerDocument.defaultView.Event("change", { bubbles: true }));
}

export function dispatchKey(el, key) {
  const KeyboardEvent = el.ownerDocument.defaultView.KeyboardEvent;
  const ev = new KeyboardEvent("keydown", { key, bubbles: true, cancelable: true });
  el.dispatchEvent(ev);
  return ev;
}
