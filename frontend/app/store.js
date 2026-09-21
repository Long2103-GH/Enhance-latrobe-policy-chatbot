/**
 * Ask La Trobe — application state store.
 *
 * Conversations live on the SERVER (user-scoped). The store holds only
 * an in-memory cache of conversation data. The active conversation ID
 * is persisted locally only so the UI can reopen the last selected
 * conversation after a page reload.
 *
 * Persisted keys (local only, no cross-user data):
 *   - token:           JWT
 *   - layout:          UI preference
 *   - theme:           UI preference
 *   - sidebarCollapsed: UI preference
 *   - activeConversationId: which conversation to reopen (user-scoped by server)
 */
(function () {
  'use strict';

  const CFG = window.ASK_LT_CONFIG;
  const KEYS = CFG.STORAGE_KEYS;

  function safeGet(key) {
    try { return window.localStorage.getItem(key); }
    catch (_) { return null; }
  }

  function safeSet(key, value) {
    try { window.localStorage.setItem(key, value); }
    catch (_) { /* quota / privacy mode — ignore */ }
  }

  function safeRemove(key) {
    try { window.localStorage.removeItem(key); }
    catch (_) { /* ignore */ }
  }

  function safeJSON(key, fallback) {
    const raw = safeGet(key);
    if (!raw) return fallback;
    try { return JSON.parse(raw); }
    catch (_) { return fallback; }
  }

  function persistKey(key, value) {
    if (key === undefined || key === null) return;
    if (value === null || value === undefined) {
      safeRemove(key);
    } else {
      safeSet(key, JSON.stringify(value));
    }
  }

  // ─── Initial state ──────────────────────────────────────────────────
  const initialState = {
    token: safeJSON(KEYS.TOKEN, null),
    user: null,
    authStatus: 'checking',

    layout: safeJSON(KEYS.LAYOUT, 'rail'),
    theme: safeJSON(KEYS.THEME, 'light'),
    sidebarCollapsed: safeJSON(KEYS.SIDEBAR_COLLAPSED, false),

    // Conversation list — fetched from backend, not localStorage
    conversations: [],
    activeConversationId: safeJSON(KEYS.ACTIVE_CONVERSATION, null),
    conversationsLoaded: false,

    messages: [],
    isSending: false,
    streamBuffer: '',
    error: null,

    isListening: false,

    settingsOpen: false,
    historyDrawerOpen: false,
  };

  const state = { ...initialState };
  const subscribers = new Set();

  function notify() {
    for (const fn of subscribers) {
      try { fn(state); } catch (err) { console.error('[store] subscriber error', err); }
    }
  }

  function persistSideEffects(patch) {
    if ('token' in patch) {
      if (patch.token) persistKey(KEYS.TOKEN, patch.token);
      else safeRemove(KEYS.TOKEN);
    }
    if ('layout' in patch) persistKey(KEYS.LAYOUT, patch.layout);
    if ('theme' in patch) persistKey(KEYS.THEME, patch.theme);
    if ('sidebarCollapsed' in patch) persistKey(KEYS.SIDEBAR_COLLAPSED, patch.sidebarCollapsed);
    if ('activeConversationId' in patch) {
      if (patch.activeConversationId) persistKey(KEYS.ACTIVE_CONVERSATION, patch.activeConversationId);
      else safeRemove(KEYS.ACTIVE_CONVERSATION);
    }
  }

  window.AskLTStore = Object.freeze({
    getState() { return state; },

    setState(patch) {
      let changed = false;
      for (const key of Object.keys(patch)) {
        if (state[key] !== patch[key]) {
          state[key] = patch[key];
          changed = true;
        }
      }
      if (!changed) return;
      persistSideEffects(patch);
      notify();
    },

    subscribe(fn) {
      subscribers.add(fn);
      return () => subscribers.delete(fn);
    },

    // ─── Session ─────────────────────────────────────────────────────
    setSession(token, user) {
      this.setState({ token, user, authStatus: token ? 'authenticated' : 'anonymous' });
    },

    clearSession() {
      this.setState({
        token: null,
        user: null,
        authStatus: 'anonymous',
        conversations: [],
        activeConversationId: null,
        conversationsLoaded: false,
        messages: [],
        streamBuffer: '',
        error: null,
      });
    },

    // ─── Conversation list (from backend) ────────────────────────────
    setConversations(list) {
      this.setState({ conversations: list || [], conversationsLoaded: true });
    },

    addConversationLocal(conv) {
      // Optimistic local insert when the backend created a new conversation.
      const existing = state.conversations.find((c) => c.id === conv.id);
      if (existing) return;
      this.setState({ conversations: [conv, ...state.conversations] });
    },

    updateConversationLocal(id, patch) {
      const conversations = state.conversations.map((c) =>
        c.id === id ? { ...c, ...patch } : c
      );
      this.setState({ conversations });
    },

    removeConversationLocal(id) {
      const conversations = state.conversations.filter((c) => c.id !== id);
      const wasActive = state.activeConversationId === id;
      this.setState({
        conversations,
        activeConversationId: wasActive ? null : state.activeConversationId,
        messages: wasActive ? [] : state.messages,
        streamBuffer: wasActive ? '' : state.streamBuffer,
        error: wasActive ? null : state.error,
      });
    },

    setActiveConversation(id, messages = []) {
      this.setState({
        activeConversationId: id,
        messages: messages.slice(),
        streamBuffer: '',
        error: null,
      });
    },

    startNewConversation() {
      this.setState({
        activeConversationId: null,
        messages: [],
        streamBuffer: '',
        error: null,
      });
    },

    toggleSidebar() {
      this.setState({ sidebarCollapsed: !state.sidebarCollapsed });
    },
  });
})();