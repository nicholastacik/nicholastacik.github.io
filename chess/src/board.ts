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
