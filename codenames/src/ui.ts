import type { Category, GameState, HistoryTurn } from "./types";
import { TOTAL_AGENTS } from "./types";

export interface UICallbacks {
  onClueSubmit(word: string, num: number): void;
  onCellClick(word: string): void;
  onEndGuessing(): void;
  onSaveKey(key: string, remember: boolean): void;
  onNewGame(): void;
  onRetry(): void;
}

const KEY_NAME = "openai_key";
const DEFAULT_MODEL = "gpt-5.6";

export function readSavedKey(): string {
  return sessionStorage.getItem(KEY_NAME) ?? "";
}

export function saveKey(key: string, remember: boolean): void {
  if (remember) sessionStorage.setItem(KEY_NAME, key);
  else sessionStorage.removeItem(KEY_NAME);
  // NOTE: never localStorage; never console.log(key)
}

// Build a word -> revealed category map from history, so covered cells can be
// shaded correctly regardless of whose keycard was in play when guessed.
function revealedCategories(state: GameState): Map<string, Category> {
  const map = new Map<string, Category>();
  for (const turn of state.history as HistoryTurn[]) {
    turn.guesses.forEach((word, i) => {
      const cat = turn.outcomes[i];
      if (cat) map.set(word, cat);
    });
  }
  return map;
}

export class GameUI {
  private root: HTMLElement;
  private cb: UICallbacks;

  private keyInput!: HTMLInputElement;
  private modelInput!: HTMLInputElement;
  private rememberInput!: HTMLInputElement;
  private gridEl!: HTMLElement;
  private clueBarEl!: HTMLElement;
  private clueWordInput!: HTMLInputElement;
  private clueNumInput!: HTMLInputElement;
  private endGuessingBtn!: HTMLButtonElement;
  private statusEl!: HTMLElement;
  private logEl!: HTMLElement;
  private errorEl!: HTMLElement;
  private errorMsgEl!: HTMLElement;
  private retryBtn!: HTMLButtonElement;

  constructor(root: HTMLElement, cb: UICallbacks) {
    this.root = root;
    this.cb = cb;
    this.buildSkeleton();
  }

  private buildSkeleton(): void {
    this.root.innerHTML = "";
    this.root.classList.add("cn-app");

    // Error banner
    this.errorEl = document.createElement("div");
    this.errorEl.className = "cn-error";
    this.errorEl.hidden = true;
    this.errorMsgEl = document.createElement("span");
    this.errorMsgEl.className = "cn-error-msg";
    this.retryBtn = document.createElement("button");
    this.retryBtn.type = "button";
    this.retryBtn.textContent = "Retry";
    this.retryBtn.className = "cn-retry";
    this.retryBtn.hidden = true;
    this.retryBtn.addEventListener("click", () => this.cb.onRetry());
    this.errorEl.appendChild(this.errorMsgEl);
    this.errorEl.appendChild(this.retryBtn);
    this.root.appendChild(this.errorEl);

    // Setup bar
    const setupBar = document.createElement("div");
    setupBar.className = "cn-setup";

    this.keyInput = document.createElement("input");
    this.keyInput.type = "password";
    this.keyInput.placeholder = "OpenAI API key (sk-...)";
    this.keyInput.className = "cn-key-input";
    this.keyInput.autocomplete = "off";
    this.keyInput.value = readSavedKey();

    this.modelInput = document.createElement("input");
    this.modelInput.type = "text";
    this.modelInput.className = "cn-model-input";
    this.modelInput.value = DEFAULT_MODEL;

    const rememberLabel = document.createElement("label");
    rememberLabel.className = "cn-remember-label";
    this.rememberInput = document.createElement("input");
    this.rememberInput.type = "checkbox";
    rememberLabel.appendChild(this.rememberInput);
    rememberLabel.appendChild(document.createTextNode(" Save key (session only)"));

    const saveKeyBtn = document.createElement("button");
    saveKeyBtn.type = "button";
    saveKeyBtn.textContent = "Save key";
    saveKeyBtn.addEventListener("click", () => {
      this.cb.onSaveKey(this.getKey(), this.rememberInput.checked);
    });

    const newGameBtn = document.createElement("button");
    newGameBtn.type = "button";
    newGameBtn.textContent = "New game";
    newGameBtn.className = "cn-new-game";
    newGameBtn.addEventListener("click", () => this.cb.onNewGame());

    setupBar.appendChild(this.keyInput);
    setupBar.appendChild(this.modelInput);
    setupBar.appendChild(rememberLabel);
    setupBar.appendChild(saveKeyBtn);
    setupBar.appendChild(newGameBtn);
    this.root.appendChild(setupBar);

    const note = document.createElement("p");
    note.className = "cn-note";
    note.textContent = "Your key stays in this browser and is sent directly to OpenAI (dangerouslyAllowBrowser).";
    this.root.appendChild(note);

    // Status line
    this.statusEl = document.createElement("div");
    this.statusEl.className = "cn-status";
    this.root.appendChild(this.statusEl);

    // Grid
    this.gridEl = document.createElement("div");
    this.gridEl.className = "cn-grid";
    this.root.appendChild(this.gridEl);

    // Clue bar
    this.clueBarEl = document.createElement("div");
    this.clueBarEl.className = "cn-clue-bar";
    this.clueWordInput = document.createElement("input");
    this.clueWordInput.type = "text";
    this.clueWordInput.placeholder = "Clue word";
    this.clueWordInput.className = "cn-clue-word";
    this.clueNumInput = document.createElement("input");
    this.clueNumInput.type = "number";
    this.clueNumInput.min = "0";
    this.clueNumInput.placeholder = "#";
    this.clueNumInput.className = "cn-clue-num";
    const clueSubmitBtn = document.createElement("button");
    clueSubmitBtn.type = "button";
    clueSubmitBtn.textContent = "Give clue";
    clueSubmitBtn.addEventListener("click", () => {
      const word = this.clueWordInput.value.trim();
      const num = Number(this.clueNumInput.value);
      if (!word || !Number.isFinite(num)) return;
      this.cb.onClueSubmit(word, num);
    });
    this.clueBarEl.appendChild(this.clueWordInput);
    this.clueBarEl.appendChild(this.clueNumInput);
    this.clueBarEl.appendChild(clueSubmitBtn);
    this.clueBarEl.hidden = true;
    this.root.appendChild(this.clueBarEl);

    // End guessing button
    this.endGuessingBtn = document.createElement("button");
    this.endGuessingBtn.type = "button";
    this.endGuessingBtn.textContent = "End guessing";
    this.endGuessingBtn.className = "cn-end-guessing";
    this.endGuessingBtn.hidden = true;
    this.endGuessingBtn.addEventListener("click", () => this.cb.onEndGuessing());
    this.root.appendChild(this.endGuessingBtn);

    // AI log panel
    const logPanel = document.createElement("div");
    logPanel.className = "cn-log-panel";
    const logTitle = document.createElement("h3");
    logTitle.textContent = "AI log";
    this.logEl = document.createElement("div");
    this.logEl.className = "cn-log";
    logPanel.appendChild(logTitle);
    logPanel.appendChild(this.logEl);
    this.root.appendChild(logPanel);
  }

