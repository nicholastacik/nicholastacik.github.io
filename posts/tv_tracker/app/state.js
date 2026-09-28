import { HEADERS } from "./headers.js";

export const TZ = "America/Toronto";

export function truthy(value) {
  return String(value).trim().toUpperCase() === "TRUE";
}

export function rowsFromValues(tab, values = []) {
  const header = HEADERS[tab];
  const rows = [];
  (values ?? []).slice(1).forEach((cells, index) => {
    if (!cells.some((cell) => cell !== "" && cell !== null && cell !== undefined)) return;
    const row = { _row: index + 2 };
    header.forEach((column, j) => {
      row[column] = cells[j] ?? "";
    });
    rows.push(row);
  });
  return rows;
}

function isActive(row) {
  return row.tmdb_id !== "" && Number.isFinite(Number(row.tmdb_id)) && truthy(row.active);
}

export function activeIds(trackedRows) {
  return new Set(trackedRows.filter(isActive).map((row) => Number(row.tmdb_id)));
}

export function activeShows(trackedRows) {
  const shows = new Map();
  for (const row of trackedRows.filter(isActive)) {
    const id = Number(row.tmdb_id);
    if (!shows.has(id)) {
      shows.set(id, {
        tmdb_id: id,
        name: String(row.name),
        poster_url: row.poster_url,
        first_air_year: row.first_air_year,
        imdb_id: String(row.imdb_id ?? ""),
      });
    }
  }
  return [...shows.values()].sort((a, b) => a.name.localeCompare(b.name));
}

export function showLink(show) {
  return /^tt\d+$/.test(String(show.imdb_id ?? ""))
    ? `https://www.imdb.com/title/${show.imdb_id}/`
    : `https://www.themoviedb.org/tv/${show.tmdb_id}`;
}

export function visibleCards(cards, trackedRows) {
  const active = activeIds(trackedRows);
  return cards
    .filter(
      (card) =>
        card.status === "new" && truthy(card.current) && (card.type === "suggestion" || active.has(Number(card.tmdb_id))),
    )
    .sort(
      (a, b) =>
        Date.parse(b.created_at) - Date.parse(a.created_at) || String(b.date).localeCompare(String(a.date)),
    );
}

export function safeUrl(url) {
  return /^https?:\/\/[^/]/i.test(String(url ?? "")) ? String(url) : null;
}

export function domain(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return "";
  }
}

const WEEKDAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function torontoDate(date = new Date()) {
  return new Intl.DateTimeFormat("en-CA", { timeZone: TZ, year: "numeric", month: "2-digit", day: "2-digit" }).format(date);
}

function utc(day) {
  return new Date(`${day}T00:00:00Z`);
}

export function addDays(day, n) {
  const date = utc(day);
  date.setUTCDate(date.getUTCDate() + n);
  return date.toISOString().slice(0, 10);
}

const DAYS_BACK = 2;
const DAYS_AHEAD = 7;
const RELATIVE = { [-1]: "Yesterday", 0: "Today", 1: "Tomorrow" };

export function windowStart(today) {
  return addDays(today, -DAYS_BACK);
}

export function inWindow(stamp, today) {
  const day = String(stamp).slice(0, 10);
  return day >= windowStart(today) && day <= addDays(today, DAYS_AHEAD);
}

export function dayLabel(day) {
  const date = utc(day);
  return `${WEEKDAYS[date.getUTCDay()]}, ${MONTHS[date.getUTCMonth()]} ${date.getUTCDate()}`;
}

export function timeLabel(airstamp) {
  const match = /T(\d{2}):(\d{2})/.exec(String(airstamp));
  if (!match) return "";
  const hour = Number(match[1]);
  return `${hour % 12 || 12}:${match[2]} ${hour >= 12 ? "PM" : "AM"}`;
}

export function scheduleDays(rows, trackedRows, today) {
  const active = activeIds(trackedRows);
  const start = windowStart(today);
  return Array.from({ length: DAYS_BACK + DAYS_AHEAD + 1 }, (_, i) => addDays(start, i)).map((day, i) => ({
    day,
    label: dayLabel(day),
    isToday: day === today,
    relative: RELATIVE[i - DAYS_BACK] ?? "",
    items: rows
      .filter((row) => String(row.airstamp).slice(0, 10) === day && active.has(Number(row.tmdb_id)))
      .sort((a, b) => String(a.airstamp).localeCompare(String(b.airstamp)))
      .map((row) => ({ ...row, time: timeLabel(row.airstamp) })),
  }));
}

function clock(ms) {
  return new Intl.DateTimeFormat("en-US", { timeZone: TZ, hour: "numeric", minute: "2-digit" })
    .format(new Date(ms))
    .replace(/ /g, " ");
}

export function scheduleHeader(metaRows, today, nowMs) {
  const meta = Object.fromEntries(metaRows.map((row) => [row.key, row.value]));
  if (!meta.last_run_at) return { kind: "stale", text: "Not refreshed yet" };
  const last = Date.parse(meta.last_run_at);
  if (!truthy(meta.last_run_ok) || !(nowMs - last <= 36 * 3600 * 1000)) {
    const names = meta.failed_shows ? `: ${meta.failed_shows}` : "";
    return { kind: "failed", text: `Couldn't refresh${names} — showing last known times` };
  }
  return { kind: "ok", text: `Updated ${clock(last)}` };
}

export function toCell(value) {
  if (typeof value === "boolean") return { userEnteredValue: { boolValue: value } };
  if (typeof value === "number") return { userEnteredValue: { numberValue: value } };
  return { userEnteredValue: { stringValue: String(value ?? "") } };
}

function updateRow(sheetIds, tab, row, firstColumn, values) {
  const column = HEADERS[tab].indexOf(firstColumn);
  return {
    updateCells: {
      range: {
        sheetId: sheetIds[tab],
        startRowIndex: row - 1,
        endRowIndex: row,
        startColumnIndex: column,
        endColumnIndex: column + values.length,
      },
      rows: [{ values: values.map(toCell) }],
      fields: "userEnteredValue",
    },
  };
}

export function planCardStatus(card, status, nowIso, sheetIds) {
  return [updateRow(sheetIds, "Cards", card._row, "status", [status, nowIso])];
}

export function planTrack({ tracked, show, source, card, today, nowIso, sheetIds }) {
  const requests = card ? planCardStatus(card, "tracked", nowIso, sheetIds) : [];
  const rows = tracked.filter((row) => Number(row.tmdb_id) === show.tmdb_id);
  if (rows.length === 0) {
    const row = {
      tmdb_id: show.tmdb_id,
      tvmaze_id: "",
      name: show.name,
      first_air_year: show.first_air_year ?? "",
      poster_url: show.poster_url ?? "",
      added_at: today,
      source,
      active: true,
      updated_at: nowIso,
    };
    requests.push({
      appendCells: {
        sheetId: sheetIds.Tracked,
        rows: [{ values: HEADERS.Tracked.map((column) => toCell(row[column])) }],
        fields: "userEnteredValue",
      },
    });
    return requests;
  }
  const wasActive = rows.some((row) => truthy(row.active));
  for (const row of rows) {
    if (!wasActive) requests.push(updateRow(sheetIds, "Tracked", row._row, "added_at", [today]));
    requests.push(updateRow(sheetIds, "Tracked", row._row, "active", [true, nowIso]));
  }
  return requests;
}

export function planUntrack({ tracked, tmdbId, nowIso, sheetIds }) {
  return tracked
    .filter((row) => Number(row.tmdb_id) === tmdbId)
    .map((row) => updateRow(sheetIds, "Tracked", row._row, "active", [false, nowIso]));
}
