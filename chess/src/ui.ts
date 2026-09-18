import { Chess } from "chess.js";
import type { Study } from "./study";
import {
  normalize,
  positionAt,
  stepForward,
  stepBack,
  siblings,
  switchSibling,
  enumerateLines,
  type TreeNode,
  type Path,
  type LineChoice,
} from "./tree";
import { createDrill, type Drill } from "./practice";
import { analyzeMismatch, type EvalProvider, type MismatchVerdict } from "./evalProvider";
import { legalDests, type MovableBoardHandle } from "./board";

export interface BoardHandle {
  setPosition(
    fen: string,
    lastMove: [string, string] | undefined,
    orientation: "white" | "black",
  ): void;
  destroy(): void;
}

export interface StudyViewDeps {
  makeBoard: (el: HTMLElement, orientation: "white" | "black") => BoardHandle;
  // Practice-mode deps are optional: renderStudyView renders a Practice entry
  // button only when both are supplied, so callers/tests that only exercise
  // the viewer (passing just `makeBoard`) keep working unchanged.
  makeMovableBoard?: PracticeDeps["makeMovableBoard"];
  evalProvider?: EvalProvider;
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

  // Practice mode is opt-in: only offered when the caller supplied both
  // practice deps (keeps renderStudyView backward-compatible with callers/
  // tests that only pass `makeBoard`).
  if (deps.makeMovableBoard && deps.evalProvider) {
    const practiceBtn = document.createElement("button");
    practiceBtn.className = "btn-practice";
    practiceBtn.textContent = "Practice";
    practiceBtn.addEventListener("click", () => {
      document.removeEventListener("keydown", onKey);
      board.destroy();
      renderPractice(root, study, {
        makeMovableBoard: deps.makeMovableBoard!,
        evalProvider: deps.evalProvider!,
        onExit: () => renderStudyView(root, study, deps),
      });
    });
    controls.append(practiceBtn);
  }

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

    // Render `node`'s move into `container`, then its continuation. A node's
    // children are [mainline, ...alternatives]; each alternative becomes its
    // own indented `.variation` block (rendered before the mainline continues,
    // so it sits at the branch point), while the mainline flows on in the same
    // container.
    function renderNode(node: TreeNode, nodePath: Path, ply: number, container: HTMLElement): void {
      const span = document.createElement("span");
      span.className = "move";
      span.textContent = moveNumberLabel(ply, node.san as string);
      span.addEventListener("click", () => {
        path = nodePath;
        render();
      });
      nodeSpans.set(node, span);
      container.appendChild(span);
      container.appendChild(document.createTextNode(" "));

      const [mainline, ...alts] = node.children;
      for (const alt of alts) {
        const variation = document.createElement("div");
        variation.className = "variation";
        container.appendChild(variation);
        renderNode(alt, [...nodePath, alt], ply + 1, variation);
      }
      if (mainline) renderNode(mainline, [...nodePath, mainline], ply + 1, container);
    }

