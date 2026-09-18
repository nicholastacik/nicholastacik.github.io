import { Chess } from "chess.js";
import { Chessground } from "@lichess-org/chessground";
import type { Api } from "@lichess-org/chessground/api";
// chessground ships its board + piece styles as these three CSS files (piece art is embedded as data URIs)
import "@lichess-org/chessground/assets/chessground.base.css";
import "@lichess-org/chessground/assets/chessground.brown.css";
import "@lichess-org/chessground/assets/chessground.cburnett.css";
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
    destroy() {
      cg.destroy();
    },
  };
}

// A board the user can move pieces on, constrained to legal moves via `setMovable`.
// Promotion: if `onMove` receives a pawn reaching the last rank, the caller resolves
// promotion (default a queen for v1; a picker can be added later).
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
      cg.set({
        turnColor,
        movable: { free: false, dests: dests as never, showDests: true, color: turnColor },
      });
    },
    destroy() {
      cg.destroy();
    },
  };
}
