import { CONFIG } from "./config.js";
import { Auth } from "./auth.js";
import { AuthError, ForbiddenError, SheetsClient } from "./sheets.js";
import { StaleError, enqueue, markCard, resume, trackShow, untrackShow } from "./actions.js";
import { resultLabel, searchShows } from "./tmdb.js";
import { activeShows, dayLabel, domain, safeUrl, scheduleDays, scheduleHeader, showLink, torontoDate, visibleCards } from "./state.js";

const SCOPE = "https://www.googleapis.com/auth/spreadsheets";
const TYPE_LABEL = { episode: "New episode", season: "Season date", news: "News", suggestion: "You might like" };

function storage() {
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

const auth = new Auth({ clientId: CONFIG.CLIENT_ID, scope: SCOPE, storage: storage() });
const sheets = new SheetsClient({ sheetId: CONFIG.SHEET_ID, getToken: () => auth.token });
const ctx = {
  sheets,
  nowIso: () => new Date().toISOString(),
  today: () => torontoDate(),
  pending: [],
  onAuthNeeded: () => {
    auth.expire();
    showGate("Your Google session expired. Reconnect to save.", "Reconnect Google");
  },
};
let data = null;
let connectPrompt = "";
let results = [];

const $ = (id) => document.getElementById(id);

function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (key === "onclick") node.addEventListener("click", value);
    else if (key === "class") node.className = value;
    else node.setAttribute(key, value);
  }
  for (const child of children.flat()) {
    if (child !== null && child !== undefined && child !== false) node.append(child);
  }
  return node;
}

function poster(url) {
  const src = safeUrl(url);
  return src ? el("img", { src, alt: "", loading: "lazy" }) : el("div", { class: "noimg" });
}

function link(url, text) {
  const href = safeUrl(url);
  return href ? el("a", { href, target: "_blank", rel: "noopener noreferrer" }, text) : null;
}

function toast(message) {
  const node = $("toast");
  node.textContent = message;
  node.hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => {
    node.hidden = true;
  }, 4000);
}

function showGate(text, button, prompt = "") {
  connectPrompt = prompt;
  $("gate-text").textContent = text;
  $("connect").hidden = !button;
  if (button) $("connect").textContent = button;
  $("gate").hidden = false;
}

function showPrivate() {
  auth.expire();
  showGate("This app is private.", "Use another account", "select_account");
}

async function load() {
  try {
    data = await sheets.readAll();
    $("gate").hidden = true;
    render();
  } catch (error) {
    if (error instanceof ForbiddenError) showPrivate();
    else if (error instanceof AuthError) ctx.onAuthNeeded();
    else toast("Couldn't load the Sheet");
  }
}

async function failed(error) {
  if (error instanceof StaleError) {
    toast("The Sheet changed, so it was reloaded");
    await load();
  } else if (error instanceof ForbiddenError) {
    showPrivate();
  } else {
    toast("Couldn't save");
  }
}

async function write(action, undo) {
  try {
    if ((await enqueue(ctx, action)) === "done") await load();
  } catch (error) {
    undo();
    render();
    await failed(error);
  }
}

function setStatus(card, status) {
  card.status = status;
  render();
  write(
    () => markCard(ctx, card, status),
    () => {
      card.status = "new";
    },
  );
}

function pendingSuggestion(tmdbId) {
  return data.Cards.find((c) => c.type === "suggestion" && c.status === "new" && Number(c.tmdb_id) === tmdbId) ?? null;
}

function track(show, source, card = null) {
  const row = { tmdb_id: show.tmdb_id, name: show.name, poster_url: show.poster_url, active: true, _row: 0 };
  if (card) card.status = "tracked";
  data.Tracked.push(row);
  render();
  toast(`Tracking ${show.name}. Episodes appear after the next daily update.`);
  write(
    () => trackShow(ctx, show, source, card),
    () => {
      if (card) card.status = "new";
      data.Tracked = data.Tracked.filter((r) => r !== row);
    },
  );
}

function untrack(tmdbId) {
  const changed = data.Tracked.filter((r) => Number(r.tmdb_id) === tmdbId);
  const before = changed.map((r) => r.active);
  for (const r of changed) r.active = false;
  render();
  write(
    () => untrackShow(ctx, tmdbId),
    () => changed.forEach((r, i) => {
      r.active = before[i];
    }),
  );
}

function formatDay(value) {
  return /^\d{4}-\d{2}-\d{2}/.test(String(value)) ? dayLabel(String(value).slice(0, 10)) : String(value);
}

