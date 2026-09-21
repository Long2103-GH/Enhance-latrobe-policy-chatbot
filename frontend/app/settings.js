/**
 * Ask La Trobe — settings panel.
 *
 * Slides in from the right. Lets users pick layout, theme, and clear history.
 * Keyboard accessible; closes on Escape or backdrop click.
 */
(function () {
  'use strict';

  const Store = window.AskLTStore;
  const Theme = window.AskLTTheme;
  const CFG = window.ASK_LT_CONFIG;

  const LAYOUTS = [
    { id: 'rail',    label: 'Rail',          desc: 'Sidebar with conversation history. Best for everyday use.' },
    { id: 'reading', label: 'Reading room',  desc: 'Centred, editorial layout. Best for long answers.' },
    { id: 'console', label: 'Console',       desc: 'Compact developer-style view. Best for power users.' },
  ];

  const THEMES = [
    { id: 'light',  label: 'Light',  desc: 'Light surfaces, dark text.' },
    { id: 'dark',   label: 'Dark',   desc: 'Reduced contrast for long sessions.' },
    { id: 'system', label: 'System', desc: 'Follow your operating system setting.' },
  ];

  /** Builds the settings panel DOM. Returns { panel, backdrop }. */
  function build({ onClose, onClearHistory, onSignOut }) {
    const backdrop = document.createElement('div');
    backdrop.className = 'settings-backdrop';
    // Click handler wired by open() so the keydown listener is cleaned up.

    const panel = document.createElement('aside');
    panel.className = 'settings-panel';
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-label', 'Settings');
    panel.addEventListener('click', (e) => e.stopPropagation());

    // ─── Header ────────────────────────────────────────────────────
    const header = document.createElement('header');
    header.className = 'settings-panel__header';

    const title = document.createElement('span');
    title.className = 'settings-panel__title';
    title.textContent = 'Settings';
    header.appendChild(title);

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'settings-panel__close';
    closeBtn.setAttribute('aria-label', 'Close settings');
    closeBtn.textContent = '×';
    // Click handler wired by open() so the keydown listener is cleaned up.
    header.appendChild(closeBtn);

    panel.appendChild(header);

    // ─── Body ──────────────────────────────────────────────────────
    const body = document.createElement('div');
    body.className = 'settings-panel__body';

    // ── Layout section ─────────────────────────────────────────────
    if (CFG.FEATURES.MULTI_LAYOUT) {
      body.appendChild(buildRadioSection({
        title: 'Layout',
        options: LAYOUTS,
        getCurrent: () => Store.getState().layout,
        onChange: (id) => Store.setState({ layout: id }),
      }));
    }

    // ── Theme section ──────────────────────────────────────────────
    if (CFG.FEATURES.DARK_MODE) {
      body.appendChild(buildRadioSection({
        title: 'Theme',
        options: THEMES,
        getCurrent: () => Store.getState().theme,
        onChange: (id) => Theme.setTheme(id),
      }));
    }

    // ── Data section ───────────────────────────────────────────────
    const dataSection = document.createElement('div');
    dataSection.className = 'settings-section';
    const dataTitle = document.createElement('span');
    dataSection.appendChild(dataTitle);
    dataTitle.className = 'settings-section__title';
    dataTitle.textContent = 'Data';

    const clearBtn = document.createElement('button');
    clearBtn.type = 'button';
    clearBtn.className = 'btn btn--secondary btn--full';
    clearBtn.textContent = 'Clear conversation history';
    clearBtn.addEventListener('click', () => {
      if (confirm('Clear all conversation history? This cannot be undone.')) {
        onClearHistory && onClearHistory();
      }
    });
    dataSection.appendChild(clearBtn);
    body.appendChild(dataSection);

    // ── Account section ────────────────────────────────────────────
    const accountSection = document.createElement('div');
    accountSection.className = 'settings-section';

    const accountTitle = document.createElement('span');
    accountTitle.className = 'settings-section__title';
    accountTitle.textContent = 'Account';
    accountSection.appendChild(accountTitle);

    const signOutBtn = document.createElement('button');
    signOutBtn.type = 'button';
    signOutBtn.className = 'btn btn--danger btn--full';
    signOutBtn.textContent = 'Sign out';
    signOutBtn.addEventListener('click', () => {
      onSignOut && onSignOut();
    });
    accountSection.appendChild(signOutBtn);
    body.appendChild(accountSection);

    panel.appendChild(body);

    return { panel, backdrop };
  }

  /** Builds a section with a radio group. Returns the section element. */
  function buildRadioSection({ title, options, getCurrent, onChange }) {
    const section = document.createElement('div');
    section.className = 'settings-section';

    const titleEl = document.createElement('span');
    titleEl.className = 'settings-section__title';
    titleEl.textContent = title;
    section.appendChild(titleEl);

    const group = document.createElement('div');
    group.className = 'radio-group';

    const current = getCurrent();

    for (const opt of options) {
      const label = document.createElement('label');
      label.className = 'radio-option' + (opt.id === current ? ' radio-option--selected' : '');

      const input = document.createElement('input');
      input.type = 'radio';
      input.name = `settings-${title.toLowerCase()}`;
      input.className = 'radio-option__input';
      input.value = opt.id;
      input.checked = opt.id === current;
      input.addEventListener('change', () => {
        if (input.checked) onChange(opt.id);
      });
      label.appendChild(input);

      const content = document.createElement('div');
      content.className = 'radio-option__content';

      const lbl = document.createElement('span');
      lbl.className = 'radio-option__label';
      lbl.textContent = opt.label;
      content.appendChild(lbl);

      if (opt.desc) {
        const desc = document.createElement('span');
        desc.className = 'radio-option__desc';
        desc.textContent = opt.desc;
        content.appendChild(desc);
      }

      label.appendChild(content);
      group.appendChild(label);
    }

    section.appendChild(group);
    return section;
  }

  /** Opens the settings panel by mounting it into the app root. */
  function open(root, handlers) {
    const { panel, backdrop } = build(handlers);
    const container = document.createElement('div');
    container.className = 'settings-container';
    container.appendChild(backdrop);
    container.appendChild(panel);
    root.appendChild(container);

    // Escape key closes; listener is removed by close().
    function onKey(e) {
      if (e.key === 'Escape') close();
    }
    document.addEventListener('keydown', onKey);

    function close() {
      document.removeEventListener('keydown', onKey);
      container.remove();
      handlers.onClose && handlers.onClose();
    }

    // Wire the close button and backdrop to the internal close(),
    // not the caller-provided onClose — otherwise the keydown listener
    // above leaks every time the user dismisses via button or backdrop.
    const closeBtn = panel.querySelector('.settings-panel__close');
    if (closeBtn) closeBtn.addEventListener('click', close);
    backdrop.addEventListener('click', close);

    // Focus the first focusable element.
    const first = panel.querySelector('input, button');
    if (first) first.focus();

    return { close };
  }

  window.AskLTSettings = Object.freeze({ open });
})();