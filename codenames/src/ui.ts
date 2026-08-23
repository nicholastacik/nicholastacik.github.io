import type { Category, GameState, HistoryTurn } from "./types";
import { TOTAL_AGENTS } from "./types";

export interface UICallbacks {
  onClueSubmit(word: string, num: number): void;
  onCellClick(word: string): void;
  onEndGuessing(): void;
  onGetClue(): void;
  onSaveKey(key: string, remember: boolean): void;
  onNewGame(): void;
  onRetry(): void;
  onLoadModels(): void;
}

const KEY_NAME = "openai_key";
const DEFAULT_MODEL = "gpt-5.6";
const CUSTOM_MODEL = "__custom__";

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
  private modelSelect!: HTMLSelectElement;
  private modelCustomInput!: HTMLInputElement;
  private rememberInput!: HTMLInputElement;
  private showKeyInput!: HTMLInputElement;
  private debugInput!: HTMLInputElement;
  private lastState: GameState | null = null;
  private gridEl!: HTMLElement;
  private clueBarEl!: HTMLElement;
  private clueWordInput!: HTMLInputElement;
  private clueNumInput!: HTMLInputElement;
  private endGuessingBtn!: HTMLButtonElement;
  private getClueBtn!: HTMLButtonElement;
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

  // Wipe the key from the input and from session storage. Closing the tab also
  // clears it, but this gives an explicit, immediate "it's gone" action.
  private clearKey(): void {
    this.keyInput.value = "";
    this.rememberInput.checked = false;
    saveKey("", false); // removes it from sessionStorage
  }

  // A visible, plain-language explanation of exactly what happens to the key,
  // plus a link to the source and the safest-usage tip. Built with textContent
  // (no innerHTML) to keep the page free of injection surface.
  // Collapsible "How to play" panel — the Duet rules as this game implements
  // them (incl. our simplifications). Default collapsed; built with textContent.
  private buildRulesPanel(): HTMLElement {
    const panel = document.createElement("details");
    panel.className = "cn-rules";

    const summary = document.createElement("summary");
    summary.textContent = "How to play";
    panel.appendChild(summary);

    const list = document.createElement("ul");
    const rules = [
      "You and the AI are partners (cooperative). Together, find all 15 agents before the 9-turn timer runs out.",
      "You each see a different key card. Turn on “Show my key card” to shade the board with yours: green = your agents, tan = bystanders, dark = assassins.",
      "Take turns: one partner gives a one-word clue + a number; the other clicks cells to guess.",
      "A guess is judged by the clue-giver’s card: green = agent found (keep guessing), bystander = turn ends, assassin = you both lose instantly.",
      "You may guess up to the clue’s number + 1 — that extra guess is meant for an agent left over from an earlier clue.",
      "Win: all 15 agents found. Lose: hit an assassin, or the 9-turn timer runs out with agents still hidden.",
    ];
    for (const text of rules) {
      const li = document.createElement("li");
      li.textContent = text;
      list.appendChild(li);
    }
    panel.appendChild(list);
    return panel;
  }

  private buildPrivacyPanel(): HTMLElement {
    const panel = document.createElement("details");
    panel.className = "cn-privacy";
    panel.open = true;

    const summary = document.createElement("summary");
    summary.textContent = "Your key & your privacy";
    panel.appendChild(summary);

    const list = document.createElement("ul");
    const bullets = [
      "Your key stays in your browser. It is sent only to OpenAI (api.openai.com) over HTTPS — never to this site, which has no server.",
      "It is not saved unless you tick “Save key”, and even then only for this browser tab (gone when you close it). It is never written to long-term storage and never logged.",
      "This page loads no third-party scripts — only its own code.",
    ];
    for (const text of bullets) {
      const li = document.createElement("li");
      li.textContent = text;
      list.appendChild(li);
    }

    // Open-source bullet with an inline link so the claims are verifiable.
    const sourceLi = document.createElement("li");
    sourceLi.appendChild(document.createTextNode("Don’t trust — verify: it’s open source. "));
    const link = document.createElement("a");
    link.href = "https://github.com/nicholastacik/nicholastacik.github.io/tree/main/codenames";
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "View the source";
    sourceLi.appendChild(link);
    sourceLi.appendChild(document.createTextNode(", or watch the Network tab: the key rides only on requests to api.openai.com."));
    list.appendChild(sourceLi);

    panel.appendChild(list);

    const tip = document.createElement("p");
    tip.className = "cn-privacy-tip";
    tip.textContent =
      "Tip: create a dedicated OpenAI key with a low spending limit for this, and revoke it when you’re done — then even a worst-case leak costs pennies.";
    panel.appendChild(tip);

    return panel;
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

    this.modelSelect = document.createElement("select");
    this.modelSelect.className = "cn-model-select";
    this.modelSelect.title = "Model";
    this.modelCustomInput = document.createElement("input");
    this.modelCustomInput.type = "text";
    this.modelCustomInput.className = "cn-model-custom";
    this.modelCustomInput.placeholder = "model id";
    this.modelCustomInput.hidden = true;
    this.setModels([]); // seed with the default + "Custom…"
    this.modelSelect.addEventListener("change", () => {
      this.modelCustomInput.hidden = this.modelSelect.value !== CUSTOM_MODEL;
    });

    const loadModelsBtn = document.createElement("button");
    loadModelsBtn.type = "button";
    loadModelsBtn.textContent = "Load my models";
    loadModelsBtn.className = "cn-load-models";
    loadModelsBtn.addEventListener("click", () => this.cb.onLoadModels());

    const rememberLabel = document.createElement("label");
    rememberLabel.className = "cn-remember-label";
    this.rememberInput = document.createElement("input");
    this.rememberInput.type = "checkbox";
    rememberLabel.appendChild(this.rememberInput);
    rememberLabel.appendChild(document.createTextNode(" Save key (session only)"));

    // Your OWN key card is always yours to see in Duet; show it during guessing
    // too (it correlates with the AI's clues). Toggle off to guess "blind".
    const showKeyLabel = document.createElement("label");
    showKeyLabel.className = "cn-remember-label";
    this.showKeyInput = document.createElement("input");
    this.showKeyInput.type = "checkbox";
    this.showKeyInput.className = "cn-showkey";
    this.showKeyInput.checked = true;
    this.showKeyInput.addEventListener("change", () => {
      if (this.lastState) this.render(this.lastState);
    });
    showKeyLabel.appendChild(this.showKeyInput);
    showKeyLabel.appendChild(document.createTextNode(" Show my key card (while guessing)"));

    // Debug: surface the AI's private intentions in the log (spoilers). Off by default.
    const debugLabel = document.createElement("label");
    debugLabel.className = "cn-remember-label";
    this.debugInput = document.createElement("input");
    this.debugInput.type = "checkbox";
    this.debugInput.className = "cn-debug";
    debugLabel.appendChild(this.debugInput);
    debugLabel.appendChild(document.createTextNode(" Debug (show AI intentions)"));

    const saveKeyBtn = document.createElement("button");
    saveKeyBtn.type = "button";
    saveKeyBtn.textContent = "Save key";
    saveKeyBtn.addEventListener("click", () => {
      this.cb.onSaveKey(this.getKey(), this.rememberInput.checked);
    });

    const clearKeyBtn = document.createElement("button");
    clearKeyBtn.type = "button";
    clearKeyBtn.textContent = "Clear key";
    clearKeyBtn.className = "cn-clear-key";
    clearKeyBtn.addEventListener("click", () => this.clearKey());

    const newGameBtn = document.createElement("button");
    newGameBtn.type = "button";
    newGameBtn.textContent = "New game";
    newGameBtn.className = "cn-new-game";
    newGameBtn.addEventListener("click", () => this.cb.onNewGame());

    setupBar.appendChild(this.keyInput);
    setupBar.appendChild(this.modelSelect);
    setupBar.appendChild(this.modelCustomInput);
    setupBar.appendChild(loadModelsBtn);
    setupBar.appendChild(rememberLabel);
    setupBar.appendChild(showKeyLabel);
    setupBar.appendChild(debugLabel);
    setupBar.appendChild(saveKeyBtn);
    setupBar.appendChild(clearKeyBtn);
    setupBar.appendChild(newGameBtn);
    this.root.appendChild(setupBar);

    this.root.appendChild(this.buildRulesPanel());
    this.root.appendChild(this.buildPrivacyPanel());

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

    // Shown on the AI's clue turn: the human explicitly requests the AI's clue.
    this.getClueBtn = document.createElement("button");
    this.getClueBtn.type = "button";
    this.getClueBtn.textContent = "Get the AI's clue";
    this.getClueBtn.className = "cn-get-clue";
    this.getClueBtn.hidden = true;
    this.getClueBtn.addEventListener("click", () => this.cb.onGetClue());
    this.root.appendChild(this.getClueBtn);

    // AI log panel
    const logPanel = document.createElement("div");
    logPanel.className = "cn-log-panel";
    const logTitle = document.createElement("h3");
    logTitle.textContent = "Game log";
    this.logEl = document.createElement("div");
    this.logEl.className = "cn-log";
    logPanel.appendChild(logTitle);
    logPanel.appendChild(this.logEl);
    this.root.appendChild(logPanel);
  }

  render(state: GameState): void {
    this.lastState = state; // remembered so the "show my key card" toggle can re-render
    // Grid
    this.gridEl.innerHTML = "";
    const revealedCats = revealedCategories(state);
    // Shade by the HUMAN's own key card only — never the AI's. Always shown while
    // the human gives a clue; while the human guesses, shown iff they opted in.
    const showOwnKey = state.clueGiver === "human" || this.showKeyInput.checked;
    const shadeKey = showOwnKey ? state.keys.human : null;

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

    // End guessing visibility — shown while YOU are guessing (the AI gave the
    // clue), so you can stop before spending all your guesses.
    const showEndGuessing = state.phase === "awaitGuess" && state.clueGiver === "ai" && state.status === "playing";
    this.endGuessingBtn.hidden = !showEndGuessing;

    // "Get the AI's clue" shows on the AI's clue turn (human triggers the fetch).
    const showGetClue = state.phase === "awaitClue" && state.clueGiver === "ai" && state.status === "playing";
    this.getClueBtn.hidden = !showGetClue;

    // Status line
    this.statusEl.innerHTML = "";
    const parts: string[] = [];
    parts.push(`Turns remaining: ${state.turnsRemaining}`);
    parts.push(`Agents found: ${state.agentsFound}/${TOTAL_AGENTS}`);
    this.statusEl.appendChild(document.createTextNode(parts.join(" · ")));

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
    // Keep the view pinned to the newest entry, but only if the user is already
    // at the bottom — so scrolling up to read history isn't yanked back down.
    const atBottom =
      this.logEl.scrollHeight - this.logEl.scrollTop - this.logEl.clientHeight < 4;
    const entry = document.createElement("div");
    entry.className = "cn-log-line";
    entry.textContent = line;
    this.logEl.appendChild(entry);
    if (atBottom) this.logEl.scrollTop = this.logEl.scrollHeight;
  }

  clearLog(): void {
    this.logEl.replaceChildren();
  }

  isDebug(): boolean {
    return this.debugInput.checked;
  }

  // Populate the model dropdown with the user's available models (from their
  // account), keeping a "Custom…" escape hatch. Preserves the current choice
  // when still available, else falls back to the default, else the first model.
  setModels(ids: string[]): void {
    const prev = this.getModel(); // preserve the current choice where possible
    const options = ids.length ? ids : [DEFAULT_MODEL];

    this.modelSelect.replaceChildren(); // clearing a select we own (no innerHTML)
    for (const id of options) {
      const opt = document.createElement("option");
      opt.value = id;
      opt.textContent = id;
      this.modelSelect.appendChild(opt);
    }
    const customOpt = document.createElement("option");
    customOpt.value = CUSTOM_MODEL;
    customOpt.textContent = "Custom…";
    this.modelSelect.appendChild(customOpt);

    if (options.includes(prev)) this.modelSelect.value = prev;
    else if (options.includes(DEFAULT_MODEL)) this.modelSelect.value = DEFAULT_MODEL;
    else this.modelSelect.value = options[0]!;
    this.modelCustomInput.hidden = this.modelSelect.value !== CUSTOM_MODEL;
  }

  getModel(): string {
    if (this.modelSelect.value === CUSTOM_MODEL) {
      return this.modelCustomInput.value.trim() || DEFAULT_MODEL;
    }
    return this.modelSelect.value || DEFAULT_MODEL;
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
