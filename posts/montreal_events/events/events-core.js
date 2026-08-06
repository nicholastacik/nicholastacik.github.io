// Pure, DOM-free helpers for the events page. Imported by app.js and the tests.

// Parse a machine line "{{tool evt-003 | hidden=no | calendar=no | recurrence=none | image=auto}}".
// Returns null if the text is not a tool line.
export function parseToolLine(line) {
  const m = /\{\{tool\s+([a-z0-9-]+)\s*\|(.*?)\}\}/.exec(line);
  if (!m) return null;
  const fields = { id: m[1], hidden: false, calendar: false, recurrence: null, image: null };
  for (const part of m[2].split("|")) {
    const idx = part.indexOf("=");
    if (idx === -1) continue;
    const k = part.slice(0, idx).trim();
    const v = part.slice(idx + 1).trim();
    if (k === "hidden") fields.hidden = v === "yes";
    else if (k === "calendar") fields.calendar = v === "yes";
    else if (k === "recurrence") fields.recurrence = v && v !== "none" ? v : null;
    else if (k === "image") fields.image = v && v !== "auto" ? v : null;
  }
  return fields;
}

// Inverse of parseToolLine — canonical formatting.
export function buildToolLine(id, fields) {
  const yn = (b) => (b ? "yes" : "no");
  return `{{tool ${id} | hidden=${yn(fields.hidden)} | calendar=${yn(fields.calendar)}` +
    ` | recurrence=${fields.recurrence ?? "none"} | image=${fields.image ?? "auto"}}}`;
}

// Return a new array with overlay decisions applied by id (does not mutate input).
export function mergeOverlay(events, overlay) {
  return events.map((ev) => {
    const o = overlay[ev.id];
    return o && "hidden" in o ? { ...ev, hidden: o.hidden } : ev;
  });
}
