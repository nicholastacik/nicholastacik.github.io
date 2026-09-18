// Test-only helpers for driving the real generated research page in jsdom.
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, resolve } from "node:path";
import { JSDOM, VirtualConsole } from "jsdom";

export const FIXED_NOW = Date.UTC(2026, 0, 15); // fixed clock for reproducible due-dates
export const PKEY = "jeopardy-practice-v1";

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

export function makeDom(html, { seedStorage, quota } = {}) {
  const errors = [];
  const virtualConsole = new VirtualConsole();
  virtualConsole.on("jsdomError", (e) => errors.push(e));
  const options = {
    runScripts: "dangerously",
    url: "https://practice.test/",
    virtualConsole,
    beforeParse(window) {
      window.Date.now = () => FIXED_NOW;
      window.Math.random = () => 0;
      window.addEventListener("error", (e) => errors.push(e.error || new Error(e.message)));
      window.addEventListener("unhandledrejection", (e) => errors.push(e.reason));
      if (seedStorage !== undefined) window.localStorage.setItem(PKEY, seedStorage);
    },
  };
  if (quota !== undefined) options.storageQuota = quota;
  const dom = new JSDOM(html, options);
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
