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
