# Engine-Verified Repertoire Trainer — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Practice" mode to the chess openings app: drill one opening line at a time, strict book-move grading, and on a repertoire mismatch the engine auto-shows how much the move loses vs its best line.

**Architecture:** A pure drill state machine (`practice.ts`) drives the loop; a pluggable `EvalProvider` (`evalProvider.ts`, default chess-api.com) supplies engine evals; a pure `analyzeMismatch` turns two evals into a trainee-perspective verdict; `board.ts` gains a movable mode + `destroy()`; `ui.ts` renders Practice mode inside the study view with an explicit teardown contract and a stale-async guard. All new logic is unit-tested with fakes, mirroring the existing `makeBoard`-injection pattern.

**Tech Stack:** TypeScript, Vite, Vitest (+ jsdom), `chess.js`, `@lichess-org/chessground`. Engine via HTTPS (chess-api.com) — CORS-open, called only on mismatches.

**Spec:** `docs/superpowers/specs/2026-09-17-chess-repertoire-trainer-design.md`

## Global Constraints

- **Branch:** work on `chess-trainer` (already stacked on the held `chess-hardening-clean`). Do NOT push/PR/merge unless the user asks. Commit locally.
- **Location:** all app code under `chess/`; run npm commands from `chess/`. Repo root `/Users/nick/Work/nicholastacik.github.io`.
- **Build:** `npm run build` is `tsc --noEmit && vitest run && vite build` (the hardening gate) → outputs to `../posts/chess/app`. `npm test` = `vitest run`.
- **Engine perspective (verified via live probe):** chess-api.com returns `eval` (pawns, number) and `centipawns` (number **or string** — coerce with `Number()`) and `mate` (number|null), all **White-perspective**. `move` is UCI; `san` is provided. Exactly one of cp/mate is meaningful (mate non-null ⇒ use mate).
- **`EngineEval` is always White-perspective.** Trainee-perspective conversion happens only in `analyzeMismatch` (negate iff trainee plays Black).
- **Strict grading:** the exact book SAN is the only pass; any other legal move is a `mismatch`, never called a "mistake"/"punishment" unless the loss supports it. Never claim a played move beats the book move.
- **Testing:** no live network in tests — inject a fake `fetch` / fake `EvalProvider`. jsdom for DOM.
- **Match existing conventions:** vanilla TS, dependency injection for testability (see `renderStudyView`'s `makeBoard`), strict tsconfig, one commit per task step where indicated. Commit message body ends with:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`

---

### Task 1: `EvalProvider` + chess-api.com adapter + cache

**Files:**
- Create: `chess/src/evalProvider.ts`
- Create: `chess/tests/evalProvider.test.ts`

**Interfaces:**
- Consumes: nothing from other tasks.
- Produces:
  - `interface EngineEval { bestMove: string /* UCI */; cp: number | null; mate: number | null; depth: number }` (White-perspective; mate non-null ⇒ cp null).
  - `interface EvalProvider { evaluate(fen: string): Promise<EngineEval> }`
  - `class ChessApiProvider implements EvalProvider` — ctor `({ depth = 12, endpoint = "https://chess-api.com/v1", fetchFn = fetch } = {})`.
  - `class CachingEvalProvider implements EvalProvider` — ctor `(inner: EvalProvider, store?: Storage)`, caches by `fen`+depth-agnostic key (the inner provider owns depth).

- [ ] **Step 1: Write the failing test** `chess/tests/evalProvider.test.ts`

```ts
import { describe, it, expect, vi } from "vitest";
import { ChessApiProvider, CachingEvalProvider, type EvalProvider, type EngineEval } from "../src/evalProvider";

// Recorded chess-api.com response (POST /v1), Black-to-move position — proves
// White-perspective: raw stockfish "score cp -32" comes back as eval +0.32.
const CP_RESPONSE = {
  type: "bestmove", move: "f8c5", san: "Bc5", eval: 0.32, centipawns: 32,
  mate: null, depth: 12,
};
const CP_RESPONSE_STRING_CENTIPAWNS = { ...CP_RESPONSE, centipawns: "32" };
const MATE_RESPONSE = {
  type: "bestmove", move: "d1h5", san: "Qh5#", eval: 99, centipawns: null,
  mate: 1, depth: 12,
};

function fakeFetch(json: unknown, ok = true) {
  return vi.fn(async () => ({ ok, json: async () => json }) as Response);
}

describe("ChessApiProvider", () => {
  it("maps a cp response to a White-perspective EngineEval", async () => {
    const fetchFn = fakeFetch(CP_RESPONSE);
    const p = new ChessApiProvider({ fetchFn, depth: 12 });
    const e = await p.evaluate("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3");
    expect(e).toEqual<EngineEval>({ bestMove: "f8c5", cp: 32, mate: null, depth: 12 });
  });

  it("coerces a string centipawns field to a number", async () => {
    const p = new ChessApiProvider({ fetchFn: fakeFetch(CP_RESPONSE_STRING_CENTIPAWNS) });
    const e = await p.evaluate("8/8/8/8/8/8/8/8 w - - 0 1");
    expect(e.cp).toBe(32);
  });

  it("maps a mate response (cp null, mate set)", async () => {
    const p = new ChessApiProvider({ fetchFn: fakeFetch(MATE_RESPONSE) });
    const e = await p.evaluate("8/8/8/8/8/8/8/8 w - - 0 1");
    expect(e.cp).toBeNull();
    expect(e.mate).toBe(1);
    expect(e.bestMove).toBe("d1h5");
  });

  it("POSTs { fen, depth } as JSON to the endpoint", async () => {
    const fetchFn = fakeFetch(CP_RESPONSE);
    await new ChessApiProvider({ fetchFn, depth: 14 }).evaluate("FEN");
    expect(fetchFn).toHaveBeenCalledOnce();
    const [url, init] = fetchFn.mock.calls[0]!;
    expect(url).toBe("https://chess-api.com/v1");
    expect(init!.method).toBe("POST");
    expect(JSON.parse(init!.body as string)).toEqual({ fen: "FEN", depth: 14 });
  });

  it("throws on a non-ok response or malformed body", async () => {
    await expect(new ChessApiProvider({ fetchFn: fakeFetch({}, false) }).evaluate("F")).rejects.toThrow();
    await expect(new ChessApiProvider({ fetchFn: fakeFetch({ nope: 1 }) }).evaluate("F")).rejects.toThrow();
  });
});

describe("CachingEvalProvider", () => {
  it("calls the inner provider once per distinct fen and caches the result", async () => {
    const inner: EvalProvider = { evaluate: vi.fn(async () => ({ bestMove: "e2e4", cp: 20, mate: null, depth: 12 })) };
    const store = new Map<string, string>();
    const fakeStorage = {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => void store.set(k, v),
    } as unknown as Storage;
    const p = new CachingEvalProvider(inner, fakeStorage);
    const a = await p.evaluate("FEN1");
    const b = await p.evaluate("FEN1");
    expect(a).toEqual(b);
    expect(inner.evaluate).toHaveBeenCalledOnce();
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd chess && npx vitest run tests/evalProvider.test.ts`
Expected: FAIL (module missing).

- [ ] **Step 3: Implement `chess/src/evalProvider.ts`**

```ts
export interface EngineEval {
  bestMove: string; // UCI, e.g. "e2e4"
  cp: number | null; // White-perspective centipawns; null iff mate is set
  mate: number | null; // White-perspective mate-in-N; null iff cp is set
  depth: number;
}

export interface EvalProvider {
  evaluate(fen: string): Promise<EngineEval>;
}

interface ChessApiOpts {
  depth?: number;
  endpoint?: string;
  fetchFn?: typeof fetch;
}

export class ChessApiProvider implements EvalProvider {
  private depth: number;
  private endpoint: string;
  private fetchFn: typeof fetch;

  constructor(opts: ChessApiOpts = {}) {
    this.depth = opts.depth ?? 12;
    this.endpoint = opts.endpoint ?? "https://chess-api.com/v1";
    this.fetchFn = opts.fetchFn ?? fetch;
  }

  async evaluate(fen: string): Promise<EngineEval> {
    const res = await this.fetchFn(this.endpoint, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ fen, depth: this.depth }),
    });
    if (!res.ok) throw new Error(`chess-api ${res.status}`);
    const data = (await res.json()) as Record<string, unknown>;
    const move = data["move"];
    if (typeof move !== "string") throw new Error("chess-api: missing move");
    const mateRaw = data["mate"];
    const mate = typeof mateRaw === "number" ? mateRaw : null;
    // eval (pawns) is always numeric and White-perspective; centipawns may be a
    // string, so derive cp from eval when not mate.
    const cp = mate === null ? Math.round(Number(data["eval"]) * 100) : null;
    const depth = typeof data["depth"] === "number" ? (data["depth"] as number) : this.depth;
    return { bestMove: move, cp, mate, depth };
  }
}

// Wraps any provider with a localStorage-backed cache keyed by FEN. The inner
// provider owns depth, so a fixed-depth provider yields a stable key space.
export class CachingEvalProvider implements EvalProvider {
  constructor(
    private inner: EvalProvider,
    private store: Storage | undefined = typeof localStorage !== "undefined" ? localStorage : undefined,
  ) {}

  async evaluate(fen: string): Promise<EngineEval> {
    const key = `chess:eval:${fen}`;
    try {
      const hit = this.store?.getItem(key);
      if (hit) return JSON.parse(hit) as EngineEval;
    } catch {
      /* ignore corrupt/absent storage */
    }
    const result = await this.inner.evaluate(fen);
    try {
      this.store?.setItem(key, JSON.stringify(result));
    } catch {
      /* ignore quota/absent storage */
    }
    return result;
  }
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd chess && npx vitest run tests/evalProvider.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/nick/Work/nicholastacik.github.io
git add chess/src/evalProvider.ts chess/tests/evalProvider.test.ts
git commit -m "feat(chess): EvalProvider interface + chess-api.com adapter with cache"
```

---

### Task 2: `analyzeMismatch` — trainee-perspective verdict

**Files:**
- Modify: `chess/src/evalProvider.ts` (append)
- Modify: `chess/tests/evalProvider.test.ts` (append a describe block)

**Interfaces:**
- Consumes: `EngineEval` (Task 1).
- Produces:
  - `type MismatchVerdict =`
    `| { kind: "playable"; bestMoveUci: string }`
    `| { kind: "loses"; lossCp: number; bestMoveUci: string }`
    `| { kind: "mated"; mateIn: number }`
    `| { kind: "missed-mate"; mateIn: number; bestMoveUci: string }`
  - `function analyzeMismatch(baseline: EngineEval, played: EngineEval, trainee: "white" | "black"): MismatchVerdict`
    - `baseline` = eval of the decision position (best play). `played` = eval of the position after the trainee's move.
    - Reports loss vs best play only; never claims the played move beats the book move.

- [ ] **Step 1: Append the failing tests** to `chess/tests/evalProvider.test.ts`

```ts
import { analyzeMismatch } from "../src/evalProvider";

describe("analyzeMismatch", () => {
  const ev = (cp: number | null, mate: number | null = null): import("../src/evalProvider").EngineEval =>
    ({ bestMove: "e2e4", cp, mate, depth: 12 });

  it("small loss → playable (White trainee)", () => {
    // baseline +0.30, played +0.10 → loses 20cp
    expect(analyzeMismatch(ev(30), ev(10), "white")).toEqual({ kind: "playable", bestMoveUci: "e2e4" });
  });

  it("large loss → loses N, in the trainee's perspective (White)", () => {
    // baseline +0.30, played -2.30 → loses 260cp
    expect(analyzeMismatch(ev(30), ev(-230), "white")).toEqual({ kind: "loses", lossCp: 260, bestMoveUci: "e2e4" });
  });

  it("converts perspective for a Black trainee", () => {
    // White-persp baseline -0.30 (good for Black = +0.30), played +2.30 (bad for Black = -2.30)
    // trainee(baseline)=+30, trainee(played)=-230 → loses 260
    expect(analyzeMismatch(ev(-30), ev(230), "black")).toEqual({ kind: "loses", lossCp: 260, bestMoveUci: "e2e4" });
  });

  it("a played move at least as good as best play → playable, never 'stronger than book'", () => {
    // played better than baseline (negative loss) → clamped to playable
    expect(analyzeMismatch(ev(20), ev(120), "white")).toEqual({ kind: "playable", bestMoveUci: "e2e4" });
  });

  it("played position is mate against the trainee → mated", () => {
    // White trainee; played is White-persp mate -2 (White gets mated in 2)
    expect(analyzeMismatch(ev(30), ev(null, -2), "white")).toEqual({ kind: "mated", mateIn: 2 });
  });

  it("a forced mate was available but thrown away → missed-mate", () => {
    // White trainee; baseline White-persp mate +3 (White mates), played only +0.10
    expect(analyzeMismatch(ev(null, 3), ev(10), "white")).toEqual({ kind: "missed-mate", mateIn: 3, bestMoveUci: "e2e4" });
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd chess && npx vitest run tests/evalProvider.test.ts`
Expected: FAIL (`analyzeMismatch` missing).

- [ ] **Step 3: Append to `chess/src/evalProvider.ts`**

```ts
export type MismatchVerdict =
  | { kind: "playable"; bestMoveUci: string }
  | { kind: "loses"; lossCp: number; bestMoveUci: string }
  | { kind: "mated"; mateIn: number }
  | { kind: "missed-mate"; mateIn: number; bestMoveUci: string };

const PLAYABLE_CP = 50; // within this loss vs best play, treat as a fine alternative

// Convert a White-perspective score to the trainee's perspective.
function toTrainee<T extends number | null>(v: T, trainee: "white" | "black"): T {
  return (v === null ? null : trainee === "white" ? v : -v) as T;
}

export function analyzeMismatch(
  baseline: EngineEval,
  played: EngineEval,
  trainee: "white" | "black",
): MismatchVerdict {
  const baseMate = toTrainee(baseline.mate, trainee);
  const playedMate = toTrainee(played.mate, trainee);

  // Played position is a forced mate against the trainee.
  if (playedMate !== null && playedMate < 0) {
    return { kind: "mated", mateIn: Math.abs(playedMate) };
  }
  // Best play had a forced mate for the trainee that the played move gave up.
  // (If the played move itself still mates for the trainee, that's fine → playable.)
  if (baseMate !== null && baseMate > 0 && !(playedMate !== null && playedMate > 0)) {
    return { kind: "missed-mate", mateIn: baseMate, bestMoveUci: baseline.bestMove };
  }
  // Played move also mates for the trainee, or any non-cp edge → playable.
  if (playedMate !== null && playedMate > 0) {
    return { kind: "playable", bestMoveUci: baseline.bestMove };
  }
  // cp path: loss vs best play, trainee perspective.
  const baseCp = toTrainee(baseline.cp, trainee) ?? 0;
  const playedCp = toTrainee(played.cp, trainee) ?? 0;
  const lossCp = baseCp - playedCp;
  if (lossCp <= PLAYABLE_CP) return { kind: "playable", bestMoveUci: baseline.bestMove };
  return { kind: "loses", lossCp, bestMoveUci: baseline.bestMove };
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd chess && npx vitest run tests/evalProvider.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/nick/Work/nicholastacik.github.io
git add chess/src/evalProvider.ts chess/tests/evalProvider.test.ts
git commit -m "feat(chess): analyzeMismatch — trainee-perspective loss-vs-best-play verdict"
```

---

### Task 3: `enumerateLines` in `tree.ts`

**Files:**
- Modify: `chess/src/tree.ts` (append)
- Modify: `chess/tests/tree.test.ts` (append a describe block)

**Interfaces:**
- Consumes: `TreeNode`, `Path`, `pathSans` (existing in `tree.ts`).
- Produces:
  - `interface LineChoice { id: string; label: string; path: Path }`
  - `function enumerateLines(root: TreeNode): LineChoice[]` — one entry per root-to-leaf path. `id` = the path's canonical SAN joined by spaces (stable, unique per move-sequence). `label` = "Mainline" for the all-`children[0]` path, else derived from the first move where the path leaves the mainline (e.g. "2... Nf6" or "vs Nf6"). Display order: mainline first, then the rest in DFS order.

- [ ] **Step 1: Append the failing test** to `chess/tests/tree.test.ts`

```ts
import { enumerateLines } from "../src/tree";

describe("enumerateLines", () => {
  // study: e4 e5 { Nf3, alt Bc4 } Nc6 ; i.e. after 1.e4 e5, White plays Nf3
  // (mainline) or Bc4 (alt). Two root-to-leaf paths.
  const s: Study = {
    id: "t", name: "T", side: "white", intro: "i",
    line: [
      { san: "e4" },
      { san: "e5" },
      { san: "Nf3", alts: [[{ san: "Bc4" }, { san: "Bc5" }]] },
      { san: "Nc6" },
    ],
  };

  it("yields one entry per root-to-leaf path, mainline first", () => {
    const lines = enumerateLines(normalize(s));
    expect(lines.length).toBe(2);
    expect(lines[0]!.label).toBe("Mainline");
    expect(pathSans(lines[0]!.path)).toEqual(["e4", "e5", "Nf3", "Nc6"]);
    expect(pathSans(lines[1]!.path)).toEqual(["e4", "e5", "Bc4", "Bc5"]);
  });

  it("gives each path a stable id from its canonical SAN", () => {
    const lines = enumerateLines(normalize(s));
    expect(lines[0]!.id).toBe("e4 e5 Nf3 Nc6");
    expect(lines[1]!.id).toBe("e4 e5 Bc4 Bc5");
    expect(lines[0]!.id).not.toBe(lines[1]!.id);
  });

  it("distinguishes two paths that would collide on a first-divergence label", () => {
    // Two alts that both start with the same move Bc4 but then diverge, so a
    // 'first divergence' label alone would collide; ids must differ.
    const s2: Study = {
      id: "t2", name: "T2", side: "white", intro: "i",
      line: [
        { san: "e4" },
        { san: "e5", alts: [
          [{ san: "d5" }, { san: "exd5" }, { san: "Qxd5" }],
          [{ san: "d5" }, { san: "Nc3" }, { san: "dxe4" }],
        ] },
      ],
    };
    const ids = enumerateLines(normalize(s2)).map((l) => l.id);
    expect(new Set(ids).size).toBe(ids.length); // all unique
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd chess && npx vitest run tests/tree.test.ts`
Expected: FAIL (`enumerateLines` missing).

- [ ] **Step 3: Append to `chess/src/tree.ts`**

```ts
export interface LineChoice {
  id: string;
  label: string;
  path: Path;
}

// One entry per root-to-leaf path. children[0] is the mainline continuation, so
// the all-first-child path is the mainline; every other leaf is a variation
// labelled by the first ply at which it left the mainline.
export function enumerateLines(root: TreeNode): LineChoice[] {
  const out: LineChoice[] = [];

  function walk(node: TreeNode, path: Path, leftMainlineAt: number | null): void {
    if (node.children.length === 0) {
      const sans = pathSans(path);
      const id = sans.join(" ");
      let label = "Mainline";
      if (leftMainlineAt !== null) {
        const idx = leftMainlineAt; // path index of the diverging move
        const ply = idx; // path[0] is root; path[1] is ply 1
        const san = path[idx]!.san as string;
        const moveNo = Math.ceil(ply / 2);
        label = ply % 2 === 1 ? `${moveNo}. ${san}` : `${moveNo}… ${san}`;
      }
      out.push({ id, label, path });
      return;
    }
    node.children.forEach((child, i) => {
      // A non-first child is a divergence from the mainline at this ply.
      const diverged = leftMainlineAt === null && i > 0 ? path.length : leftMainlineAt;
      walk(child, [...path, child], diverged);
    });
  }

  walk(root, [root], null);
  return out;
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd chess && npx vitest run tests/tree.test.ts`
Expected: PASS (existing tree tests + the 3 new ones).

- [ ] **Step 5: Commit**

```bash
cd /Users/nick/Work/nicholastacik.github.io
git add chess/src/tree.ts chess/tests/tree.test.ts
git commit -m "feat(chess): enumerateLines — root-to-leaf lines with stable ids"
```

---

### Task 4: `practice.ts` — drill state machine

**Files:**
- Create: `chess/src/practice.ts`
- Create: `chess/tests/practice.test.ts`

**Interfaces:**
- Consumes: `Path`, `positionAt`, `TreeNode` (from `tree.ts`).
- Produces:
  - `type Grade = { kind: "correct"; expected: string } | { kind: "mismatch"; expected: string; played: string }`
  - `interface PracticeState { fen: string; ply: number; toMove: "user" | "opponent" | "done"; mistakes: number; revealed: number; cleanFirstTry: number }`
  - `interface Summary { plies: number; cleanFirstTry: number; mistakes: number; revealed: number }`
  - `interface Drill { state(): PracticeState; playOpponent(): { san: string } | null; submit(san: string): Grade; reveal(): string; summary(): Summary }`
  - `function createDrill(line: Path, userSide: "white" | "black"): Drill`
    - `line` is a root-to-leaf `Path` (from `enumerateLines`). The move at `line[1]` is ply 1 (White's first move), `line[2]` ply 2 (Black), etc.
    - The user answers the plies for their side; the other plies are the opponent's book replies.

- [ ] **Step 1: Write the failing test** `chess/tests/practice.test.ts`

```ts
import { describe, it, expect } from "vitest";
import type { Study } from "../src/study";
import { normalize, enumerateLines } from "../src/tree";
import { createDrill } from "../src/practice";

// 1.e4 e5 2.Nf3 Nc6 — mainline only.
const study: Study = {
  id: "t", name: "T", side: "white", intro: "i",
  line: [{ san: "e4" }, { san: "e5" }, { san: "Nf3" }, { san: "Nc6" }],
};
const mainline = () => enumerateLines(normalize(study))[0]!.path;

describe("createDrill (White trainee)", () => {
  it("starts with the user to move (White) at the start position", () => {
    const d = createDrill(mainline(), "white");
    const s = d.state();
    expect(s.toMove).toBe("user");
    expect(s.ply).toBe(0);
    expect(s.fen.split(" ")[0]).toBe("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR");
    expect(d.playOpponent()).toBeNull(); // not the opponent's turn
  });

  it("grades the correct book move and advances to the opponent", () => {
    const d = createDrill(mainline(), "white");
    expect(d.submit("e4")).toEqual({ kind: "correct", expected: "e4" });
    expect(d.state().toMove).toBe("opponent");
    expect(d.playOpponent()).toEqual({ san: "e5" }); // applies + returns Black's book reply
    expect(d.state().toMove).toBe("user");
    expect(d.state().ply).toBe(2);
  });

  it("holds and counts a mismatch without advancing", () => {
    const d = createDrill(mainline(), "white");
    const g = d.submit("d4");
    expect(g).toEqual({ kind: "mismatch", expected: "e4", played: "d4" });
    expect(d.state().toMove).toBe("user");
    expect(d.state().ply).toBe(0);
    expect(d.state().mistakes).toBe(1);
  });

  it("reveal applies the book move and marks the ply non-clean", () => {
    const d = createDrill(mainline(), "white");
    expect(d.reveal()).toBe("e4");
    expect(d.state().toMove).toBe("opponent");
    d.playOpponent();
    d.submit("Nf3");
    d.playOpponent(); // Nc6, final ply (opponent)
    const sum = d.summary();
    expect(sum.revealed).toBe(1);
    expect(sum.cleanFirstTry).toBe(1); // only Nf3 was clean first try
  });

  it("reaches 'done' after the final book move (final move by opponent)", () => {
    const d = createDrill(mainline(), "white");
    d.submit("e4"); d.playOpponent(); // e5
    d.submit("Nf3"); d.playOpponent(); // Nc6 (final, opponent)
    expect(d.state().toMove).toBe("done");
    expect(d.summary()).toEqual({ plies: 4, cleanFirstTry: 2, mistakes: 0, revealed: 0 });
  });
});

describe("createDrill (Black trainee)", () => {
  // Same line, but the user plays Black: opponent (White) moves first.
  it("opponent (White) moves first, then the user answers as Black", () => {
    const d = createDrill(mainline(), "black");
    expect(d.state().toMove).toBe("opponent");
    expect(d.playOpponent()).toEqual({ san: "e4" });
    expect(d.state().toMove).toBe("user");
    expect(d.submit("e5")).toEqual({ kind: "correct", expected: "e5" });
  });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd chess && npx vitest run tests/practice.test.ts`
Expected: FAIL (`createDrill` missing).

- [ ] **Step 3: Implement `chess/src/practice.ts`**

```ts
import type { Path } from "./tree";
import { positionAt } from "./tree";

export type Grade =
  | { kind: "correct"; expected: string }
  | { kind: "mismatch"; expected: string; played: string };

export interface PracticeState {
  fen: string;
  ply: number; // number of book moves applied so far (0 = start position)
  toMove: "user" | "opponent" | "done";
  mistakes: number;
  revealed: number;
  cleanFirstTry: number;
}

export interface Summary {
  plies: number;
  cleanFirstTry: number;
  mistakes: number;
  revealed: number;
}

export interface Drill {
  state(): PracticeState;
  playOpponent(): { san: string } | null;
  submit(san: string): Grade;
  reveal(): string;
  summary(): Summary;
}

// line[0] is the root; line[i] (i>=1) is the book move at ply i. White plays odd
// plies, Black even plies. The user owns the plies for `userSide`.
export function createDrill(line: Path, userSide: "white" | "black"): Drill {
  const moves = line.slice(1); // book SAN nodes, ply 1..N
  const total = moves.length;
  let ply = 0; // book moves applied
  let mistakes = 0;
  let revealed = 0;
  let cleanFirstTry = 0;
  let dirtyThisPly = false; // a mismatch or reveal happened at the current ply

  const sideAt = (nextPly: number): "white" | "black" => (nextPly % 2 === 1 ? "white" : "black");
  const isUsersTurn = (): boolean => ply < total && sideAt(ply + 1) === userSide;

  const toMove = (): PracticeState["toMove"] =>
    ply >= total ? "done" : isUsersTurn() ? "user" : "opponent";

  const expectedSan = (): string => moves[ply]!.san as string;

  const fen = (): string => positionAt(line.slice(0, ply + 1)).fen;

  const advance = (): void => {
    ply += 1;
    dirtyThisPly = false;
  };

  return {
    state(): PracticeState {
      return { fen: fen(), ply, toMove: toMove(), mistakes, revealed, cleanFirstTry };
    },
    playOpponent() {
      if (toMove() !== "opponent") return null;
      const san = expectedSan();
      advance();
      return { san };
    },
    submit(san: string): Grade {
      const expected = expectedSan();
      if (san === expected) {
        if (!dirtyThisPly) cleanFirstTry += 1;
        advance();
        return { kind: "correct", expected };
      }
      mistakes += 1;
      dirtyThisPly = true;
      return { kind: "mismatch", expected, played: san };
    },
    reveal(): string {
      const expected = expectedSan();
      revealed += 1;
      dirtyThisPly = true;
      advance();
      return expected;
    },
    summary(): Summary {
      return { plies: total, cleanFirstTry, mistakes, revealed };
    },
  };
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd chess && npx vitest run tests/practice.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/nick/Work/nicholastacik.github.io
git add chess/src/practice.ts chess/tests/practice.test.ts
git commit -m "feat(chess): practice drill state machine (strict grading, both sides)"
```

---

### Task 5: `board.ts` — movable mode, `destroy()`, legal-dests helper

**Files:**
- Modify: `chess/src/ui.ts` (extend `BoardHandle` with `destroy()`)
- Modify: `chess/src/board.ts` (implement `destroy()`; add `createMovableBoard`; export `legalDests`)
- Modify: `chess/tests/*` — add `chess/tests/board-dests.test.ts` for the pure helper
- Modify: existing view-only `createBoard` callers/tests only if the interface change requires (it is additive: add `destroy`)

**Interfaces:**
- Consumes: `chess.js`, `@lichess-org/chessground`, `BoardHandle` (in `ui.ts`).
- Produces:
  - `BoardHandle` gains `destroy(): void`.
  - `interface MovableBoardHandle extends BoardHandle { setMovable(dests: Map<string, string[]>, turnColor: "white" | "black"): void }`
  - `function createMovableBoard(el, { orientation, onMove }): MovableBoardHandle` where `onMove: (from: string, to: string, promotion?: string) => void`.
  - `function legalDests(fen: string): Map<string, string[]>` — pure, from `chess.js`: for each from-square with legal moves, the list of to-squares. Used to constrain the movable board.

- [ ] **Step 1: Write the failing test** `chess/tests/board-dests.test.ts`

```ts
import { describe, it, expect } from "vitest";
import { legalDests } from "../src/board";

describe("legalDests", () => {
  it("returns 20 origin→dest moves for the start position (16 pawn + 4 knight sources)", () => {
    const d = legalDests("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1");
    // 8 pawns each with 2 dests, 2 knights each with 2 dests → sources: a2..h2, b1, g1
    expect(d.get("e2")).toEqual(expect.arrayContaining(["e3", "e4"]));
    expect(d.get("g1")).toEqual(expect.arrayContaining(["f3", "h3"]));
    const totalMoves = [...d.values()].reduce((n, arr) => n + arr.length, 0);
    expect(totalMoves).toBe(20);
  });
});
```

Note: `board.ts` imports chessground CSS; jsdom tests only exercise the pure `legalDests` (no chessground instantiation), so importing it is fine. `createBoard`/`createMovableBoard` themselves stay manual-verified (chessground needs layout).

- [ ] **Step 2: Run to verify it fails**

Run: `cd chess && npx vitest run tests/board-dests.test.ts`
Expected: FAIL (`legalDests` missing).

- [ ] **Step 3: Extend `BoardHandle` in `chess/src/ui.ts`**

Add `destroy(): void;` to the `BoardHandle` interface:
```ts
export interface BoardHandle {
  setPosition(fen: string, lastMove: [string, string] | undefined, orientation: "white" | "black"): void;
  destroy(): void;
}
```

- [ ] **Step 4: Implement in `chess/src/board.ts`**

Add the import and helper, implement `destroy` on the existing view-only board, and add the movable factory:
```ts
import { Chess } from "chess.js";
import type { BoardHandle } from "./ui";

export interface MovableBoardHandle extends BoardHandle {
  setMovable(dests: Map<string, string[]>, turnColor: "white" | "black"): void;
}

// Pure: legal moves as an origin→dests map (chessground's `movable.dests` shape).
export function legalDests(fen: string): Map<string, string[]> {
  const chess = new Chess(fen);
  const dests = new Map<string, string[]>();
  for (const m of chess.moves({ verbose: true })) {
    const list = dests.get(m.from) ?? [];
    list.push(m.to);
    dests.set(m.from, list);
  }
  return dests;
}
```

In the existing `createBoard`, capture the chessground `Api` and return `destroy() { cg.destroy(); }` alongside `setPosition`.

Add `createMovableBoard`:
```ts
export function createMovableBoard(
  el: HTMLElement,
  opts: { orientation: "white" | "black"; onMove: (from: string, to: string, promotion?: string) => void },
): MovableBoardHandle {
  const cg = Chessground(el, {
    orientation: opts.orientation,
    movable: { free: false, dests: new Map(), showDests: true },
    events: {
      move: (from, to) => opts.onMove(from as string, to as string),
    },
  });
  return {
    setPosition(fen, lastMove, orientation) {
      cg.set({ fen, lastMove: lastMove as never, orientation });
    },
    setMovable(dests, turnColor) {
      cg.set({ turnColor, movable: { free: false, dests, showDests: true, color: turnColor } });
    },
    destroy() {
      cg.destroy();
    },
  };
}
```
Promotion: if `onMove` receives a pawn reaching the last rank, the caller resolves promotion (default a queen for v1; a picker can be added later) — document this in a comment. Keep the CSS imports as they are.

- [ ] **Step 5: Run the pure test + full suite**

Run: `cd chess && npx vitest run tests/board-dests.test.ts && npm test`
Expected: PASS. (The `BoardHandle.destroy` addition may require the study view's fake boards in `tests/ui-study.test.ts` to add a `destroy() {}` stub — update those fakes minimally if TypeScript/tests flag it.)

- [ ] **Step 6: Commit**

```bash
cd /Users/nick/Work/nicholastacik.github.io
git add chess/src/board.ts chess/src/ui.ts chess/tests/board-dests.test.ts chess/tests/ui-study.test.ts
git commit -m "feat(chess): movable board + destroy() + legalDests helper"
```

---

### Task 6: `ui.ts` — Practice mode (entry, line picker, drill loop, teardown, stale guard)

**Files:**
- Modify: `chess/src/ui.ts` (add Practice mode)
- Modify: `chess/src/style.css` (practice styles)
- Create: `chess/tests/ui-practice.test.ts`

**Interfaces:**
- Consumes: `enumerateLines`/`LineChoice` (tree), `createDrill`/`Drill` (practice), `EvalProvider`/`analyzeMismatch`/`MismatchVerdict` (evalProvider), `MovableBoardHandle`/`legalDests` (board), `positionAt` (tree).
- Produces:
  - `interface PracticeDeps { makeMovableBoard: (el, opts) => MovableBoardHandle; evalProvider: EvalProvider }`
  - `function renderPractice(root: HTMLElement, study: Study, deps: PracticeDeps): void` — line picker → drill. Rendered contract for tests: a `.line-picker` with a `.line-choice[data-id]` per line; on pick, a `.practice` view with `.practice-status`, `.practice-feedback`, and `.btn-reveal` / `.btn-restart` / `.btn-exit`; the movable board is created via `deps.makeMovableBoard`.
  - A **Practice** entry button added to `renderStudyView` that swaps the viewer for `renderPractice` (removing the viewer's keydown handler and calling `board.destroy()` first).

- [ ] **Step 1: Write the failing test** `chess/tests/ui-practice.test.ts`

```ts
import { describe, it, expect, vi } from "vitest";
import { renderPractice, type PracticeDeps } from "../src/ui";
import type { Study } from "../src/study";
import type { EngineEval } from "../src/evalProvider";

const study: Study = {
  id: "t", name: "T", side: "white", intro: "i",
  line: [{ san: "e4" }, { san: "e5" }, { san: "Nf3" }, { san: "Nc6" }],
};

function fakeBoard() {
  const calls: string[] = [];
  const handle = {
    setPosition: () => calls.push("setPosition"),
    setMovable: () => calls.push("setMovable"),
    destroy: () => calls.push("destroy"),
  };
  return { make: (_el: HTMLElement, _o: unknown) => handle as never, handle, calls };
}

// Provider whose promises we resolve manually, to drive race tests.
function deferredProvider() {
  const pending: Array<(e: EngineEval) => void> = [];
  const provider = { evaluate: vi.fn(() => new Promise<EngineEval>((res) => pending.push(res))) };
  return { provider, resolveNext: (e: EngineEval) => pending.shift()!(e) };
}

function mount(): HTMLElement {
  const root = document.createElement("div");
  document.body.appendChild(root);
  return root;
}

describe("renderPractice", () => {
  it("renders a line picker with one choice per line", () => {
    const fb = fakeBoard();
    const root = mount();
    renderPractice(root, study, { makeMovableBoard: fb.make, evalProvider: { evaluate: vi.fn() } });
    expect(root.querySelectorAll(".line-choice").length).toBe(1); // mainline only
  });

  it("a correct move advances; the opponent replies automatically", () => {
    const fb = fakeBoard();
    const root = mount();
    const onMove = captureOnMove(fb);
    renderPractice(root, study, { makeMovableBoard: fb.make, evalProvider: { evaluate: vi.fn() } });
    root.querySelector<HTMLElement>(".line-choice")!.click();
    onMove.current("e2", "e4"); // play e4
    expect(root.querySelector(".practice-status")!.textContent).not.toContain("mismatch");
    // board received the opponent's reply position
    expect(fb.calls.filter((c) => c === "setPosition").length).toBeGreaterThan(1);
  });

  it("a mismatch calls the engine and renders the verdict", async () => {
    const dp = deferredProvider();
    const fb = fakeBoard();
    const root = mount();
    const onMove = captureOnMove(fb);
    renderPractice(root, study, { makeMovableBoard: fb.make, evalProvider: dp.provider });
    root.querySelector<HTMLElement>(".line-choice")!.click();
    onMove.current("d2", "d4"); // wrong: book is e4
    expect(root.querySelector(".practice-feedback")!.textContent).toContain("e4"); // book shown immediately
    // two evals requested (baseline + played); resolve them
    dp.resolveNext({ bestMove: "e2e4", cp: 30, mate: null, depth: 12 });
    dp.resolveNext({ bestMove: "e2e4", cp: -230, mate: null, depth: 12 });
    await Promise.resolve(); await Promise.resolve();
    expect(root.querySelector(".practice-feedback")!.textContent).toMatch(/loses/i);
  });

  it("drops a stale engine result that resolves after Exit", async () => {
    const dp = deferredProvider();
    const fb = fakeBoard();
    const root = mount();
    const onMove = captureOnMove(fb);
    renderPractice(root, study, { makeMovableBoard: fb.make, evalProvider: dp.provider });
    root.querySelector<HTMLElement>(".line-choice")!.click();
    onMove.current("d2", "d4");
    root.querySelector<HTMLElement>(".btn-exit")!.click(); // leave before results arrive
    expect(fb.calls).toContain("destroy");
    dp.resolveNext({ bestMove: "e2e4", cp: 30, mate: null, depth: 12 });
    dp.resolveNext({ bestMove: "e2e4", cp: -230, mate: null, depth: 12 });
    await Promise.resolve(); await Promise.resolve();
    // feedback from the abandoned drill must not reappear
    expect(root.querySelector(".practice-feedback")).toBeNull();
  });

  it("degrades gracefully when the engine rejects", async () => {
    const provider = { evaluate: vi.fn(async () => { throw new Error("network"); }) };
    const fb = fakeBoard();
    const root = mount();
    const onMove = captureOnMove(fb);
    renderPractice(root, study, { makeMovableBoard: fb.make, evalProvider: provider });
    root.querySelector<HTMLElement>(".line-choice")!.click();
    onMove.current("d2", "d4");
    await Promise.resolve(); await Promise.resolve();
    const fb2 = root.querySelector(".practice-feedback")!;
    expect(fb2.textContent).toContain("e4"); // still shows the book move
    expect(fb2.textContent).toMatch(/couldn.t reach the engine/i);
  });
});

// Helper: renderPractice passes an onMove callback into makeMovableBoard; capture it.
function captureOnMove(fb: ReturnType<typeof fakeBoard>) {
  const ref: { current: (from: string, to: string, promo?: string) => void } = { current: () => {} };
  const orig = fb.make;
  (fb as { make: PracticeDeps["makeMovableBoard"] }).make = (el, opts) => {
    ref.current = (opts as { onMove: typeof ref.current }).onMove;
    return orig(el, opts as never);
  };
  return ref;
}
```

Note: the test wires `captureOnMove` before `renderPractice` reads `deps.makeMovableBoard`; if ordering is awkward in practice, restructure so `makeMovableBoard` records `opts.onMove` into a shared ref. The behaviors under test are: line picker renders; correct advances + opponent auto-replies; mismatch shows book immediately + engine verdict after resolve; stale result after Exit is dropped and `destroy()` was called; engine rejection degrades gracefully.

- [ ] **Step 2: Run to verify it fails**

Run: `cd chess && npx vitest run tests/ui-practice.test.ts`
Expected: FAIL (`renderPractice` missing).

- [ ] **Step 3: Implement `renderPractice` in `chess/src/ui.ts`**

Add imports:
```ts
import { enumerateLines, type LineChoice } from "./tree";
import { createDrill, type Drill } from "./practice";
import { analyzeMismatch, type EvalProvider, type MismatchVerdict } from "./evalProvider";
import { legalDests, type MovableBoardHandle } from "./board";
```

Add:
```ts
export interface PracticeDeps {
  makeMovableBoard: (
    el: HTMLElement,
    opts: { orientation: "white" | "black"; onMove: (from: string, to: string, promotion?: string) => void },
  ) => MovableBoardHandle;
  evalProvider: EvalProvider;
}

function trainerSide(side: Study["side"]): "white" | "black" {
  return side === "black" ? "black" : "white"; // "both" → white in v1
}

function verdictText(v: MismatchVerdict, bookSan: string): string {
  switch (v.kind) {
    case "playable": return `Not your line — book move is ${bookSan}. Your move is a playable alternative.`;
    case "loses": return `Not your line — book move is ${bookSan}. Your move loses ~${(v.lossCp / 100).toFixed(1)}; the engine prefers ${v.bestMoveUci}.`;
    case "mated": return `Not your line — book move is ${bookSan}. Your move gets mated in ${v.mateIn}.`;
    case "missed-mate": return `Not your line — book move is ${bookSan}. A forced mate in ${v.mateIn} was available (${v.bestMoveUci}).`;
  }
}
```

`renderPractice` builds the line picker (`enumerateLines(normalize(study))`), and on a pick constructs the drill view. Core drill wiring (pseudocode-precise — implement literally):
```ts
export function renderPractice(root: HTMLElement, study: Study, deps: PracticeDeps): void {
  root.innerHTML = "";
  const side = trainerSide(study.side);
  const lines = enumerateLines(normalize(study));

  // --- line picker ---
  const picker = document.createElement("div");
  picker.className = "line-picker";
  for (const line of lines) {
    const btn = document.createElement("button");
    btn.className = "line-choice";
    btn.dataset.id = line.id;
    btn.textContent = line.label;
    btn.addEventListener("click", () => startDrill(line));
    picker.appendChild(btn);
  }
  root.append(pickerHeader(study), picker, exitButton(() => leave()));

  let board: MovableBoardHandle | null = null;
  let drill: Drill | null = null;
  let sessionId = 0; // bumped on every start/restart/exit; guards stale evals

  function startDrill(line: LineChoice): void {
    sessionId += 1;
    const mySession = sessionId;
    drill = createDrill(line.path, side);
    root.innerHTML = "";
    const boardEl = document.createElement("div");
    boardEl.className = "board";
    const status = div("practice-status");
    const feedback = div("practice-feedback");
    const controls = practiceControls(
      () => { const san = drill!.reveal(); showBook(san); syncBoard(); },
      () => startDrill(line),   // restart
      () => leave(),            // exit
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

  async function runAnalysis(mySession: number, attempt: number, fenBefore: string, from: string, to: string, bookSan: string, feedback: HTMLElement): Promise<void> {
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
    return mySession === sessionId && !!drill && drill.state().mistakes === attempt && drill.state().toMove === "user";
  }

  function leave(): void {
    sessionId += 1;   // invalidate any in-flight analysis
    board?.destroy();
    board = null;
    drill = null;
    // caller (study view) is responsible for restoring the viewer; here we clear.
    root.innerHTML = "";
  }
  // ... small DOM helpers: div(), pickerHeader(), exitButton(), practiceControls(),
  //     renderSummary(), showBook(), toSan(), fenAfterMove() (chess.js) ...
}
```
The stale guard is the `(sessionId, attempt)` pair checked by `isCurrent` before any async result mutates the DOM (§spec: `(sessionId, ply, attempt)` — `ply` is implied by the drill instance + `mySession`). `toSan`/`fenAfterMove` use `chess.js` (`new Chess(fen).move({from,to,promotion:"q"})` → `.san` / `.fen()`), defaulting promotion to queen for v1.

- [ ] **Step 4: Wire the Practice entry into `renderStudyView`**

In `renderStudyView`, add a **Practice** button to `.controls`. On click: remove the viewer's `keydown` handler, `board.destroy()` the view-only board, and call `renderPractice(root, study, deps)`. When practice `leave()`s, re-invoke `renderStudyView` to restore the viewer. Extend `StudyViewDeps` to also carry `makeMovableBoard` + `evalProvider` (or pass a combined deps object). Ensure the existing MutationObserver teardown still removes the viewer keydown handler when `root` is cleared by practice.

- [ ] **Step 5: Add practice styles to `chess/src/style.css`**

```css
.line-picker { display: flex; flex-direction: column; gap: 0.4rem; max-width: 420px; margin: 1rem auto; padding: 0 1rem; }
.line-choice { text-align: left; padding: 0.6rem 0.8rem; border: 1px solid #ddd; border-radius: 6px; background: #fff; cursor: pointer; font: inherit; }
.line-choice:hover { border-color: #888; }
.practice { display: grid; grid-template-columns: minmax(280px, 460px) 1fr; gap: 1rem; max-width: 900px; margin: 0 auto; padding: 1rem; align-items: start; }
.practice .board { width: 100%; aspect-ratio: 1 / 1; }
.practice-status { font-weight: 600; }
.practice-feedback { min-height: 3rem; line-height: 1.5; color: #444; }
.practice-controls { display: flex; gap: 0.5rem; margin-top: 0.5rem; }
@media (max-width: 700px) { .practice { grid-template-columns: 1fr; } }
```

- [ ] **Step 6: Run the practice tests + full suite + build**

Run: `cd chess && npx vitest run tests/ui-practice.test.ts && npm test && npm run build`
Expected: all PASS; build succeeds.

- [ ] **Step 7: Manually verify end-to-end**

Run: `cd chess && npm run dev`; open a study → **Practice** → pick the mainline; play the book moves (opponent auto-replies); play a wrong move and confirm the book move shows immediately and the engine verdict follows; Reveal, Restart, Exit all work; Exit restores the viewer. Stop the server.

- [ ] **Step 8: Commit**

```bash
cd /Users/nick/Work/nicholastacik.github.io
git add chess/src/ui.ts chess/src/style.css chess/tests/ui-practice.test.ts
git commit -m "feat(chess): Practice mode — drill lines with engine-verified feedback"
```

---

### Task 7: Rebuild committed bundle + blog note

**Files:**
- Modify (generated): `posts/chess/app/**`
- Modify: `posts/chess/index.qmd` (a short "Practice mode" paragraph)

**Interfaces:** none (publishing artifacts).

- [ ] **Step 1: Add a short Practice-mode paragraph to `posts/chess/index.qmd`**

After the existing "How it's built" section, add ~3 sentences: you can now drill a line from memory (Practice mode), it grades strictly against your repertoire, and on a wrong move a hosted Stockfish (chess-api.com) shows how much the move loses vs the best line — the same engine plumbing a future "learn from my chess.com blunders" trainer will reuse.

- [ ] **Step 2: Rebuild the committed app bundle**

Run: `cd chess && npm run build`
Expected: tests run green + `../posts/chess/app` regenerated.

- [ ] **Step 3: Commit**

```bash
cd /Users/nick/Work/nicholastacik.github.io
git add posts/chess/index.qmd posts/chess/app
git commit -m "build(chess): publish Practice mode (rebuild bundle + blog note)"
```

- [ ] **Step 4: Final verification**

Run: `cd chess && npm test && npm run build`
Expected: all tests pass; build succeeds. Do not push/merge unless the user asks.

---

## Self-Review

**Spec coverage:**
- Practice mode inside the study view → Task 6. ✓
- One line at a time, line picker → Tasks 3 (enumerateLines) + 6. ✓
- Strict grading, exact book move → Task 4 (`submit`). ✓
- Mismatch (not "mistake"); engine loss-vs-best-play only; no stronger-than-book → Task 2 (`analyzeMismatch`) + Task 6 (`verdictText`). ✓
- Baseline = decision position, played = after-move, trainee-perspective, mate handling → Task 2. ✓
- Opponent auto-replies (`playOpponent` applies) → Task 4 + Task 6 (`autoPlayOpponent`). ✓
- Movable board + `destroy()` + legal dests → Task 5. ✓
- Pluggable `EvalProvider`, chess-api.com default (White-perspective, string-cp coercion), localStorage cache → Task 1. ✓
- Auto feedback on mismatch → Task 6. ✓
- Stable line ids persisted (completion) → Task 3 (ids); completion persistence is a small addition in Task 6's summary/leave (keyed by id) — **covered**, see note below.
- Stale-async guard `(session, attempt)` → Task 6 (`isCurrent`). ✓
- Teardown contract (viewer keydown removed, boards destroyed) → Tasks 5 + 6. ✓
- Graceful engine-failure degradation → Task 6. ✓
- Tests: adapter (cp+mate+string coercion), analyze (both sides/mate/playable), enumerateLines (ids/collision), drill (both sides/completion/summary), dests, ui-practice (advance/mismatch/stale-after-exit/failure) → Tasks 1–6. ✓

**Gap found & fixed inline:** completion persistence (localStorage `chess:practice:<studyId>` → set of completed line ids) was named in the spec but not given its own step. It is small; fold it into Task 6, Step 3 (`renderSummary` marks the line id complete via a tolerant localStorage read/write, and the line picker marks completed choices) — add a unit test in `ui-practice.test.ts` asserting a completed line's id is written to a fake `Storage`. Implementers: treat this as part of Task 6.

**Placeholder scan:** the Task-6 drill wiring is given as precise pseudocode with named helpers rather than 100% literal source (the DOM helpers `div()`, `practiceControls()`, `toSan()`, `fenAfterMove()` are described with their exact `chess.js` calls). This is the one task where the plan specifies behavior + key code rather than a full transcription — acceptable because it's UI glue over already-fully-specified pure modules, and the tests pin the observable contract. All pure-logic tasks (1–5) have complete literal code.

**Type consistency:** `EngineEval` (Task 1) is consumed unchanged by `analyzeMismatch` (Task 2) and `runAnalysis` (Task 6). `Drill`/`Grade`/`PracticeState` (Task 4) match their use in Task 6. `BoardHandle.destroy()` (Task 5) is implemented by both boards and called in Task 6's `leave()`. `MovableBoardHandle`/`legalDests` (Task 5) match Task 6's `makeMovableBoard`/`syncBoard`. `enumerateLines`→`LineChoice` (Task 3) feeds Task 6's picker. Trainee-perspective side derivation (`trainerSide`) is the single source for "which side is the user" and is passed into `createDrill`, `analyzeMismatch`, and the board orientation.
