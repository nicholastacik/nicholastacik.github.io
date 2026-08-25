import { Chessground } from "@lichess-org/chessground";
import type { Api } from "@lichess-org/chessground/api";
// chessground ships its board + piece styles as these three CSS files (piece art is embedded as data URIs)
import "@lichess-org/chessground/assets/chessground.base.css";
import "@lichess-org/chessground/assets/chessground.brown.css";
import "@lichess-org/chessground/assets/chessground.cburnett.css";
import type { BoardHandle } from "./ui";

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
