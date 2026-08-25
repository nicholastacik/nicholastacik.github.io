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
