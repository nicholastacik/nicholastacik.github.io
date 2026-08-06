import { test } from "node:test";
import assert from "node:assert/strict";
import { parseToolLine, buildToolLine, mergeOverlay } from "./events-core.js";

test("parseToolLine reads all fields", () => {
  const r = parseToolLine(
    "{{tool evt-003 | hidden=yes | calendar=no | recurrence=weekly, Tuesdays | image=https://x/y.png}}");
  assert.deepEqual(r, {
    id: "evt-003", hidden: true, calendar: false,
    recurrence: "weekly, Tuesdays", image: "https://x/y.png",
  });
});

test("parseToolLine maps none/auto to null", () => {
  const r = parseToolLine(
    "{{tool mus-007 | hidden=no | calendar=no | recurrence=none | image=auto}}");
  assert.deepEqual(r, {
    id: "mus-007", hidden: false, calendar: false, recurrence: null, image: null,
  });
});

test("parseToolLine returns null on non-tool text", () => {
  assert.equal(parseToolLine("Just For Laughs, downtown"), null);
});

test("buildToolLine round-trips with parseToolLine", () => {
  const line =
    "{{tool evt-010 | hidden=yes | calendar=yes | recurrence=none | image=auto}}";
  assert.equal(buildToolLine("evt-010", parseToolLine(line)), line);
});

test("buildToolLine defaults null recurrence/image to none/auto", () => {
  assert.equal(
    buildToolLine("brd-001", { hidden: false, calendar: false, recurrence: null, image: null }),
    "{{tool brd-001 | hidden=no | calendar=no | recurrence=none | image=auto}}");
});

test("mergeOverlay overrides hidden by id, leaves others untouched", () => {
  const events = [{ id: "a", hidden: false }, { id: "b", hidden: false }];
  const merged = mergeOverlay(events, { a: { hidden: true } });
  assert.equal(merged[0].hidden, true);
  assert.equal(merged[1].hidden, false);
  assert.equal(events[0].hidden, false); // input not mutated
});
