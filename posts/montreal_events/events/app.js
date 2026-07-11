// Montreal events page. Reads ./events.json (committed by the update skill).
const CATEGORY_LABELS = {
  festival: "Festivals", music: "Music", museum: "Museums", sports: "Sports",
  "board-games": "Board games", trivia: "Trivia", "escape-room": "Escape rooms",
  hike: "Hikes", market: "Markets", other: "Other",
};
const STATUS_LABELS = {
  "date-specific": "Dated", recurring: "Recurring",
  evergreen: "Evergreen", lead: "Unverified — check first",
};
const STATUS_ORDER = { "date-specific": 0, recurring: 1, evergreen: 2, lead: 3 };
const CLOSING_SOON_DAYS = 14;
const STALE_DAYS = 10;

const state = { view: "all", categories: new Set() };
let events = [];

const $ = (sel) => document.querySelector(sel);
const parseDate = (s) => (s ? new Date(s + "T00:00:00") : null);
const today = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d; };
const addDays = (d, n) => { const c = new Date(d); c.setDate(c.getDate() + n); return c; };
const dayMs = 86400000;

function weekendWindow() {
  // Fri–Sun window containing today, or the upcoming one (Mon–Thu).
  const t = today();
  const dow = t.getDay(); // Sun=0 ... Sat=6
  const fri = addDays(t, dow === 0 ? -2 : 5 - dow);
  return [fri, addDays(fri, 2)];
}

function windowFor(view) {
  if (view === "weekend") return weekendWindow();
  if (view === "month") return [today(), addDays(today(), 30)];
  return null;
}

function inView(ev, win) {
  if (!win) return true;
  if (ev.status === "recurring") return true;
  const start = parseDate(ev.start_date), end = parseDate(ev.end_date);
  if (!start && !end) return false; // evergreen/leads only in "All"
  return (start ?? end) <= win[1] && (end ?? start) >= win[0];
}

function fmtRange(ev) {
  const opts = { month: "short", day: "numeric" };
  const start = parseDate(ev.start_date), end = parseDate(ev.end_date);
  if (start && end && ev.start_date !== ev.end_date)
    return `${start.toLocaleDateString("en-CA", opts)} – ${end.toLocaleDateString("en-CA", opts)}`;
  const one = end ?? start;
  return one ? `until ${one.toLocaleDateString("en-CA", opts)}` : "";
}

function badges(ev) {
  const out = [];
  const end = parseDate(ev.end_date);
  if (end) {
    const days = Math.round((end - today()) / dayMs);
    if (days >= 0 && days <= CLOSING_SOON_DAYS)
      out.push(`<span class="badge badge-closing">closing soon</span>`);
  }
  const cls = ev.status === "lead" ? "badge badge-lead" : "badge badge-status";
  out.push(`<span class="${cls}">${STATUS_LABELS[ev.status]}</span>`);
  return out.join("");
}

function card(ev) {
  const meta = [CATEGORY_LABELS[ev.category], fmtRange(ev), ev.location]
    .filter(Boolean).join(" · ");
  const links = [];
  if (ev.url) {
    links.push(`<a href="${ev.url}" rel="noopener">Website</a>`);
    if (ev.url_ok === false)
      links.push(`<span class="dead-link">⚠ link may be dead</span>`);
  }
  if (ev.location) {
    const q = encodeURIComponent(`${ev.location}, Montréal, QC`);
    links.push(`<a href="https://www.google.com/maps/search/?api=1&query=${q}" rel="noopener">Map</a>`);
  }
  return `<article class="card">
    <h2>${ev.title}${badges(ev)}</h2>
    <p class="meta">${meta}</p>
    <p>${ev.description}${ev.notes ? ` <em>${ev.notes}</em>` : ""}</p>
    ${links.length ? `<div class="links">${links.join(" ")}</div>` : ""}
  </article>`;
}

function render() {
  const win = windowFor(state.view);
  const visible = events
    .filter((ev) => inView(ev, win))
    .filter((ev) => !state.categories.size || state.categories.has(ev.category))
    .sort((a, b) =>
      STATUS_ORDER[a.status] - STATUS_ORDER[b.status] ||
      (a.end_date ?? "9999").localeCompare(b.end_date ?? "9999") ||
      a.title.localeCompare(b.title));
  $("#list").innerHTML = visible.length
    ? visible.map(card).join("")
    : `<p class="meta">Nothing matches — try widening the filters.</p>`;
}

function renderChips() {
  const present = [...new Set(events.map((e) => e.category))]
    .sort((a, b) => CATEGORY_LABELS[a].localeCompare(CATEGORY_LABELS[b]));
  $("#chips").innerHTML = present.map((c) =>
    `<button class="chip" data-category="${c}">${CATEGORY_LABELS[c]}</button>`).join("");
  $("#chips").addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (!chip) return;
    const c = chip.dataset.category;
    state.categories.has(c) ? state.categories.delete(c) : state.categories.add(c);
    chip.classList.toggle("active");
    render();
  });
}

function renderFreshness(lastUpdated) {
  const el = $("#freshness");
  el.hidden = false;
  const days = Math.round((today() - parseDate(lastUpdated)) / dayMs);
  el.textContent = `Last updated ${lastUpdated}`;
  if (days > STALE_DAYS) {
    el.classList.add("stale");
    el.textContent += ` — this data is ${days} days old.`;
  }
}

$("#views").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-view]");
  if (!btn) return;
  state.view = btn.dataset.view;
  document.querySelectorAll("#views button").forEach((b) =>
    b.classList.toggle("active", b === btn));
  render();
});

fetch("./events.json")
  .then((r) => { if (!r.ok) throw new Error(r.status); return r.json(); })
  .then((data) => {
    events = data.events;
    renderFreshness(data.last_updated);
    renderChips();
    render();
  })
  .catch(() => {
    $("#list").innerHTML = `<p class="error">Couldn't load events data. Try refreshing.</p>`;
  });
