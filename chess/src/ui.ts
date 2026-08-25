import type { Study } from "./study";
import {
  normalize,
  positionAt,
  stepForward,
  stepBack,
  siblings,
  switchSibling,
  type TreeNode,
  type Path,
} from "./tree";

export interface BoardHandle {
  setPosition(
    fen: string,
    lastMove: [string, string] | undefined,
    orientation: "white" | "black",
  ): void;
}

export interface StudyViewDeps {
  makeBoard: (el: HTMLElement, orientation: "white" | "black") => BoardHandle;
}

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

function defaultOrientation(side: Study["side"]): "white" | "black" {
  return side === "black" ? "black" : "white";
}

function moveNumberLabel(ply: number, san: string): string {
  // ply is 1-based half-move count. White moves on odd plies.
  const moveNo = Math.ceil(ply / 2);
  return ply % 2 === 1 ? `${moveNo}. ${san}` : `${moveNo}… ${san}`;
}

export function renderStudyView(root: HTMLElement, study: Study, deps: StudyViewDeps): void {
  root.innerHTML = "";
  const tree = normalize(study);
  let path: Path = [tree]; // start at the root position
  let orientation = defaultOrientation(study.side);

  // Layout skeleton.
  const container = document.createElement("div");
  container.className = "study-view";

  const back = document.createElement("a");
  back.className = "back-link";
  back.href = "#/";
  back.textContent = "← All openings";

  const title = document.createElement("h1");
  title.className = "study-title";
  title.textContent = study.name;

  const boardEl = document.createElement("div");
  boardEl.className = "board";

  const side = document.createElement("div");
  side.className = "study-side";

  const annotation = document.createElement("div");
  annotation.className = "annotation";

  const treeEl = document.createElement("div");
  treeEl.className = "variation-tree";

  const controls = document.createElement("div");
  controls.className = "controls";
  const prevBtn = document.createElement("button");
  prevBtn.className = "btn-prev";
  prevBtn.textContent = "‹ Prev";
  const nextBtn = document.createElement("button");
  nextBtn.className = "btn-next";
  nextBtn.textContent = "Next ›";
  const flipBtn = document.createElement("button");
  flipBtn.className = "btn-flip";
  flipBtn.textContent = "Flip board";
  controls.append(prevBtn, nextBtn, flipBtn);

  side.append(annotation, controls, treeEl);
  container.append(back, title, boardEl, side);
  root.append(container);

  const board = deps.makeBoard(boardEl, orientation);

  // --- rendering ---
  // Map each rendered .move element to the TreeNode it represents, so render()
  // can toggle .current without tearing down and recreating the tree DOM
  // (which would detach any element a caller already has a reference to).
  const nodeSpans = new Map<TreeNode, HTMLElement>();

  function buildTree(): void {
    treeEl.innerHTML = "";
    nodeSpans.clear();

    function renderNode(node: TreeNode, nodePath: Path, ply: number): void {
      const span = document.createElement("span");
      span.className = "move";
      span.dataset.path = String(ply);
      span.textContent = moveNumberLabel(ply, node.san as string);
      span.addEventListener("click", () => {
        path = nodePath;
        render();
      });
      nodeSpans.set(node, span);
      treeEl.appendChild(span);
      treeEl.appendChild(document.createTextNode(" "));

      const [mainline, ...alts] = node.children;
      // Render alternatives to the *next* move as nested, parenthesized lines.
      for (const alt of alts) {
        const wrap = document.createElement("span");
        wrap.className = "variation";
        wrap.textContent = "(";
        treeEl.appendChild(wrap);
        renderNode(alt, [...nodePath, alt], ply + 1);
        treeEl.appendChild(document.createTextNode(") "));
      }
      if (mainline) renderNode(mainline, [...nodePath, mainline], ply + 1);
    }

    const first = tree.children[0];
    // Render the first move plus any alternatives to it (siblings of children[0]).
    for (let i = 1; i < tree.children.length; i++) {
      const alt = tree.children[i]!;
      const wrap = document.createElement("span");
      wrap.className = "variation";
      wrap.textContent = "(";
      treeEl.appendChild(wrap);
      renderNode(alt, [tree, alt], 1);
      treeEl.appendChild(document.createTextNode(") "));
    }
    if (first) renderNode(first, [tree, first], 1);
  }

  function updateCurrent(): void {
    const currentNode = path[path.length - 1]!;
    for (const [node, span] of nodeSpans) {
      span.classList.toggle("current", node === currentNode);
    }
  }

  function render(): void {
    const current = path[path.length - 1]!;
    const pos = positionAt(path);
    board.setPosition(pos.fen, pos.lastMove, orientation);
    annotation.textContent = current.comment ?? (path.length === 1 ? study.intro : "");
    prevBtn.disabled = path.length <= 1;
    nextBtn.disabled = current.children.length === 0;
    updateCurrent();
  }

  // --- interactions ---
  nextBtn.addEventListener("click", () => {
    const next = stepForward(path);
    if (next) { path = next; render(); }
  });
  prevBtn.addEventListener("click", () => {
    const prev = stepBack(path);
    if (prev) { path = prev; render(); }
  });
  flipBtn.addEventListener("click", () => {
    orientation = orientation === "white" ? "black" : "white";
    render();
  });

  function switchSiblingBy(delta: number): void {
    const sibs = siblings(path);
    if (sibs.length <= 1) return;
    const current = path[path.length - 1]!;
    const idx = sibs.indexOf(current);
    const nextIdx = (idx + delta + sibs.length) % sibs.length;
    path = switchSibling(path, sibs[nextIdx]!);
    render();
  }

  function onKey(e: KeyboardEvent): void {
    if (e.key === "ArrowRight") { nextBtn.click(); }
    else if (e.key === "ArrowLeft") { prevBtn.click(); }
    else if (e.key === "ArrowUp") { e.preventDefault(); switchSiblingBy(-1); }
    else if (e.key === "ArrowDown") { e.preventDefault(); switchSiblingBy(1); }
  }
  document.addEventListener("keydown", onKey);
  // Detach the key handler when the view is torn down (router re-render clears root).
  const observer = new MutationObserver(() => {
    if (!root.contains(container)) {
      document.removeEventListener("keydown", onKey);
      observer.disconnect();
    }
  });
  observer.observe(root, { childList: true });

  buildTree();
  render();
}