function cardView(card) {
  const suggestion = card.type === "suggestion";
  const linkText = card.type === "news" ? domain(card.link) : String(card.link).includes("imdb.com") ? "IMDb" : "TMDB";
  const buttons = suggestion
    ? [
        el("button", { class: "primary", onclick: () => track({ tmdb_id: Number(card.tmdb_id), name: String(card.show_name), first_air_year: Number(card.date) || "", poster_url: card.image_url }, "suggestion", card) }, "Track"),
        el("button", { onclick: () => setStatus(card, "ignored") }, "Ignore"),
      ]
    : [el("button", { class: "primary", onclick: () => setStatus(card, "noted") }, "Noted")];
  const when = suggestion ? `First aired ${card.date}` : formatDay(card.date);
  const source = link(card.link, linkText);
  return el(
    "li",
    { class: `card ${card.type}` },
    poster(card.image_url),
    el(
      "div",
      { class: "body" },
      el("p", { class: "kind" }, TYPE_LABEL[card.type] ?? String(card.type)),
      el("h3", {}, String(card.show_name)),
      el("p", { class: "sub" }, String(suggestion ? card.body : card.headline)),
      card.type === "news" && card.body ? el("p", { class: "detail" }, String(card.body)) : null,
      el("p", { class: "meta" }, when, source ? " · " : "", source),
      el("div", { class: "actions" }, buttons),
    ),
  );
}

function renderFeed() {
  const cards = visibleCards(data.Cards, data.Tracked);
  $("feed-empty").hidden = cards.length > 0;
  $("feed").replaceChildren(...cards.map(cardView));
}

function renderWeek() {
  const today = torontoDate();
  const header = scheduleHeader(data.Meta, today, Date.now());
  const status = $("week-status");
  status.textContent = header.text;
  status.className = `status ${header.kind}`;
  const days = scheduleDays(data.Schedule, data.Tracked, today);
  const container = $("week");
  if (!days.some((day) => day.items.length)) {
    container.replaceChildren(el("p", { class: "empty" }, header.kind === "ok" ? "Nothing airing this week." : "No schedule yet."));
    return;
  }
  container.replaceChildren(
    ...days
      .filter((day) => day.items.length || day.isToday)
      .map((day) =>
        el(
          "section",
          { class: day.isToday ? "day today" : "day" },
          el("h3", {}, day.relative ? `${day.relative} · ${day.label}` : day.label),
          day.items.length
            ? el(
                "ul",
                { class: "airings" },
                day.items.map((item) =>
                  el(
                    "li",
                    {},
                    poster(item.image_url),
                    el(
                      "div",
                      {},
                      el("strong", {}, link(item.link, String(item.show_name)) ?? String(item.show_name)),
                      el("p", {}, String(item.episode_label)),
                      el("p", { class: "meta" }, [item.time, item.network].filter(Boolean).join(" · ")),
                    ),
                  ),
                ),
              )
            : el("p", { class: "meta" }, "Nothing today."),
        ),
      ),
  );
}

function renderResults() {
  const tracking = new Set(activeShows(data.Tracked).map((s) => s.tmdb_id));
  $("results").replaceChildren(
    ...results.map((show) =>
      el(
        "li",
        {},
        poster(show.poster_url),
        el("span", {}, link(showLink(show), resultLabel(show))),
        tracking.has(show.tmdb_id)
          ? el("span", { class: "tag" }, "Tracking")
          : el("button", { class: "primary", onclick: () => track(show, "search", pendingSuggestion(show.tmdb_id)) }, "Track"),
      ),
    ),
  );
}

function renderShows() {
  $("tracked").replaceChildren(
    ...activeShows(data.Tracked).map((show) =>
      el("li", {}, poster(show.poster_url), el("span", {}, link(showLink(show), show.name)), el("button", { onclick: () => untrack(show.tmdb_id) }, "Untrack")),
    ),
  );
  renderResults();
}

function render() {
  if (!data) return;
  renderFeed();
  renderWeek();
  renderShows();
}

let searchTimer;
$("search").addEventListener("input", (event) => {
  clearTimeout(searchTimer);
  const query = event.target.value.trim();
  searchTimer = setTimeout(async () => {
    if (!query) {
      results = [];
    } else {
      try {
        results = await searchShows(query, CONFIG.TMDB_API_KEY);
      } catch {
        toast("Search failed");
        return;
      }
    }
    if (data) renderResults();
  }, 300);
});

for (const button of document.querySelectorAll(".tabs button")) {
  button.addEventListener("click", () => {
    for (const other of document.querySelectorAll(".tabs button")) other.classList.toggle("active", other === button);
    for (const view of document.querySelectorAll(".view")) view.hidden = view.id !== `view-${button.dataset.view}`;
  });
}

$("connect").addEventListener("click", async () => {
  try {
    await auth.connect(connectPrompt);
  } catch {
    toast("Google sign-in didn't finish");
    return;
  }
  $("gate").hidden = true;
  if (ctx.pending.length) {
    try {
      await resume(ctx);
    } catch (error) {
      await failed(error);
    }
  }
  await load();
});

$("refresh").addEventListener("click", () => {
  if (auth.valid()) load();
  else showGate("Connect your Google account to load your shows.", "Connect Google");
});

if (auth.valid()) load();
else showGate("Connect your Google account to load your shows.", "Connect Google");