    // Root's children are the first move plus any alternatives to it.
    const [firstMain, ...firstAlts] = tree.children;
    for (const alt of firstAlts) {
      const variation = document.createElement("div");
      variation.className = "variation";
      treeEl.appendChild(variation);
      renderNode(alt, [tree, alt], 1, variation);
    }
    if (firstMain) renderNode(firstMain, [tree, firstMain], 1, treeEl);
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

// ---------------------------------------------------------------------------
// Practice mode
// ---------------------------------------------------------------------------

export interface PracticeDeps {
  makeMovableBoard: (
    el: HTMLElement,
    opts: { orientation: "white" | "black"; onMove: (from: string, to: string, promotion?: string) => void },
  ) => MovableBoardHandle;
  evalProvider: EvalProvider;
  // Optional: renderStudyView passes these so the drill can persist completed
  // lines and hand control back to the viewer on Exit. Standalone callers
  // (and the tests) may omit both.
  storage?: Storage;
  onExit?: () => void;
}

function trainerSide(side: Study["side"]): "white" | "black" {
  return side === "black" ? "black" : "white"; // "both" → white in v1
}

function verdictText(v: MismatchVerdict, bookSan: string): string {
  switch (v.kind) {
    case "playable":
      return `Not your line — book move is ${bookSan}. Your move is a playable alternative.`;
    case "loses":
      return `Not your line — book move is ${bookSan}. Your move loses ~${(v.lossCp / 100).toFixed(1)}; the engine prefers ${v.bestMoveUci}.`;
    case "mated":
      return `Not your line — book move is ${bookSan}. Your move gets mated in ${v.mateIn}.`;
    case "missed-mate":
      return `Not your line — book move is ${bookSan}. A forced mate in ${v.mateIn} was available (${v.bestMoveUci}).`;
  }
}

function toSan(fen: string, from: string, to: string): string {
  const chess = new Chess(fen);
  const move = chess.move({ from, to, promotion: "q" });
  return move.san;
}

function fenAfterMove(fen: string, from: string, to: string): string {
  const chess = new Chess(fen);
  chess.move({ from, to, promotion: "q" });
  return chess.fen();
}

function div(className: string): HTMLElement {
  const el = document.createElement("div");
  el.className = className;
  return el;
}

function pickerHeader(study: Study): HTMLElement {
  const header = div("practice-picker-header");
  const h2 = document.createElement("h2");
  h2.textContent = `Practice: ${study.name}`;
  header.appendChild(h2);
  return header;
}

function exitButton(onClick: () => void): HTMLButtonElement {
  const btn = document.createElement("button");
  btn.className = "btn-exit";
  btn.textContent = "Exit";
  btn.addEventListener("click", onClick);
  return btn;
}

function practiceControls(onReveal: () => void, onRestart: () => void, onExit: () => void): HTMLElement {
  const controls = div("practice-controls");
  const reveal = document.createElement("button");
  reveal.className = "btn-reveal";
  reveal.textContent = "Reveal";
  reveal.addEventListener("click", onReveal);
  const restart = document.createElement("button");
  restart.className = "btn-restart";
  restart.textContent = "Restart";
  restart.addEventListener("click", onRestart);
  controls.append(reveal, restart, exitButton(onExit));
  return controls;
}

function practiceStorageKey(studyId: string): string {
  return `chess:practice:${studyId}`;
}

// Tolerant of absent/corrupt storage: any failure yields an empty set/no-op.
function loadCompletedLines(storage: Storage | undefined, studyId: string): Set<string> {
  try {
    const raw = storage?.getItem(practiceStorageKey(studyId));
    if (!raw) return new Set();
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return new Set();
    return new Set(parsed.filter((x): x is string => typeof x === "string"));
  } catch {
    return new Set();
  }
}

function saveCompletedLines(storage: Storage | undefined, studyId: string, ids: Set<string>): void {
  try {
    storage?.setItem(practiceStorageKey(studyId), JSON.stringify([...ids]));
  } catch {
    /* ignore quota/absent storage */
  }
}

export function renderPractice(root: HTMLElement, study: Study, deps: PracticeDeps): void {
  root.innerHTML = "";
  const side = trainerSide(study.side);
  const lines = enumerateLines(normalize(study));
  const storage = deps.storage ?? (typeof localStorage !== "undefined" ? localStorage : undefined);
  const completed = loadCompletedLines(storage, study.id);

  // --- line picker ---
  const picker = document.createElement("div");
  picker.className = "line-picker";
  for (const line of lines) {
    const btn = document.createElement("button");
    btn.className = "line-choice" + (completed.has(line.id) ? " completed" : "");
    btn.dataset.id = line.id;
    btn.textContent = line.label;
    btn.addEventListener("click", () => startDrill(line));
    picker.appendChild(btn);
  }
  root.append(pickerHeader(study), picker, exitButton(() => leave()));

  let board: MovableBoardHandle | null = null;
  let drill: Drill | null = null;
  let currentLineId: string | null = null;
  let sessionId = 0; // bumped on every start/restart/exit; guards stale evals

  function startDrill(line: LineChoice): void {
    sessionId += 1;
    const mySession = sessionId;
    currentLineId = line.id;
    drill = createDrill(line.path, side);
    root.innerHTML = "";
    const boardEl = document.createElement("div");
    boardEl.className = "board";
    const status = div("practice-status");
    const feedback = div("practice-feedback");
    const controls = practiceControls(
      () => {
        const san = drill!.reveal();
        feedback.textContent = `Revealed: ${san}.`;
        syncBoard();
        autoPlayOpponent(status);
      },
      () => startDrill(line), // restart
      () => leave(), // exit
    );
    const practice = document.createElement("div");
    practice.className = "practice";
    practice.append(boardEl, status, feedback, controls);
    root.append(practice);

    board = deps.makeMovableBoard(boardEl, {
      orientation: side,
      onMove: (from, to) => onUserMove(mySession, from, to, status, feedback),
    });
    syncBoard();
    autoPlayOpponent(status);
  }

  function syncBoard(): void {
    if (!board || !drill) return;
    const st = drill.state();
    board.setPosition(st.fen, undefined, side);
    if (st.toMove === "user") board.setMovable(legalDests(st.fen), side);
    else board.setMovable(new Map(), side); // freeze while opponent/done
  }

  function autoPlayOpponent(status: HTMLElement): void {
    if (!drill) return;
    while (drill.state().toMove === "opponent") {
      drill.playOpponent();
    }
    syncBoard();
    if (drill.state().toMove === "done") renderSummary(status);
  }

  function renderSummary(status: HTMLElement): void {
    if (!drill) return;
    const s = drill.summary();
    status.textContent = `Done! ${s.cleanFirstTry}/${s.plies} clean first try, ${s.mistakes} mistakes, ${s.revealed} revealed.`;
    if (currentLineId) {
      completed.add(currentLineId);
      saveCompletedLines(storage, study.id, completed);
    }
  }

  function onUserMove(mySession: number, from: string, to: string, status: HTMLElement, feedback: HTMLElement): void {
    if (!drill || mySession !== sessionId) return;
    const chessSan = toSan(drill.state().fen, from, to); // via chess.js
    const grade = drill.submit(chessSan);
    if (grade.kind === "correct") {
      feedback.textContent = "";
      autoPlayOpponent(status);
      return;
    }
    // mismatch: show book immediately (strict), then engine analysis (async).
    feedback.textContent = `Not your line — book move is ${grade.expected}.`;
    const fenBefore = drill.state().fen; // decision position (drill did not advance)
    const attempt = drill.state().mistakes;
    void runAnalysis(mySession, attempt, fenBefore, from, to, grade.expected, feedback);
    syncBoard(); // re-arm the board for a retry
  }

  async function runAnalysis(
    mySession: number,
    attempt: number,
    fenBefore: string,
    from: string,
    to: string,
    bookSan: string,
    feedback: HTMLElement,
  ): Promise<void> {
    const fenAfter = fenAfterMove(fenBefore, from, to); // via chess.js
    try {
      const [baseline, played] = await Promise.all([
        deps.evalProvider.evaluate(fenBefore),
        deps.evalProvider.evaluate(fenAfter),
      ]);
      if (!isCurrent(mySession, attempt)) return; // stale: retried/advanced/exited
      feedback.textContent = verdictText(analyzeMismatch(baseline, played, side), bookSan);
    } catch {
      if (!isCurrent(mySession, attempt)) return;
      feedback.textContent = `Not your line — book move is ${bookSan}. (Couldn't reach the engine for the analysis.)`;
    }
  }

  function isCurrent(mySession: number, attempt: number): boolean {
    return (
      mySession === sessionId &&
      !!drill &&
      drill.state().mistakes === attempt &&
      drill.state().toMove === "user"
    );
  }

  function leave(): void {
    sessionId += 1; // invalidate any in-flight analysis
    board?.destroy();
    board = null;
    drill = null;
    root.innerHTML = "";
    deps.onExit?.();
  }
}
