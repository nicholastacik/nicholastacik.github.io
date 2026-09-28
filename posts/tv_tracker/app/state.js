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
      shows.set(id, { tmdb_id: id, name: String(row.name), poster_url: row.poster_url, first_air_year: row.first_air_year });
    }
  }
  return [...shows.values()].sort((a, b) => a.name.localeCompare(b.name));
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