  render(state: GameState): void {
    // Grid
    this.gridEl.innerHTML = "";
    const revealedCats = revealedCategories(state);
    const shadeKey = state.clueGiver === "human" ? state.keys.human : null;

    state.words.forEach((word, i) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.dataset.cell = "true";
      btn.textContent = word;
      btn.className = "cn-cell";

      const revealed = state.revealed[i];
      if (revealed) {
        btn.classList.add("revealed");
        const cat = revealedCats.get(word);
        if (cat) btn.classList.add(`cat-${cat}`);
        btn.disabled = true;
      } else if (shadeKey) {
        btn.classList.add(`shade-${shadeKey[i]}`);
      }

      btn.addEventListener("click", () => this.cb.onCellClick(word));
      this.gridEl.appendChild(btn);
    });

    // Clue bar visibility
    const showClueBar = state.phase === "awaitClue" && state.clueGiver === "human" && state.status === "playing";
    this.clueBarEl.hidden = !showClueBar;

    // End guessing visibility
    const showEndGuessing = state.phase === "awaitGuess" && state.clueGiver === "human" && state.status === "playing";
    this.endGuessingBtn.hidden = !showEndGuessing;

    // Status line
    this.statusEl.innerHTML = "";
    const parts: string[] = [];
    parts.push(`Turns remaining: ${state.turnsRemaining}`);
    parts.push(`Agents found: ${state.agentsFound}/${TOTAL_AGENTS}`);
    this.statusEl.appendChild(document.createTextNode(parts.join(" · ")));

    if (state.suddenDeath) {
      const badge = document.createElement("span");
      badge.className = "cn-badge cn-badge-sudden-death";
      badge.textContent = "SUDDEN DEATH";
      this.statusEl.appendChild(badge);
    }
    if (state.status === "won") {
      const badge = document.createElement("span");
      badge.className = "cn-badge cn-badge-won";
      badge.textContent = "YOU WIN";
      this.statusEl.appendChild(badge);
    } else if (state.status === "lost") {
      const badge = document.createElement("span");
      badge.className = "cn-badge cn-badge-lost";
      badge.textContent = "YOU LOSE";
      this.statusEl.appendChild(badge);
    }
  }

  log(line: string): void {
    const entry = document.createElement("div");
    entry.className = "cn-log-line";
    entry.textContent = line;
    this.logEl.appendChild(entry);
  }

  getModel(): string {
    return this.modelInput.value.trim() || DEFAULT_MODEL;
  }

  getKey(): string {
    return this.keyInput.value.trim();
  }

  setError(msg: string | null): void {
    if (msg === null) {
      this.errorEl.hidden = true;
      this.errorMsgEl.textContent = "";
      this.retryBtn.hidden = true;
    } else {
      this.errorEl.hidden = false;
      this.errorMsgEl.textContent = msg;
      this.retryBtn.hidden = false;
    }
  }
}
