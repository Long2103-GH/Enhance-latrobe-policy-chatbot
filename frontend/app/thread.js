/**
 * Ask La Trobe — chat thread renderer.
 *
 * Renders the message list as a DOM tree:
 *  - Empty state with greeting + suggestions
 *  - User and bot messages
 *  - Loading indicator ("Generating answer" + 3 dots)
 *  - Streaming cursor
 *  - Citations (styled cards only — no markdown duplicates)
 *  - Per-message actions (copy, regenerate) — both user and bot
 *  - Relative timestamps ("Today · 2:15 PM")
 */
(function () {
  'use strict';

  const MD = window.AskLTMarkdown;

  // ─── Relative time formatting ──────────────────────────────────────
  function formatRelativeTime(isoOrDate) {
    const d = isoOrDate instanceof Date ? isoOrDate : new Date(isoOrDate);
    if (isNaN(d.getTime())) return '';

    const now = new Date();
    const startOfDay = (dt) => new Date(dt.getFullYear(), dt.getMonth(), dt.getDate());
    const daysDiff = Math.round((startOfDay(now) - startOfDay(d)) / 86400000);

    const time = d.toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' });
    if (daysDiff === 0) return `Today · ${time}`;
    if (daysDiff === 1) return `Yesterday · ${time}`;
    if (daysDiff < 7) return `${daysDiff} days ago`;
    return d.toLocaleDateString([], { day: 'numeric', month: 'short' });
  }

  // ─── Empty state ───────────────────────────────────────────────────
  function buildEmptyState({ greeting, suggestions, onSuggestionClick }) {
    const wrap = document.createElement('div');
    wrap.className = 'thread__empty';

    const greetingBlock = document.createElement('div');
    greetingBlock.className = 'thread__greeting';

    const label = document.createElement('span');
    label.className = 'thread__greeting-label';
    label.textContent = 'Internal knowledge assistant';
    greetingBlock.appendChild(label);

    const text = document.createElement('h1');
    text.className = 'thread__greeting-text';
    text.textContent = greeting;
    greetingBlock.appendChild(text);

    const sub = document.createElement('p');
    sub.className = 'thread__greeting-sub';
    sub.textContent = 'Ask about policies, procedures and internal documentation. Answers are generated and should be confirmed against the source policy before you act on them.';
    greetingBlock.appendChild(sub);

    wrap.appendChild(greetingBlock);

    if (Array.isArray(suggestions) && suggestions.length > 0) {
      const grid = document.createElement('div');
      grid.className = 'suggestions';

      for (const s of suggestions) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'suggestion';
        btn.addEventListener('click', () => onSuggestionClick && onSuggestionClick(s.text));

        const tag = document.createElement('span');
        tag.className = 'suggestion__tag';
        tag.textContent = s.tag;
        btn.appendChild(tag);

        const textEl = document.createElement('span');
        textEl.className = 'suggestion__text';
        textEl.textContent = s.text;
        btn.appendChild(textEl);

        grid.appendChild(btn);
      }

      wrap.appendChild(grid);
    }

    return wrap;
  }

  // ─── User message ──────────────────────────────────────────────────
  function buildUserMessage(message, handlers) {
    const wrap = document.createElement('div');
    wrap.className = 'message message--user';

    const bubble = document.createElement('div');
    bubble.className = 'message__bubble';
    bubble.textContent = message.text;
    wrap.appendChild(bubble);

    const actions = document.createElement('div');
    actions.className = 'message__actions message__actions--user';

    const copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.className = 'message__action';
    copyBtn.textContent = message.copyLabel || 'Copy';
    copyBtn.addEventListener('click', () => handlers.onCopy && handlers.onCopy());
    actions.appendChild(copyBtn);

    if (message.timestamp) {
      const ts = document.createElement('span');
      ts.className = 'message__time';
      ts.textContent = formatRelativeTime(message.timestamp);
      actions.appendChild(ts);
    }

    wrap.appendChild(actions);

    return wrap;
  }

  // ─── Bot message ───────────────────────────────────────────────────
  function buildBotMessage(message, handlers) {
    const wrap = document.createElement('div');
    wrap.className = 'message message--bot';

    const row = document.createElement('div');
    row.className = 'message__row';

    const avatar = document.createElement('div');
    avatar.className = 'message__avatar';
    avatar.textContent = 'LT';
    row.appendChild(avatar);

    const body = document.createElement('div');
    body.className = 'message__body';

    // Loading state
    if (message.isLoading) {
      body.appendChild(buildLoadingIndicator());
      row.appendChild(body);
      wrap.appendChild(row);
      return wrap;
    }

    // Markdown content
    const md = document.createElement('div');
    md.className = 'md';
    MD.applyMarkdownToElement(md, message.text);
    body.appendChild(md);

    // Citations
    if (Array.isArray(message.citations) && message.citations.length > 0) {
      const cites = MD.buildCitationsElement(message.citations);
      if (cites) body.appendChild(cites);
    }

    // Actions
    const actions = document.createElement('div');
    actions.className = 'message__actions';

    const copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.className = 'message__action';
    copyBtn.textContent = message.copyLabel || 'Copy';
    copyBtn.addEventListener('click', () => handlers.onCopy && handlers.onCopy());
    actions.appendChild(copyBtn);

    const retryBtn = document.createElement('button');
    retryBtn.type = 'button';
    retryBtn.className = 'message__action';
    retryBtn.textContent = 'Regenerate';
    retryBtn.addEventListener('click', () => handlers.onRetry && handlers.onRetry());
    actions.appendChild(retryBtn);

    if (message.timestamp) {
      const ts = document.createElement('span');
      ts.className = 'message__time';
      ts.textContent = formatRelativeTime(message.timestamp);
      actions.appendChild(ts);
    }

    body.appendChild(actions);
    row.appendChild(body);
    wrap.appendChild(row);

    return wrap;
  }

  // ─── Loading indicator ─────────────────────────────────────────────
  function buildLoadingIndicator() {
    const el = document.createElement('div');
    el.className = 'loading-indicator';
    el.innerHTML = `
      <span class="loading-indicator__text">Generating answer</span>
      <span class="loading-indicator__dots" aria-hidden="true">
        <span class="loading-indicator__dot"></span>
        <span class="loading-indicator__dot"></span>
        <span class="loading-indicator__dot"></span>
      </span>
    `;
    return el;
  }

  // ─── Streaming message ─────────────────────────────────────────────
  function buildStreamingMessage(text) {
    const wrap = document.createElement('div');
    wrap.className = 'message message--bot';

    const row = document.createElement('div');
    row.className = 'message__row';

    const avatar = document.createElement('div');
    avatar.className = 'message__avatar';
    avatar.textContent = 'LT';
    row.appendChild(avatar);

    const body = document.createElement('div');
    body.className = 'message__body';

    const md = document.createElement('div');
    md.className = 'md';
    MD.applyMarkdownToElement(md, text);
    body.appendChild(md);

    const cursor = document.createElement('span');
    cursor.className = 'stream-cursor';
    body.appendChild(cursor);

    row.appendChild(body);
    wrap.appendChild(row);
    return wrap;
  }

  // ─── Error block ───────────────────────────────────────────────────
  function buildErrorMessage(text) {
    const el = document.createElement('div');
    el.className = 'alert';
    el.textContent = text;
    return el;
  }

  // ─── Main render ───────────────────────────────────────────────────
  function render(container, props) {
    container.innerHTML = '';

    const isEmpty = props.messages.length === 0 && !props.isStreaming;
    if (isEmpty) {
      container.appendChild(buildEmptyState({
        greeting: props.greeting,
        suggestions: props.suggestions,
        onSuggestionClick: props.handlers.onSuggestion,
      }));
      return;
    }

    for (let i = 0; i < props.messages.length; i++) {
      const m = props.messages[i];
      if (m.role === 'user') {
        container.appendChild(buildUserMessage(m, {
          onCopy: () => props.handlers.onCopy(m.text),
        }));
      } else {
        container.appendChild(buildBotMessage(m, {
          onCopy: () => props.handlers.onCopy(m.text),
          onRetry: () => props.handlers.onRetry(i),
        }));
      }
    }

    // Streaming: if we have buffer text, show it; otherwise show loading dots
    if (props.isStreaming) {
      if (props.streamText && props.streamText.length > 0) {
        container.appendChild(buildStreamingMessage(props.streamText));
      } else {
        const loadingMsg = { isLoading: true };
        container.appendChild(buildBotMessage(loadingMsg, {}));
      }
    }

    if (props.error) {
      container.appendChild(buildErrorMessage(props.error));
    }
  }

  window.AskLTThread = Object.freeze({
    render,
    formatRelativeTime,
  });
})();