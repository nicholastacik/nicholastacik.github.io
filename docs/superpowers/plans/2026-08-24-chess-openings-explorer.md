# Chess Openings Explorer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an interactive web page that lets you walk chess openings move-by-move on a board, with a clickable variation tree and per-move prose, plus a Claude skill to draft new openings and a blog post.

**Architecture:** A Vite/TypeScript single-page app in `chess/`, mirroring the existing `codenames/` project: `vite build` outputs a static bundle to `../posts/chess/app`, which Quarto copies into the site and the blog post links to. Studies are authored as JSON of moves + prose (no precomputed positions); the app replays SAN with `chess.js` at load to derive board positions, and renders them with `@lichess-org/chessground`. Move legality is enforced by the test suite, not the browser.

**Tech Stack:** TypeScript, Vite, Vitest (+ jsdom), Zod, `chess.js` (legality + SAN→position), `@lichess-org/chessground` (board rendering only).

**Spec:** `docs/superpowers/specs/2026-08-24-chess-openings-explorer-design.md`

## Global Constraints

- **Project location:** all app code lives under `chess/`; all commands run from `chess/` unless stated. The repo root is `/Users/nick/Work/nicholastacik.github.io`.
- **Build output:** `vite build` MUST write to `../posts/chess/app` (via `build.outDir`), with `base: "./"`. This is what Quarto publishes.
- **Match codenames conventions:** vanilla TS (no UI framework), strict tsconfig with `noUncheckedIndexedAccess`, pure logic in testable modules, DOM/board wired at the bottom of `main.ts` and via injected dependencies so logic is testable under jsdom.
- **`package.json` scripts:** `dev` = `vite`; `build` = `tsc --noEmit && vite build`; `test` = `vitest run`; `test:watch` = `vitest`.
- **Study id rule:** a study's `id` is a slug matching `^[a-z0-9-]+$` and MUST equal its filename stem (`src/studies/<id>.json`).
- **SAN dialect:** all moves are standard algebraic notation as `chess.js` accepts it: castling is `O-O` / `O-O-O` (capital letter O, not zero), promotion is `e8=Q`, captures `exd5` / `Nxe5`, disambiguation `Nbd2` / `R1e2`, check/mate suffixes `+` / `#` are allowed.
- **Commit style:** conventional commits, one per task step where indicated. End every commit message body with:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- **Do not push or open PRs** unless the user asks. Work stays on branch `chess-openings-explorer`.

---

### Task 1: Project scaffold & build wiring

Creates the Vite/TS project skeleton and proves it builds to the correct output directory. No app logic yet.

**Files:**
- Create: `chess/package.json`
- Create: `chess/tsconfig.json`
- Create: `chess/vite.config.ts`
- Create: `chess/index.html`
- Create: `chess/src/main.ts`
- Create: `chess/src/style.css`
- Create: `chess/.gitignore`
- Create: `chess/tests/scaffold.test.ts`

**Interfaces:**
- Consumes: nothing (first task).
- Produces: a working `npm run build` and `npm test`; the `src/` and `tests/` layout every later task extends.

- [ ] **Step 1: Create `chess/package.json`**

```json
{
  "name": "chess-openings",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "tsc --noEmit && vite build",
    "test": "vitest run",
    "test:watch": "vitest"
  },
  "dependencies": {
    "@lichess-org/chessground": "^9.1.1",
    "chess.js": "^1.0.0"
  },
  "devDependencies": {
    "jsdom": "^25.0.0",
    "typescript": "^5.5.0",
    "vite": "^5.4.0",
    "vitest": "^2.1.0",
    "zod": "^3.23.8"
  }
}
```

- [ ] **Step 2: Create `chess/tsconfig.json`** (matches codenames)

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler",
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "esModuleInterop": true,
    "skipLibCheck": true,
    "resolveJsonModule": true,
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "types": ["vitest/globals"]
  },
  "include": ["src", "tests"]
}
```

- [ ] **Step 3: Create `chess/vite.config.ts`**

```ts
import { defineConfig } from "vite";

export default defineConfig({
  base: "./",
  build: { outDir: "../posts/chess/app", emptyOutDir: true },
  test: { environment: "jsdom", globals: true },
});
```

- [ ] **Step 4: Create `chess/index.html`**

```html
<!doctype html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>Chess Openings Explorer</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.ts"></script>
  </body>
</html>
```

- [ ] **Step 5: Create a minimal `chess/src/main.ts` and `chess/src/style.css`**

`chess/src/main.ts`:
```ts
import "./style.css";

if (typeof document !== "undefined" && document.getElementById("app")) {
  document.getElementById("app")!.textContent = "Chess Openings Explorer";
}
```

`chess/src/style.css`:
```css
:root { font-family: system-ui, sans-serif; }
body { margin: 0; }
```

- [ ] **Step 6: Create `chess/.gitignore`**

```
node_modules/
```

- [ ] **Step 7: Write the scaffold test** `chess/tests/scaffold.test.ts`

```ts
import { describe, it, expect } from "vitest";

describe("scaffold", () => {
  it("runs the vitest + jsdom environment", () => {
    const el = document.createElement("div");
    el.textContent = "ok";
    expect(el.textContent).toBe("ok");
  });
});
```

- [ ] **Step 8: Install dependencies**

Run: `cd chess && npm install`
Expected: dependencies install; `node_modules/@lichess-org/chessground` and `node_modules/chess.js` exist.

- [ ] **Step 9: Verify the test runs**

Run: `cd chess && npm test`
Expected: PASS (1 test).

- [ ] **Step 10: Verify the build outputs to the right place**

Run: `cd chess && npm run build`
Expected: build succeeds and creates `posts/chess/app/index.html` (i.e. `../posts/chess/app/` relative to `chess/`).

- [ ] **Step 11: Commit**

```bash
cd /Users/nick/Work/nicholastacik.github.io
git add chess/package.json chess/package-lock.json chess/tsconfig.json chess/vite.config.ts chess/index.html chess/src/main.ts chess/src/style.css chess/.gitignore chess/tests/scaffold.test.ts
git commit -m "chore(chess): scaffold vite/ts app with build wiring"
```

Note: `chess/node_modules/` is gitignored; `posts/chess/app/` build output is committed later (Task 9) once it's meaningful. If `posts/chess/app/` was created by the build, leave it uncommitted for now.

---

### Task 2: Study schema & types

Defines the authored study shape and a Zod validator. Pure, no DOM.

**Files:**
- Create: `chess/src/study.ts`
- Create: `chess/tests/schema.test.ts`

**Interfaces:**
- Consumes: nothing from other tasks (uses `zod`).
- Produces:
  - `interface Shape { orig: string; dest?: string; brush: string }`
  - `interface AuthoredNode { san: string; comment?: string; nag?: string; shapes?: Shape[]; alts?: AuthoredNode[][] }`
  - `interface Study { id: string; name: string; eco?: string; side: "white" | "black" | "both"; intro: string; line: AuthoredNode[] }`
  - `const studySchema: z.ZodType<Study>` — parses/validates a study object.
  - `function parseStudy(data: unknown): Study` — `studySchema.parse(data)`.

- [ ] **Step 1: Write the failing test** `chess/tests/schema.test.ts`

```ts
import { describe, it, expect } from "vitest";
import { parseStudy } from "../src/study";

