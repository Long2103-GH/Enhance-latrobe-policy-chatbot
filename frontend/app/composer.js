/**
 * Ask La Trobe — composer (input + mic + send/stop button).
 * Managed as a class so state can persist across renders.
 */
(function () {
  "use strict";

  class Composer {
    constructor({ onSubmit, onStop, onMic }) {
      this.onSubmit = onSubmit;
      this.onStop = onStop;
      this.onMic = onMic;
      this.value = "";
      this.isBusy = false;
      this.isListening = false;
      this.hintText = "Answers are grounded in the La Trobe Policy Database.";
      this.el = this._build();
    }

    _build() {
      const wrap = document.createElement("div");
      wrap.className = "composer";

      const box = document.createElement("div");
      box.className = "composer__box";

      this.inputEl = document.createElement("textarea");
      this.inputEl.className = "composer__input";
      this.inputEl.rows = 1;
      this.inputEl.placeholder = "Ask about a policy, form or process…";
      this.inputEl.setAttribute("aria-label", "Ask a question");
      this.inputEl.addEventListener("input", () => this._onInput());
      this.inputEl.addEventListener("keydown", (e) => this._onKeyDown(e));
      box.appendChild(this.inputEl);

      const actions = document.createElement("div");
      actions.className = "composer__actions";

      this.micBtn = document.createElement("button");
      this.micBtn.type = "button";
      this.micBtn.className = "composer__mic";
      this.micBtn.title = "Voice input";
      this.micBtn.setAttribute("aria-label", "Voice input");
      this.micBtn.addEventListener("click", () => this.onMic && this.onMic());

      const micIcon = document.createElement("span");
      micIcon.className = "composer__mic-icon";
      this.micBtn.appendChild(micIcon);
      actions.appendChild(this.micBtn);

      this.sendBtn = document.createElement("button");
      this.sendBtn.type = "button";
      this.sendBtn.className = "btn btn--primary";
      this.sendBtn.textContent = "Send";
      this.sendBtn.addEventListener("click", () => this._submit());
      actions.appendChild(this.sendBtn);

      this.stopBtn = document.createElement("button");
      this.stopBtn.type = "button";
      this.stopBtn.className = "btn btn--secondary";
      this.stopBtn.textContent = "Stop";
      this.stopBtn.addEventListener(
        "click",
        () => this.onStop && this.onStop(),
      );
      this.stopBtn.style.display = "none";
      actions.appendChild(this.stopBtn);

      box.appendChild(actions);
      wrap.appendChild(box);

      const meta = document.createElement("div");
      meta.className = "composer__meta";

      this.hintEl = document.createElement("span");
      this.hintEl.textContent = this.hintText;
      meta.appendChild(this.hintEl);

      const shortcut = document.createElement("span");
      shortcut.textContent = "Enter to send · Shift+Enter for a new line";
      meta.appendChild(shortcut);

      wrap.appendChild(meta);

      return wrap;
    }

    _onInput() {
      this.value = this.inputEl.value;
      this._autoResize();
    }

    _autoResize() {
      this.inputEl.style.height = "auto";
      this.inputEl.style.height =
        Math.min(this.inputEl.scrollHeight, 150) + "px";
    }

    _onKeyDown(e) {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        this._submit();
      }
    }

    _submit() {
      const text = (this.value || "").trim();
      if (!text || this.isBusy) return;
      this.onSubmit && this.onSubmit(text);
    }

    /** Called by chat controller when a message is accepted. */
    clear() {
      this.value = "";
      this.inputEl.value = "";
      this._autoResize();
    }

    /** Called when a suggestion is clicked externally. */
    setValue(text) {
      this.value = text;
      this.inputEl.value = text;
      this.inputEl.focus();
      this._autoResize();
    }

    setBusy(isBusy) {
      this.isBusy = isBusy;
      this.sendBtn.style.display = isBusy ? "none" : "";
      this.stopBtn.style.display = isBusy ? "" : "none";
      this.inputEl.disabled = isBusy;
    }

    setListening(isListening) {
      this.isListening = isListening;
      this.micBtn.classList.toggle("composer__mic--listening", isListening);
      this.hintEl.textContent = isListening
        ? "Listening — speak now."
        : this.hintText;
    }

    focus() {
      this.inputEl.focus();
    }
  }

  window.AskLTComposer = { Composer };
})();
