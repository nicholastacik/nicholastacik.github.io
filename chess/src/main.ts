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