const good = {
  id: "italian-game",
  name: "Italian Game",
  eco: "C50",
  side: "white",
  intro: "Quick development and pressure on f7.",
  line: [
    { san: "e4", comment: "Stake the center." },
    { san: "e5" },
    { san: "Nf3", comment: "Attacks e5." },
    {
      san: "Nc6",
      alts: [
        [{ san: "Nf6", comment: "The Petrov." }],
      ],
    },
  ],
};

describe("parseStudy", () => {
  it("accepts a valid study", () => {
    const s = parseStudy(good);
    expect(s.id).toBe("italian-game");
    expect(s.line[3]!.alts![0]![0]!.san).toBe("Nf6");
  });

  it("rejects a bad id slug", () => {
    expect(() => parseStudy({ ...good, id: "Italian Game" })).toThrow();
  });

  it("rejects a bad side", () => {
    expect(() => parseStudy({ ...good, side: "grey" })).toThrow();
  });

  it("rejects an empty line", () => {
    expect(() => parseStudy({ ...good, line: [] })).toThrow();
  });

  it("rejects a node missing san", () => {
    expect(() => parseStudy({ ...good, line: [{ comment: "no move" }] })).toThrow();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chess && npx vitest run tests/schema.test.ts`
Expected: FAIL (cannot import `parseStudy`).

- [ ] **Step 3: Implement `chess/src/study.ts`**

```ts
import { z } from "zod";

export interface Shape {
  orig: string;
  dest?: string;
  brush: string;
}

export interface AuthoredNode {
  san: string;
  comment?: string;
  nag?: string;
  shapes?: Shape[];
  alts?: AuthoredNode[][];
}

export interface Study {
  id: string;
  name: string;
  eco?: string;
  side: "white" | "black" | "both";
  intro: string;
  line: AuthoredNode[];
}

const shapeSchema: z.ZodType<Shape> = z
  .object({
    orig: z.string(),
    dest: z.string().optional(),
    brush: z.string(),
  })
  .strict();

const nodeSchema: z.ZodType<AuthoredNode> = z.lazy(() =>
  z
    .object({
      san: z.string().min(2),
      comment: z.string().optional(),
      nag: z.string().optional(),
      shapes: z.array(shapeSchema).optional(),
      alts: z.array(z.array(nodeSchema)).optional(),
    })
    .strict(),
);

export const studySchema: z.ZodType<Study> = z
  .object({
    id: z.string().regex(/^[a-z0-9-]+$/),
    name: z.string().min(1),
    eco: z.string().optional(),
    side: z.enum(["white", "black", "both"]),
    intro: z.string().min(1),
    line: z.array(nodeSchema).min(1),
  })
  .strict();

export function parseStudy(data: unknown): Study {
  return studySchema.parse(data);
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chess && npx vitest run tests/schema.test.ts`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
cd /Users/nick/Work/nicholastacik.github.io
git add chess/src/study.ts chess/tests/schema.test.ts
git commit -m "feat(chess): study schema and zod validation"
```

---

### Task 3: Tree model — normalize, navigate, replay, validate legality

Converts the authored `line`/`alts` shape into a children-based tree, replays SAN with `chess.js` to get positions, and exposes pure navigation helpers. This is the logical heart of the app.

**Files:**
- Create: `chess/src/tree.ts`
- Create: `chess/tests/tree.test.ts`

**Interfaces:**
- Consumes: from `study.ts` — `Study`, `AuthoredNode`, `Shape`.
- Produces:
  - `interface TreeNode { san: string | null; comment?: string; nag?: string; shapes?: Shape[]; children: TreeNode[] }` (root has `san === null`; `children[0]` is the mainline continuation).
  - `type Path = TreeNode[]` (root-first; last element is the current node).
  - `function normalize(study: Study): TreeNode`
  - `function pathSans(path: Path): string[]`
  - `function replay(sans: string[]): { fen: string; lastMove?: [string, string] }` (throws on an illegal move).
  - `function positionAt(path: Path): { fen: string; lastMove?: [string, string] }`
  - `function validateLegality(root: TreeNode): string[]` (`[]` = every move legal).
  - `function stepForward(path: Path): Path | null` (advance to `children[0]`, else null).
  - `function stepBack(path: Path): Path | null` (drop last node, else null at root).
  - `function siblings(path: Path): TreeNode[]` (nodes sharing the current node's parent, in order; `[]` at root).
  - `function switchSibling(path: Path, node: TreeNode): Path` (replace the current node with a sibling).

- [ ] **Step 1: Write the failing test** `chess/tests/tree.test.ts`

```ts
import { describe, it, expect } from "vitest";
import type { Study } from "../src/study";
import {
  normalize,
  pathSans,
  replay,
  positionAt,
  validateLegality,
  stepForward,
  stepBack,
  siblings,
  switchSibling,
  type Path,
} from "../src/tree";

const START = "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR";
const AFTER_E4 = "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR";

const study: Study = {
  id: "t",
  name: "T",
  side: "white",
  intro: "intro",
  line: [
    { san: "e4" },
    { san: "e5" },
    {
      san: "Nf3",
      alts: [[{ san: "Bc4" }]], // alternative to Nf3 at White's 2nd move
    },
    { san: "Nc6" },
  ],
};

describe("normalize", () => {
  it("builds a root with null san and mainline at children[0]", () => {
    const root = normalize(study);
    expect(root.san).toBeNull();
    expect(root.children[0]!.san).toBe("e4");
    expect(root.children[0]!.children[0]!.san).toBe("e5");
  });

  it("places alts as siblings of the mainline node under the same parent", () => {
    const root = normalize(study);
    const afterE5 = root.children[0]!.children[0]!; // node reached after 1.e4 e5
    expect(afterE5.children.map((c) => c.san)).toEqual(["Nf3", "Bc4"]);
  });
});

describe("replay", () => {
  it("returns the start position for no moves", () => {
    expect(replay([]).fen.split(" ")[0]).toBe(START);
  });

  it("computes position and lastMove after e4", () => {
    const r = replay(["e4"]);
    expect(r.fen.split(" ")[0]).toBe(AFTER_E4);
    expect(r.lastMove).toEqual(["e2", "e4"]);
  });

  it("throws on an illegal move", () => {
    expect(() => replay(["e5"])).toThrow();
  });
});

describe("navigation", () => {
  it("pathSans skips the root", () => {
    const root = normalize(study);
    const path: Path = [root, root.children[0]!]; // root -> e4
    expect(pathSans(path)).toEqual(["e4"]);
  });

  it("positionAt replays the path", () => {
    const root = normalize(study);
    const path: Path = [root, root.children[0]!];
    expect(positionAt(path).lastMove).toEqual(["e2", "e4"]);
  });

  it("stepForward follows the mainline; stepBack reverses it", () => {
    const root = normalize(study);
    let path: Path | null = [root];
    path = stepForward(path!);
    expect(path![path!.length - 1]!.san).toBe("e4");
    path = stepBack(path!);
    expect(path!.length).toBe(1);
    expect(stepBack(path!)).toBeNull();
  });

  it("siblings returns alternatives at the branch point; switchSibling swaps line", () => {
    const root = normalize(study);
    // path root -> e4 -> e5 -> Nf3
    const e4 = root.children[0]!;
    const e5 = e4.children[0]!;
    const nf3 = e5.children[0]!;
    const path: Path = [root, e4, e5, nf3];
    expect(siblings(path).map((n) => n.san)).toEqual(["Nf3", "Bc4"]);
    const bc4 = e5.children[1]!;
    const swapped = switchSibling(path, bc4);
    expect(swapped[swapped.length - 1]!.san).toBe("Bc4");
    expect(pathSans(swapped)).toEqual(["e4", "e5", "Bc4"]);
  });
});

describe("validateLegality", () => {
  it("returns [] when all moves are legal", () => {
    expect(validateLegality(normalize(study))).toEqual([]);
  });

  it("reports an illegal move", () => {
    const bad: Study = { ...study, line: [{ san: "e4" }, { san: "e4" }] };
    const errs = validateLegality(normalize(bad));
    expect(errs.length).toBe(1);
    expect(errs[0]).toContain("e4");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chess && npx vitest run tests/tree.test.ts`
Expected: FAIL (cannot import from `../src/tree`).

- [ ] **Step 3: Implement `chess/src/tree.ts`**

```ts
import { Chess } from "chess.js";
import type { AuthoredNode, Shape, Study } from "./study";

export interface TreeNode {
  san: string | null;
  comment?: string;
  nag?: string;
  shapes?: Shape[];
  children: TreeNode[];
}

export type Path = TreeNode[];

function normalizeLine(line: AuthoredNode[], parent: TreeNode): void {
  let prev = parent;
  for (const authored of line) {
    const node: TreeNode = {
      san: authored.san,
      comment: authored.comment,
      nag: authored.nag,
      shapes: authored.shapes,
      children: [],
    };
    // The mainline node is appended first, so it stays at children[0].
    prev.children.push(node);
    // alts on this authored node are alternatives *to* it: they branch from
    // the same parent (prev), becoming siblings after the mainline node.
    if (authored.alts) {
      for (const altLine of authored.alts) normalizeLine(altLine, prev);
    }
    prev = node;
  }
}

export function normalize(study: Study): TreeNode {
  const root: TreeNode = { san: null, children: [] };
  normalizeLine(study.line, root);
  return root;
}

export function pathSans(path: Path): string[] {
  return path.slice(1).map((n) => n.san as string);
}

export function replay(sans: string[]): { fen: string; lastMove?: [string, string] } {
  const chess = new Chess();
  let lastMove: [string, string] | undefined;
  for (const san of sans) {
    const m = chess.move(san); // throws on an illegal move (chess.js v1)
    lastMove = [m.from, m.to];
  }
  return { fen: chess.fen(), lastMove };
}

export function positionAt(path: Path): { fen: string; lastMove?: [string, string] } {
  return replay(pathSans(path));
}

export function validateLegality(root: TreeNode): string[] {
  const errors: string[] = [];
  function walk(node: TreeNode, sans: string[]): void {
    for (const child of node.children) {
      const seq = [...sans, child.san as string];
      try {
        replay(seq);
      } catch {
        errors.push(`Illegal move ${child.san} after ${sans.join(" ") || "start"}`);
        continue; // don't recurse past an illegal position
      }
      walk(child, seq);
    }
  }
  walk(root, []);
  return errors;
}

export function stepForward(path: Path): Path | null {
  const current = path[path.length - 1]!;
  const next = current.children[0];
  return next ? [...path, next] : null;
}

export function stepBack(path: Path): Path | null {
  return path.length > 1 ? path.slice(0, -1) : null;
}

export function siblings(path: Path): TreeNode[] {
  if (path.length < 2) return [];
  const parent = path[path.length - 2]!;
  return parent.children;
}

export function switchSibling(path: Path, node: TreeNode): Path {
  return [...path.slice(0, -1), node];
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chess && npx vitest run tests/tree.test.ts`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
cd /Users/nick/Work/nicholastacik.github.io
git add chess/src/tree.ts chess/tests/tree.test.ts
git commit -m "feat(chess): tree normalization, navigation, and legality validation"
```

---

### Task 4: Study loading & the first real study (integrity gate)

Auto-discovers study JSON files via Vite's `import.meta.glob`, validates them against the schema, and adds the first real opening. The integrity test replays every study and is the gate that makes the Claude skill trustworthy.

**Files:**
- Create: `chess/src/studies/italian-game.json`
- Modify: `chess/src/study.ts` (add `loadStudies`)
- Create: `chess/tests/integrity.test.ts`

**Interfaces:**
- Consumes: from `study.ts` — `studySchema`, `Study`; from `tree.ts` — `normalize`, `validateLegality`.
- Produces:
  - `function loadStudies(): Study[]` in `study.ts` — reads `./studies/*.json`, validates each, returns them sorted by `name`.

- [ ] **Step 1: Create the first real study** `chess/src/studies/italian-game.json`

```json
{
  "id": "italian-game",
  "name": "Italian Game",
  "eco": "C50",
  "side": "white",
  "intro": "The Italian Game develops quickly, points the bishop at Black's weak f7-square, and fights for the center. It leads to both quiet positional play (Giuoco Pianissimo) and sharp lines.",
  "line": [
    { "san": "e4", "comment": "Stake a claim in the center and open lines for the bishop and queen." },
    { "san": "e5", "comment": "Black mirrors, contesting the center directly." },
    { "san": "Nf3", "comment": "Develop with a threat: the knight attacks the e5-pawn." },
    { "san": "Nc6", "comment": "Defend e5 and develop toward the center.",
      "alts": [
        [{ "san": "Nf6", "comment": "The Petrov Defense — Black counterattacks e4 instead of defending e5. A different opening entirely." }]
      ] },
    { "san": "Bc4", "comment": "The move that names the opening: the bishop eyes f7, the weakest square in Black's camp.",
      "alts": [
        [{ "san": "Bb5", "comment": "The Ruy Lopez — pinning pressure on the c6-knight instead." }]
      ] },
    { "san": "Bc5", "comment": "The Giuoco Piano ('quiet game'): Black mirrors, aiming the bishop at f2.",
      "alts": [
        [{ "san": "Nf6", "comment": "The Two Knights Defense — a sharper, more aggressive try that invites tactics." }]
      ] },
    { "san": "c3", "comment": "Prepare d4, building a big center. The modern main line often continues with slow maneuvering (the Giuoco Pianissimo)." },
    { "san": "Nf6", "comment": "Develop and pressure e4." },
    { "san": "d3", "comment": "The Giuoco Pianissimo: support e4 and keep the center closed for slow, strategic play." }
  ]
}
```

- [ ] **Step 2: Write the failing integrity test** `chess/tests/integrity.test.ts`

```ts
import { describe, it, expect } from "vitest";
import { loadStudies } from "../src/study";
import { normalize, validateLegality } from "../src/tree";

describe("study integrity", () => {
  const studies = loadStudies();

  it("discovers at least one study", () => {
    expect(studies.length).toBeGreaterThan(0);
  });

  it("every study id matches its own slug rule and is unique", () => {
    const ids = studies.map((s) => s.id);
    expect(new Set(ids).size).toBe(ids.length);
    for (const id of ids) expect(id).toMatch(/^[a-z0-9-]+$/);
  });

  it("every move in every study is legal", () => {
    for (const study of studies) {
      const errors = validateLegality(normalize(study));
      expect(errors, `${study.id}: ${errors.join("; ")}`).toEqual([]);
    }
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd chess && npx vitest run tests/integrity.test.ts`
Expected: FAIL (`loadStudies` is not exported).

- [ ] **Step 4: Add `loadStudies` to `chess/src/study.ts`**

Append to `chess/src/study.ts`:
```ts
// Eagerly import every study JSON at build time. Vite returns the parsed
// object as each module's default export. Validated here so a malformed
// study fails fast (in tests and at build), never silently in the browser.
const modules = import.meta.glob<Study>("./studies/*.json", {
  eager: true,
  import: "default",
});

export function loadStudies(): Study[] {
  return Object.values(modules)
    .map((m) => studySchema.parse(m))
    .sort((a, b) => a.name.localeCompare(b.name));
}
```

- [ ] **Step 5: Run test to verify it passes**

Run: `cd chess && npx vitest run tests/integrity.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 6: Run the full suite**

Run: `cd chess && npm test`
Expected: PASS (all tests from Tasks 1–4).

- [ ] **Step 7: Commit**

```bash
cd /Users/nick/Work/nicholastacik.github.io
git add chess/src/study.ts chess/src/studies/italian-game.json chess/tests/integrity.test.ts
git commit -m "feat(chess): glob-load studies with legality integrity test; add Italian Game"
```

---

### Task 5: Board wrapper (chessground) & piece-rendering verification

Wraps `@lichess-org/chessground` behind a tiny interface and confirms the board + pieces actually render. This task has an explicit empirical check because chessground's shipped CSS/piece assets are the one integration point that can vary by version.

**Files:**
- Create: `chess/src/board.ts`
- Modify: `chess/src/main.ts` (temporary smoke wiring, replaced in Task 7)

**Interfaces:**
- Consumes: `@lichess-org/chessground`.
- Produces:
  - `interface BoardHandle { setPosition(fen: string, lastMove: [string, string] | undefined, orientation: "white" | "black"): void }`
  - `function createBoard(el: HTMLElement, orientation: "white" | "black"): BoardHandle`

- [ ] **Step 1: Confirm the CSS asset filenames actually shipped**

Run: `cd chess && ls node_modules/@lichess-org/chessground/assets`
Expected: files including `chessground.base.css`, a board theme CSS (e.g. `chessground.brown.css`), and a piece-set CSS (e.g. `chessground.cburnett.css`). Note the exact names — use them verbatim in Step 2. If a name differs, substitute the actual filename.

- [ ] **Step 2: Implement `chess/src/board.ts`**

```ts
import { Chessground } from "@lichess-org/chessground";
import type { Api } from "@lichess-org/chessground/api";
// Board + piece styles shipped with chessground. If Step 1 showed different
// filenames, update these three imports to match.
import "@lichess-org/chessground/assets/chessground.base.css";
import "@lichess-org/chessground/assets/chessground.brown.css";
import "@lichess-org/chessground/assets/chessground.cburnett.css";

export interface BoardHandle {
  setPosition(
    fen: string,
    lastMove: [string, string] | undefined,
    orientation: "white" | "black",
  ): void;
}

export function createBoard(el: HTMLElement, orientation: "white" | "black"): BoardHandle {
  const cg: Api = Chessground(el, {
    viewOnly: true, // a study viewer: no dragging or move input
    coordinates: true,
    orientation,
  });
  return {
    setPosition(fen, lastMove, o) {
      cg.set({
        fen,
        orientation: o,
        // Passing undefined clears the previous highlight (e.g. at the root).
        lastMove: lastMove as never,
      });
    },
  };
}
```

- [ ] **Step 3: Temporary smoke wiring in `chess/src/main.ts`**

Replace `chess/src/main.ts` with:
```ts
import "./style.css";
import { createBoard } from "./board";

if (typeof document !== "undefined" && document.getElementById("app")) {
  const app = document.getElementById("app")!;
  const boardEl = document.createElement("div");
  boardEl.style.width = "384px";
  boardEl.style.height = "384px";
  app.appendChild(boardEl);
  const board = createBoard(boardEl, "white");
  // Show the position after 1.e4 to confirm pieces render.
  board.setPosition(
    "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
    ["e2", "e4"],
    "white",
  );
}
```

- [ ] **Step 4: Empirically verify the board and pieces render**

Run: `cd chess && npm run dev` (starts Vite; note the localhost URL), then open it in a browser.
Expected: a chessboard with the starting pieces except the white e-pawn on e4, e4/e2 highlighted, coordinates visible.
- If the board grid shows but **pieces are missing**, the piece-set CSS references sprite files not present in the package. Remedy: vendor the cburnett SVG pieces (12 files) into `chess/public/pieces/` from the chessground repo's `assets/pieces` (or lila's `public/piece/cburnett`), and add a small piece CSS in `board.ts`'s imports that maps `.cg-wrap piece.<role>.<color> { background-image: url(/pieces/<code>.svg) }` for the 12 pieces. Keep this only if needed.
Stop the dev server (Ctrl-C) when confirmed.

- [ ] **Step 5: Verify build still succeeds** (CSS imports must bundle)

Run: `cd chess && npm run build`
Expected: build succeeds; `posts/chess/app/` contains bundled CSS assets.

- [ ] **Step 6: Commit**

```bash
cd /Users/nick/Work/nicholastacik.github.io
git add chess/src/board.ts chess/src/main.ts
# If pieces had to be vendored:
# git add chess/public/pieces
git commit -m "feat(chess): chessground board wrapper with verified piece rendering"
```

---

### Task 6: Landing page & hash router

Renders the list of studies with a search filter, and routes between the landing page (`#/`) and a study (`#/study/<id>`).

**Files:**
- Create: `chess/src/ui.ts`
- Modify: `chess/src/main.ts` (real wiring)
- Modify: `chess/src/style.css` (landing styles)
- Create: `chess/tests/ui-landing.test.ts`

**Interfaces:**
- Consumes: from `study.ts` — `Study`, `loadStudies`; from `board.ts` — `BoardHandle`, `createBoard` (used by main, not this test).
- Produces (in `ui.ts`):
  - `function renderLanding(root: HTMLElement, studies: Study[], onOpen: (id: string) => void): void` — clears `root`, renders a search input (`.study-search`) and one `.study-card[data-id]` per study (showing name, and ECO/side when present). Typing in the search filters cards by name or ECO (case-insensitive substring). Clicking a card calls `onOpen(id)`.

- [ ] **Step 1: Write the failing test** `chess/tests/ui-landing.test.ts`

```ts
import { describe, it, expect, vi } from "vitest";
import { renderLanding } from "../src/ui";
import type { Study } from "../src/study";

const studies: Study[] = [
  { id: "italian-game", name: "Italian Game", eco: "C50", side: "white", intro: "i", line: [{ san: "e4" }] },
  { id: "french-defense", name: "French Defense", eco: "C00", side: "black", intro: "i", line: [{ san: "e4" }] },
];

function mount(): HTMLElement {
  const root = document.createElement("div");
  document.body.appendChild(root);
  return root;
}

describe("renderLanding", () => {
  it("renders one card per study", () => {
    const root = mount();
    renderLanding(root, studies, () => {});
    expect(root.querySelectorAll(".study-card").length).toBe(2);
  });

  it("filters cards by the search box (name or eco)", () => {
    const root = mount();
    renderLanding(root, studies, () => {});
    const search = root.querySelector<HTMLInputElement>(".study-search")!;
    search.value = "french";
    search.dispatchEvent(new Event("input"));
    const visible = [...root.querySelectorAll<HTMLElement>(".study-card")].filter(
      (c) => c.style.display !== "none",
    );
    expect(visible.length).toBe(1);
    expect(visible[0]!.dataset.id).toBe("french-defense");
  });

  it("calls onOpen with the study id when a card is clicked", () => {
    const root = mount();
    const onOpen = vi.fn();
    renderLanding(root, studies, onOpen);
    root.querySelector<HTMLElement>('.study-card[data-id="italian-game"]')!.click();
    expect(onOpen).toHaveBeenCalledWith("italian-game");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chess && npx vitest run tests/ui-landing.test.ts`
Expected: FAIL (cannot import `renderLanding`).

- [ ] **Step 3: Implement `renderLanding` in `chess/src/ui.ts`**

```ts
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chess && npx vitest run tests/ui-landing.test.ts`
Expected: PASS (3 tests).

- [ ] **Step 5: Wire the router in `chess/src/main.ts`**

Replace `chess/src/main.ts` with:
```ts
import "./style.css";
import { loadStudies } from "./study";
import { renderLanding, renderStudyView } from "./ui";
import { createBoard } from "./board";

if (typeof document !== "undefined" && document.getElementById("app")) {
  const app = document.getElementById("app")!;
  const studies = loadStudies();

  function route(): void {
    const hash = location.hash.replace(/^#/, "") || "/";
    if (hash.startsWith("/study/")) {
      const id = decodeURIComponent(hash.slice("/study/".length));
      const study = studies.find((s) => s.id === id);
      if (study) {
        renderStudyView(app, study, {
          makeBoard: (el, orientation) => createBoard(el, orientation),
        });
        return;
      }
    }
    renderLanding(app, studies, (id) => {
      location.hash = `#/study/${encodeURIComponent(id)}`;
    });
  }

  window.addEventListener("hashchange", route);
  route();
}
```

Note: `renderStudyView` and its `makeBoard` dep are defined in Task 7. Until then, `tsc --noEmit` will error on the missing export — that's expected; do NOT run `npm run build` at this step. The landing test (Step 4) does not import `main.ts`, so it passes independently.

- [ ] **Step 6: Add landing styles to `chess/src/style.css`**

Append:
```css
.landing-header { padding: 1.5rem 1rem 0.5rem; max-width: 720px; margin: 0 auto; }
.landing-header h1 { margin: 0 0 0.25rem; }
.landing-header p { margin: 0; color: #555; }
.study-search { display: block; width: calc(100% - 2rem); max-width: 720px; margin: 1rem auto; padding: 0.6rem 0.8rem; font-size: 1rem; box-sizing: border-box; }
.study-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(220px, 1fr)); gap: 0.75rem; max-width: 720px; margin: 0 auto 2rem; padding: 0 1rem; }
.study-card { display: flex; flex-direction: column; gap: 0.25rem; text-align: left; padding: 0.9rem 1rem; border: 1px solid #ddd; border-radius: 8px; background: #fff; cursor: pointer; font: inherit; }
.study-card:hover { border-color: #888; }
.study-card-name { font-weight: 600; }
.study-card-meta { color: #777; font-size: 0.85rem; text-transform: capitalize; }
```

- [ ] **Step 7: Commit**

```bash
cd /Users/nick/Work/nicholastacik.github.io
git add chess/src/ui.ts chess/src/main.ts chess/src/style.css chess/tests/ui-landing.test.ts
git commit -m "feat(chess): landing page with study search and hash router"
```

---

### Task 7: Study view — board, variation tree, annotations, controls

Renders the interactive study: board on the left, clickable variation tree, annotation panel, and prev/next controls with keyboard support. The board is injected via a factory so the view's logic is testable under jsdom with a fake board.

**Files:**
- Modify: `chess/src/ui.ts` (add `renderStudyView`, `StudyViewDeps`)
- Modify: `chess/src/style.css` (study-view layout)
- Create: `chess/tests/ui-study.test.ts`

**Interfaces:**
- Consumes: from `study.ts` — `Study`; from `board.ts` — `BoardHandle`; from `tree.ts` — `normalize`, `positionAt`, `stepForward`, `stepBack`, `siblings`, `switchSibling`, `TreeNode`, `Path`.
- Produces (in `ui.ts`):
  - `interface StudyViewDeps { makeBoard: (el: HTMLElement, orientation: "white" | "black") => BoardHandle }`
  - `function renderStudyView(root: HTMLElement, study: Study, deps: StudyViewDeps): void`
  - Rendered structure the test relies on: a `.board` element (passed to `makeBoard`); a `.variation-tree` containing one `.move[data-path]` per non-root node (clicking sets the current position); an `.annotation` element (shows the current node's comment, or the study `intro` at the root); a `.controls` region with `.btn-prev`, `.btn-next`, `.btn-flip`; the currently-selected move carries the `.current` class. Left/Right arrow keys step the mainline; Up/Down switch among sibling variations.

- [ ] **Step 1: Write the failing test** `chess/tests/ui-study.test.ts`

```ts
import { describe, it, expect } from "vitest";
import { renderStudyView, type BoardHandle } from "../src/ui";
import type { Study } from "../src/study";

const study: Study = {
  id: "t",
  name: "T",
  side: "white",
  intro: "INTRO TEXT",
  line: [
    { san: "e4", comment: "first move" },
    { san: "e5", comment: "reply" },
    { san: "Nf3", comment: "mainline", alts: [[{ san: "Bc4", comment: "alt line" }]] },
  ],
};

interface Recorded { fen: string; lastMove?: [string, string]; orientation: string }

function fakeBoardFactory() {
  const calls: Recorded[] = [];
  const make = (_el: HTMLElement, orientation: "white" | "black"): BoardHandle => ({
    setPosition(fen, lastMove, o) {
      calls.push({ fen, lastMove, orientation: o });
    },
  });
  return { make, calls };
}

function mount(): HTMLElement {
  const root = document.createElement("div");
  document.body.appendChild(root);
  return root;
}

describe("renderStudyView", () => {
  it("starts at the root: shows the intro and the start position", () => {
    const root = mount();
    const fb = fakeBoardFactory();
    renderStudyView(root, study, { makeBoard: fb.make });
    expect(root.querySelector(".annotation")!.textContent).toContain("INTRO TEXT");
    const last = fb.calls[fb.calls.length - 1]!;
    expect(last.fen.split(" ")[0]).toBe("rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR");
  });

  it("Next advances the mainline and updates the annotation + board", () => {
    const root = mount();
    const fb = fakeBoardFactory();
    renderStudyView(root, study, { makeBoard: fb.make });
    root.querySelector<HTMLElement>(".btn-next")!.click();
    expect(root.querySelector(".annotation")!.textContent).toContain("first move");
    const last = fb.calls[fb.calls.length - 1]!;
    expect(last.lastMove).toEqual(["e2", "e4"]);
  });

  it("clicking a variation move jumps the board to that line", () => {
    const root = mount();
    const fb = fakeBoardFactory();
    renderStudyView(root, study, { makeBoard: fb.make });
    // Find the alt move Bc4 and click it.
    const moves = [...root.querySelectorAll<HTMLElement>(".variation-tree .move")];
    const bc4 = moves.find((m) => m.textContent!.includes("Bc4"))!;
    bc4.click();
    expect(root.querySelector(".annotation")!.textContent).toContain("alt line");
    const last = fb.calls[fb.calls.length - 1]!;
    expect(last.lastMove).toEqual(["f1", "c4"]);
    expect(bc4.classList.contains("current")).toBe(true);
  });

  it("defaults orientation to black for a black-side study", () => {
    const root = mount();
    const fb = fakeBoardFactory();
    renderStudyView(root, { ...study, side: "black" }, { makeBoard: fb.make });
    expect(fb.calls[fb.calls.length - 1]!.orientation).toBe("black");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd chess && npx vitest run tests/ui-study.test.ts`
Expected: FAIL (`renderStudyView` / `BoardHandle` not exported from `ui.ts`).

- [ ] **Step 3: Implement `renderStudyView` in `chess/src/ui.ts`**

Add these imports at the top of `chess/src/ui.ts`:
```ts
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
```

Add near the top of `chess/src/ui.ts` (re-export the board interface so views and tests share one type):
```ts
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
```

Note: update `chess/src/board.ts` to import and use this shared `BoardHandle` from `./ui` instead of declaring its own, so there is exactly one definition. (Change `board.ts`'s local `export interface BoardHandle {...}` to `import type { BoardHandle } from "./ui";`.)

Append the view implementation to `chess/src/ui.ts`:
```ts
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
  // Map each rendered .move element to the full Path that selects it, so a
  // click can jump straight there without re-deriving the path.
  function buildTree(): void {
    treeEl.innerHTML = "";
    const currentNode = path[path.length - 1]!;

    function renderNode(node: TreeNode, nodePath: Path, ply: number): void {
      const span = document.createElement("span");
      span.className = "move";
      if (node === currentNode) span.classList.add("current");
      span.dataset.path = String(ply);
      span.textContent = moveNumberLabel(ply, node.san as string);
      span.addEventListener("click", () => {
        path = nodePath;
        render();
      });
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

  function render(): void {
    const current = path[path.length - 1]!;
    const pos = positionAt(path);
    board.setPosition(pos.fen, pos.lastMove, orientation);
    annotation.textContent = current.comment ?? (path.length === 1 ? study.intro : "");
    prevBtn.disabled = path.length <= 1;
    nextBtn.disabled = current.children.length === 0;
    buildTree();
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

  render();
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd chess && npx vitest run tests/ui-study.test.ts`
Expected: PASS (4 tests).

- [ ] **Step 5: Update `chess/src/board.ts` to use the shared `BoardHandle`**

Change the top of `chess/src/board.ts`: remove its local `export interface BoardHandle {...}` and instead add `import type { BoardHandle } from "./ui";`. Keep `createBoard` returning that type.

- [ ] **Step 6: Add study-view styles to `chess/src/style.css`**

Append:
```css
.study-view { display: grid; grid-template-columns: minmax(280px, 480px) 1fr; gap: 1.25rem; align-items: start; max-width: 960px; margin: 0 auto; padding: 1rem; }
.study-view .back-link { grid-column: 1 / -1; text-decoration: none; color: #555; }
.study-view .study-title { grid-column: 1 / -1; margin: 0.25rem 0; }
.study-view .board { width: 100%; aspect-ratio: 1 / 1; }
.study-side { display: flex; flex-direction: column; gap: 1rem; }
.annotation { min-height: 3.5rem; line-height: 1.5; }
.controls { display: flex; gap: 0.5rem; }
.controls button { padding: 0.4rem 0.8rem; font: inherit; cursor: pointer; }
.controls button:disabled { opacity: 0.4; cursor: default; }
.variation-tree { line-height: 1.9; }
.variation-tree .move { cursor: pointer; padding: 0 0.15rem; border-radius: 3px; }
.variation-tree .move:hover { background: #eee; }
.variation-tree .move.current { background: #1a73e8; color: #fff; }
.variation-tree .variation { color: #777; }
@media (max-width: 700px) { .study-view { grid-template-columns: 1fr; } }
```

- [ ] **Step 7: Run the full suite and build**

Run: `cd chess && npm test && npm run build`
Expected: all tests PASS; build succeeds (now that `renderStudyView` exists, `tsc --noEmit` is clean).

- [ ] **Step 8: Manually verify the whole app end-to-end**

Run: `cd chess && npm run dev`, open the URL, confirm: landing lists the Italian Game; clicking it opens the study; Next/Prev and arrow keys walk the moves; clicking a variation (e.g. the Petrov/Ruy alternatives) jumps the board; Flip works; the browser Back button returns to the landing page. Stop the server when done.

- [ ] **Step 9: Commit**

```bash
cd /Users/nick/Work/nicholastacik.github.io
git add chess/src/ui.ts chess/src/board.ts chess/src/style.css chess/tests/ui-study.test.ts
git commit -m "feat(chess): interactive study view with variation tree and keyboard nav"
```

---

### Task 8: The "add an opening" Claude skill

Creates a project skill that drafts a new opening study, validates it via the test suite, and builds. This is a documentation/instructions deliverable — no app code.

**Files:**
- Create: `.claude/skills/chess-opening/SKILL.md`

**Interfaces:**
- Consumes: the study JSON format from Task 2, the file location rule from Global Constraints, and the `npm test` / `npm run build` gates from Tasks 1–7.
- Produces: a skill invocable as `/chess-opening` (project scope), alongside the existing `.claude/skills/cryptic-crossword/`.

- [ ] **Step 1: Create `.claude/skills/chess-opening/SKILL.md`**

```markdown
---
name: chess-opening
description: Add a new chess opening to the Chess Openings Explorer (the Vite app in chess/). Use when the user wants to add, create, or draft an opening / variation study for the interactive openings page — e.g. "add the Sicilian Najdorf", "create a French Defense study", "add an opening to the chess explorer". Drafts the move tree and annotations from opening theory, writes a validated study JSON, and rebuilds.
---

# Add a Chess Opening

Draft a new opening as a self-contained study for the Chess Openings Explorer
(the Vite/TS app in `chess/`). Each study is one JSON file of moves + prose;
the app replays the moves to render positions, and the test suite enforces that
every move is legal.

## Inputs

Ask the user for (or take from their request):
- The opening **name** (e.g. "Sicilian Najdorf").
- Optional **focus**: which side's repertoire (White/Black/both), and how deep
  (main lines only, or key sidelines too). Default: the mainline plus 1–2 of the
  most important variations, ~8–12 plies deep.

## Steps

1. **Choose an id.** Slugify the name to match `^[a-z0-9-]+$` (e.g.
   `sicilian-najdorf`). The file MUST be `chess/src/studies/<id>.json`.

2. **Draft the study** from your own opening knowledge. Produce this exact JSON
   shape:

   ```json
   {
     "id": "sicilian-najdorf",
     "name": "Sicilian Najdorf",
     "eco": "B90",
     "side": "black",
     "intro": "2–4 sentences: the ideas, pawn structure, and what each side wants.",
     "line": [
       { "san": "e4", "comment": "Explain the move's purpose." },
       { "san": "c5" },
       { "san": "Nf3", "comment": "…",
         "alts": [
           [ { "san": "Nc3", "comment": "A different move order or system." } ]
         ] }
     ]
   }
   ```

   Rules:
   - `line` is the mainline: an array of move nodes played in sequence.
   - A node is `{ san, comment?, nag?, alts? }`. `alts` is a list of alternative
     *lines* branching at that node's ply — each alt is itself an array of nodes
     (a continuation). Use alts for the important divergences a learner should
     see, not every sideline.
   - `side` sets the default board orientation: use `"black"` for Black
     repertoires so the board starts from Black's view.
   - Write `comment` as short, concrete teaching notes ("controls d5", "prepares
     …", "the point of the whole system"). Not every node needs a comment;
     annotate the instructive ones.
   - **SAN dialect** (must match `chess.js`): castling `O-O` / `O-O-O` (letter O,
     not zero), promotion `e8=Q`, captures `exd5` / `Nxe5`, disambiguation
     `Nbd2`, check `+`, mate `#`. Do NOT include move numbers inside `san`.

3. **Write the file** to `chess/src/studies/<id>.json`.

4. **Validate — this is the gate.** Run:
   ```bash
   cd chess && npm test
   ```
   The integrity test replays every move with `chess.js`. If it reports an
   illegal move (e.g. "Illegal move Nf3 after e4 e5"), you made a theory or SAN
   error — fix the offending move(s) in the JSON and re-run until the suite is
   green. Never ship a study that fails the suite.

5. **Build:**
   ```bash
   cd chess && npm run build
   ```

6. **Report to the user** with this caveat, verbatim in spirit:
   > The moves are machine-verified as legal, but the *opening theory and the
   > choice of lines are my draft* — please review the variations and the prose
   > for accuracy before relying on them.

   Show the user the study id and the lines you included so they can spot-check.

## Notes

- No manifest to update — studies are auto-discovered via `import.meta.glob`.
- Keep studies focused: one opening/family per file. Shared early moves being
  duplicated across studies is fine and expected.
- Do not modify app code (`src/*.ts`) — this skill only adds a study JSON.
```

- [ ] **Step 2: Verify the skill is discoverable and the flow works**

Run: `cd chess && npm test` (sanity: suite is green before using the skill).
Then, as a dry run of the skill's own gate, temporarily add an intentionally illegal study and confirm `npm test` fails, then delete it:
```bash
cd /Users/nick/Work/nicholastacik.github.io/chess
printf '%s' '{"id":"bad-test","name":"Bad","side":"white","intro":"x","line":[{"san":"e4"},{"san":"e4"}]}' > src/studies/bad-test.json
npm test; echo "exit: $?"   # expected: integrity test FAILS (illegal second e4)
rm src/studies/bad-test.json
npm test                     # expected: PASS again
```

- [ ] **Step 3: Commit**

```bash
cd /Users/nick/Work/nicholastacik.github.io
git add .claude/skills/chess-opening/SKILL.md
git commit -m "feat(chess): add chess-opening skill to draft new opening studies"
```

---

### Task 9: Blog post & site build wiring

Adds the blog post that links to the app and wires the app's build output into the Quarto site so it publishes. Final end-to-end deliverable.

**Files:**
- Modify: `_quarto.yml` (add the app to `resources:`)
- Create: `posts/chess/index.qmd`
- Add (build output, committed): `posts/chess/app/**`

**Interfaces:**
- Consumes: the built app at `posts/chess/app/` (from `npm run build`), the site's existing Quarto/GitHub-Pages pipeline.
- Produces: a published post at `/posts/chess/` linking into `/posts/chess/app/`.

- [ ] **Step 1: Add the app to `_quarto.yml` resources**

In `_quarto.yml`, under `project.resources`, add the chess app alongside the existing entries:
```yaml
  resources:
    - "posts/jeopardy_ds/research/**"
    - "posts/montreal_events/events/**"
    - "posts/codenames/app/**"
    - "posts/chess/app/**"
```
(Keep the existing entries; add only the last line.)

- [ ] **Step 2: Create the blog post** `posts/chess/index.qmd`

```markdown
---
title: "Walking chess openings instead of reading them"
date: 2026-08-24
categories: [chess, interactive, AI]
---

I'm learning chess, and opening theory is usually written as a wall of move
notation — `1.e4 e5 2.Nf3 Nc6 3.Bc4 Bc5 4.c3 Nf6 5.d3`. I find that hard to
follow: I can't *see* the position, and the moment a line branches I lose the
thread.

So I built a small tool to **walk** openings instead of read them: a board, a
variation tree, and a short explanation at every move. Step forward and back
with the arrow keys, click any move in the tree to jump there, and follow
branches (the Petrov, the Ruy Lopez, the Two Knights) as first-class lines.

<p><a class="btn btn-primary" href="app/" target="_blank" rel="noopener">
Open the Chess Openings Explorer →</a></p>

## How it's built

It's a small Vite + TypeScript app. The interesting design decisions:

- **Studies are just moves and prose.** Each opening is one JSON file — the
  mainline, its variations, and a comment on the instructive moves. No board
  positions are stored.
- **The browser replays the moves.** Because the app already bundles
  [`chess.js`](https://github.com/jhlywa/chess.js), it replays a line's moves to
  derive each position on the fly, and renders it with Lichess's
  [chessground](https://github.com/lichess-org/chessground) board. That keeps the
  study files human-readable and skips a precompute step.
- **Legality is a test, not a runtime check.** A Vitest suite replays every move
  in every study and fails the build on anything illegal — so a broken line can
  never reach the page.
- **Adding an opening is a Claude skill.** I describe an opening ("add the
  Najdorf, from Black's side"), Claude drafts the move tree and annotations from
  opening theory into a new study file, the test suite verifies every move is
  legal, and it rebuilds. The theory is Claude's draft and I review it, but the
  moves are guaranteed to be real chess.

The variation tree turned out to be the crux. Openings are naturally a tree, but
they're *authored* most comfortably as a mainline with occasional
"…or you could play this" asides. So a study is written in that readable
line-plus-alternatives shape, then normalized once into a plain tree the UI can
walk and click.
```

- [ ] **Step 3: Build the app so the output exists to publish**

Run: `cd chess && npm run build`
Expected: `posts/chess/app/index.html` and bundled assets exist.

- [ ] **Step 4: Render the site locally to confirm it wires up** (if Quarto is installed)

Run: `cd /Users/nick/Work/nicholastacik.github.io && quarto render posts/chess/index.qmd`
Expected: renders without error; `_site/posts/chess/index.html` exists and the `app/` resource is copied. (If Quarto isn't installed locally, skip — the GitHub Action renders on push. Note this in the commit if skipped.)

- [ ] **Step 5: Commit**

```bash
cd /Users/nick/Work/nicholastacik.github.io
git add _quarto.yml posts/chess/index.qmd posts/chess/app
git commit -m "post: chess openings explorer — walk openings interactively"
```

- [ ] **Step 6: Final full verification**

Run: `cd chess && npm test && npm run build`
Expected: all tests PASS; build succeeds. The feature branch `chess-openings-explorer` now contains the app, the skill, and the post. Do not push or merge unless the user asks.

---

## Self-Review

**Spec coverage:**
- Guided step-through (board + Next/Prev + arrow keys) → Task 7. ✓
- Variation tree sidebar, click to jump → Task 7. ✓
- Per-move annotations + per-study intro → Task 7 (`annotation` fallback to `intro`). ✓
- Landing page listing studies with search → Task 6. ✓
- Self-contained study files, moves + prose only → Tasks 2, 4. ✓
- App replays SAN with chess.js at load → Task 3 (`replay`/`positionAt`). ✓
- chessground rendering, flip for black repertoires → Tasks 5, 7. ✓
- Claude skill to draft an opening (name it, Claude drafts) with legality gate + review caveat → Task 8. ✓
- Test suite: schema, study integrity (replay legality), tree navigation → Tasks 2, 3, 4 (+ UI tests 6, 7). ✓
- Blog post (why + how, link to app) → Task 9. ✓
- Build wiring: Vite outDir → `../posts/chess/app`, `_quarto.yml` resource → Tasks 1, 9. ✓
- Hash routing for shareable study URLs + Back button → Task 6. ✓
- Out of scope (drill mode, engine eval, PGN import, accounts, arrows UI) → not built; `shapes` reserved in schema (Task 2) with no UI, matching the spec. ✓

**Placeholder scan:** No TBD/TODO/"handle edge cases" left; every code step has concrete code. The one conditional (Task 5, Step 4 piece-rendering fallback) has a concrete remedy, not a vague instruction. ✓

**Type consistency:** `BoardHandle` is defined once in `ui.ts` and imported by `board.ts` (Task 7, Steps 3 & 5) — no duplicate/divergent definition. `Study`, `AuthoredNode`, `Shape` (Task 2) are consumed unchanged by `tree.ts` (Task 3) and `ui.ts` (Tasks 6, 7). `TreeNode`/`Path` and the nav functions (`normalize`, `positionAt`, `stepForward`, `stepBack`, `siblings`, `switchSibling`) are defined in Task 3 and used with matching signatures in Task 7. `loadStudies`/`studySchema` (Tasks 2, 4) used by `main.ts` (Task 6) and integrity test (Task 4). ✓
