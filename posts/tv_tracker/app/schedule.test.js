import { test } from "node:test";
import assert from "node:assert/strict";
import { dayLabel, inWindow, scheduleDays, scheduleHeader, timeLabel, torontoDate, windowStart } from "./state.js";

test("torontoDate uses Eastern time", () => {
  assert.equal(torontoDate(new Date("2026-09-29T01:30:00Z")), "2026-09-28");
  assert.equal(torontoDate(new Date("2026-12-08T04:59:00Z")), "2026-12-07");
});

test("window runs from two days back to seven days ahead", () => {
  assert.equal(windowStart("2026-09-30"), "2026-09-28");
  assert.equal(windowStart("2026-10-01"), "2026-09-29");
  assert.ok(inWindow("2026-09-28", "2026-09-30") && inWindow("2026-10-07T21:00-04:00", "2026-09-30"));
  assert.ok(!inWindow("2026-09-27", "2026-09-30") && !inWindow("2026-10-08", "2026-09-30"));
});

test("labels never shift date-only values", () => {
  assert.equal(dayLabel("2026-09-28"), "Mon, Sep 28");
  assert.equal(dayLabel("2026-10-04"), "Sun, Oct 4");
  assert.equal(timeLabel("2026-09-28T21:00-04:00"), "9:00 PM");
  assert.equal(timeLabel("2026-09-28T00:30-04:00"), "12:30 AM");
  assert.equal(timeLabel("2026-09-28T12:05-04:00"), "12:05 PM");
  assert.equal(timeLabel("2026-09-30"), "");
});

test("scheduleDays groups by local day and drops inactive shows", () => {
  const rows = [
    { tmdb_id: 3, airstamp: "2026-09-30", show_name: "Streamer" },
    { tmdb_id: 1, airstamp: "2026-09-28T21:00-04:00", show_name: "Late" },
    { tmdb_id: 1, airstamp: "2026-09-28T20:00-04:00", show_name: "Early" },
    { tmdb_id: 2, airstamp: "2026-09-29T20:00-04:00", show_name: "Untracked" },
  ];
  const trackedRows = [{ tmdb_id: 1, active: true }, { tmdb_id: 3, active: true }, { tmdb_id: 2, active: false }];
  const days = scheduleDays(rows, trackedRows, "2026-09-30");
  assert.equal(days.length, 10);
  assert.equal(days[0].day, "2026-09-28");
  assert.equal(days[9].day, "2026-10-07");
  assert.deepEqual(days.slice(0, 4).map((d) => d.relative), ["", "Yesterday", "Today", "Tomorrow"]);
  assert.deepEqual(days[0].items.map((i) => [i.show_name, i.time]), [["Early", "8:00 PM"], ["Late", "9:00 PM"]]);
  assert.deepEqual(days[1].items, []);
  assert.deepEqual(days[2].items.map((i) => [i.show_name, i.time]), [["Streamer", ""]]);
  assert.ok(days[2].isToday && !days[0].isToday);
});

const meta = (values) => Object.entries(values).map(([key, value]) => ({ key, value }));
const NOW = Date.parse("2026-09-28T09:00:00-04:00");

test("scheduleHeader states", () => {
  const ok = { last_run_at: "2026-09-28T06:02:00-04:00", last_run_ok: true, schedule_from: "2026-09-26", failed_shows: "", failed_steps: "" };
  assert.deepEqual(scheduleHeader(meta(ok), "2026-09-28", NOW), { kind: "ok", text: "Updated 6:02 AM" });
  assert.deepEqual(scheduleHeader([], "2026-09-28", NOW), { kind: "stale", text: "Not refreshed yet" });
  assert.deepEqual(scheduleHeader(meta({ ...ok, last_run_ok: false, failed_shows: "Slow Horses" }), "2026-09-28", NOW), {
    kind: "failed",
    text: "Couldn't refresh: Slow Horses — showing last known times",
  });
  const old = { ...ok, last_run_at: "2026-09-26T20:00:00-04:00" };
  assert.equal(scheduleHeader(meta(old), "2026-09-28", NOW).text, "Couldn't refresh — showing last known times");
});
