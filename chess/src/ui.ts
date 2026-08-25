import type { Study } from "./study";

export function renderLanding(
  root: HTMLElement,
  studies: Study[],
  onOpen: (id: string) => void,
): void {
  root.innerHTML = "";

  const header = document.createElement("header");
  header.className = "landing-header";
  const h1 = document.createElement("h1");
  h1.textContent = "Chess Openings Explorer";
  const p = document.createElement("p");
  p.textContent = "Walk through openings move by move. Pick one to begin.";
  header.append(h1, p);

  const search = document.createElement("input");
  search.className = "study-search";
  search.type = "search";
  search.placeholder = "Search by name or ECO code…";

  const list = document.createElement("div");
  list.className = "study-list";

  for (const study of studies) {
    const card = document.createElement("button");
    card.className = "study-card";
    card.dataset.id = study.id;

    const name = document.createElement("span");
    name.className = "study-card-name";
    name.textContent = study.name;

    const meta = document.createElement("span");
    meta.className = "study-card-meta";
    const bits = [study.eco, study.side].filter(Boolean);
    meta.textContent = bits.join(" · ");

    card.append(name, meta);
    card.addEventListener("click", () => onOpen(study.id));
    list.appendChild(card);
  }

  search.addEventListener("input", () => {
    const q = search.value.trim().toLowerCase();
    for (const study of studies) {
      const card = list.querySelector<HTMLElement>(`.study-card[data-id="${study.id}"]`);
      if (!card) continue;
      const hay = `${study.name} ${study.eco ?? ""}`.toLowerCase();
      card.style.display = hay.includes(q) ? "" : "none";
    }
  });

  root.append(header, search, list);
}
