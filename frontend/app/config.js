/**
 * Ask La Trobe — environment configuration.
 *
 * Edit per environment. Never put secrets here.
 * Read-only after load; other modules consume `window.ASK_LT_CONFIG`.
 */
(function () {
  'use strict';

  /** @type {Readonly<AppConfig>} */
  window.ASK_LT_CONFIG = Object.freeze({
    // ─── API ─────────────────────────────────────────────────────────
    API_BASE_URL:
    window.location.hostname === 'localhost' ||
    window.location.hostname === '127.0.0.1'
      ? 'http://127.0.0.1:8000/api/v1'
      : '/api/v1',
    REQUEST_TIMEOUT_MS: 60000,

    // ─── Branding ────────────────────────────────────────────────────
    APP_NAME: 'Ask La Trobe',
    APP_TAGLINE: 'Policy, procedure and staff documentation',
    APP_ENV: 'development', // "development" | "staging" | "production"

    // ─── Behaviour ───────────────────────────────────────────────────
    MAX_CONVERSATION_TURNS: 8,
    STREAM_CHARS_PER_TICK: 2,
    STREAM_TICK_MS: 20,
    COPY_FEEDBACK_MS: 1400,

    // ─── Storage keys ────────────────────────────────────────────────
    STORAGE_KEYS: Object.freeze({
      TOKEN: 'ask_lt.token',
      LAYOUT: 'ask_lt.layout',
      THEME: 'ask_lt.theme',
      SIDEBAR_COLLAPSED: 'ask_lt.sidebar_collapsed',
      ACTIVE_CONVERSATION: 'ask_lt.active_conversation',
    }),

    // ─── Suggested prompts ───────────────────────────────────────────
    SUGGESTIONS: Object.freeze([
      { tag: 'Policy',    text: 'What are the grounds for approving a special consideration request?' },
      { tag: 'Procedure', text: 'Walk me through raising a purchase order for research equipment.' },
      { tag: 'HR',        text: 'How much personal leave can a continuing staff member accrue?' },
      { tag: 'IT',        text: 'A student can\'t access a Learning Portal subject site — what do I check first?' },
    ]),

    // ─── Feature flags ───────────────────────────────────────────────
    FEATURES: Object.freeze({
      MULTI_LAYOUT: true,     // allow switching between rail/reading/console
      DARK_MODE: true,
      VOICE_INPUT: true,
      SETTINGS_PANEL: true,
    }),

    // ─── User-facing messages ────────────────────────────────────────
    MESSAGES: Object.freeze({
      OFFLINE: 'The assistant could not be reached. Please check your connection and try again.',
      SESSION_EXPIRED: 'Your session expired. Please sign in again.',
      RATE_LIMITED: 'Too many requests. Please wait a moment and try again.',
      GENERIC_ERROR: 'Something went wrong. Please try again.',
      EMPTY_QUERY: 'Please enter a question before sending.',
      LOGIN_REQUIRED: 'Please sign in to continue.',
      NO_CITATIONS: 'No sources cited for this answer.',
    }),
  });
})();