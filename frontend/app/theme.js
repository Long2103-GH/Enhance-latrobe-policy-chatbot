/**
 * Ask La Trobe — theme manager.
 *
 * Manages the "light" | "dark" | "system" theme.
 * Applies the resolved theme to <html data-theme="..."> so CSS tokens react.
 * Responds to OS theme changes when theme === "system".
 */
(function () {
  'use strict';

  const Store = window.AskLTStore;
  const VALID_THEMES = ['light', 'dark', 'system'];

  /** @returns {'light'|'dark'} */
  function resolveTheme(preference) {
    if (preference === 'light' || preference === 'dark') return preference;
    // system
    if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
      return 'dark';
    }
    return 'light';
  }

  function applyTheme(preference) {
    const resolved = resolveTheme(preference);
    document.documentElement.setAttribute('data-theme', preference);
    document.documentElement.style.colorScheme = resolved;

    // Update meta theme-color so mobile browser chrome matches.
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) {
      meta.setAttribute('content', resolved === 'dark' ? '#1A1A1A' : '#E4002B');
    }

    // Emit an event for other modules that want to react.
    window.dispatchEvent(new CustomEvent('theme:changed', {
      detail: { preference, resolved },
    }));
  }

  /** Called by settings UI to change theme. */
  function setTheme(preference) {
    if (!VALID_THEMES.includes(preference)) return;
    // Store update triggers the subscriber below, which calls applyTheme.
    Store.setState({ theme: preference });
  }

  /** Called on boot + whenever store theme changes. */
  function syncFromStore() {
    applyTheme(Store.getState().theme);
  }

  // ─── React to OS theme changes when preference === "system" ─────────
  if (window.matchMedia) {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    const onChange = () => {
      if (Store.getState().theme === 'system') {
        applyTheme('system');
      }
    };
    // Modern + legacy API compatibility
    if (mq.addEventListener) mq.addEventListener('change', onChange);
    else if (mq.addListener) mq.addListener(onChange);
  }

  // ─── Subscribe to store changes ─────────────────────────────────────
  Store.subscribe((state) => {
    const current = document.documentElement.getAttribute('data-theme');
    if (state.theme !== current) applyTheme(state.theme);
  });

  // ─── Public API ─────────────────────────────────────────────────────
  window.AskLTTheme = Object.freeze({
    setTheme,
    syncFromStore,
    getTheme: () => Store.getState().theme,
    getResolvedTheme: () => resolveTheme(Store.getState().theme),
    VALID_THEMES: Object.freeze(VALID_THEMES.slice()),
  });

  // ─── Apply immediately at module load ───────────────────────────────
  // The initial `data-theme="light"` in index.html would otherwise cause
  // a flash of light theme for users whose stored preference is "dark"
  // (or "system" on a dark OS), until the next store notify arrives.
  syncFromStore();
})();