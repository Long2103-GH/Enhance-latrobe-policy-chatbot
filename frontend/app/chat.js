/**
 * Ask La Trobe — chat controller (server-side conversations).
 *
 * Responsibilities:
 *   - Send a query and, if continuing an existing conversation, send the id.
 *   - Adopt the conversation id the backend returns (new or existing).
 *   - Render the answer in a single pass (no simulated streaming).
 *   - Notify the view when a user message is sent and when an assistant
 *     message is committed, so the view can scroll to the right place.
 *
 * All queries — including greetings — go through the full RAG pipeline.
 * There are no hardcoded shortcut replies.
 */
(function () {
  'use strict';

  const CFG = window.ASK_LT_CONFIG;
  const Store = window.AskLTStore;
  const Api = window.AskLTApi;

  class ChatController {
    constructor({
      onRender,
      onConversationsChanged,
      onUserSent,
      onAssistantCommitted,
    }) {
      this.onRender = onRender;
      this.onConversationsChanged = onConversationsChanged || (() => {});
      this.onUserSent = onUserSent || null;
      this.onAssistantCommitted = onAssistantCommitted || null;
      this._abortController = null;
      this._requestId = 0;
    }

    // ─── Send ────────────────────────────────────────────────────────
    async send(query) {
      const state = Store.getState();
      if (state.isSending) return;

      const requestId = ++this._requestId;

      const q = (query || '').trim();
      if (!q) {
        Store.setState({ error: CFG.MESSAGES.EMPTY_QUERY });
        this.onRender();
        return;
      }

      // Build conversation history for the backend.
      const conversation = state.messages
        .slice(-CFG.MAX_CONVERSATION_TURNS)
        .map((m) => ({
          role: m.role === 'user' ? 'user' : 'assistant',
          content: m.text,
        }));

      const userMessage = { role: 'user', text: q };
      const messages = state.messages.concat([userMessage]);

      // Notify the view BEFORE the state change so the upcoming render
      // already knows where to scroll.
      if (typeof this.onUserSent === 'function') {
        this.onUserSent();
      }

      // Show the user's message immediately.
      Store.setState({
        messages,
        isSending: true,
        error: null,
      });
      this.onRender();

      
      try {
        this._abortController = new AbortController();

        const data = await Api.chat(
          state.token,
          {
            query: q,
            conversation,
            conversation_id: state.activeConversationId,
          },
          this._abortController.signal,
        );

        if (requestId !== this._requestId) return;
        this._abortController = null;

        const fullAnswer = data.answer || '';
        const citations = data.citations || [];
        const returnedConversationId = data.conversation_id;

        // If the backend created or moved us to a conversation, adopt its id.
        if (
          returnedConversationId &&
          returnedConversationId !== state.activeConversationId
        ) {
          Store.setState({ activeConversationId: returnedConversationId });

          const title = q.length > 42 ? q.slice(0, 42).trim() + '…' : q;

          Store.addConversationLocal({
            id: returnedConversationId,
            title,
            when: 'Today',
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            message_count: 2,
          });
        } else if (returnedConversationId) {
          Store.updateConversationLocal(returnedConversationId, {
            updated_at: new Date().toISOString(),
            message_count: state.messages.length + 2,
          });
        }

        this._commit(
          fullAnswer,
          citations,
          messages,
          returnedConversationId,
          requestId,
        );

        this.onConversationsChanged();
      } catch (err) {
        if (requestId !== this._requestId) return;

        if (
          err &&
          err.name === 'NetworkError' &&
          err.cause &&
          err.cause.name === 'AbortError'
        ) {
          return;
        }

        this._abortController = null;
        this._handleError(err);
      }
    }

    // ─── Commit finished answer ──────────────────────────────────────
    _commit(text, citations, priorMessages, activeId, requestId) {
      if (requestId !== this._requestId) return;

      const botMessage = {
        role: 'assistant',
        text,
        citations,
      };

      const messages = priorMessages.concat([botMessage]);


      // Notify the view BEFORE the state change so the upcoming render
      // already knows where to scroll.
      if (typeof this.onAssistantCommitted === 'function') {
        this.onAssistantCommitted();
      }



      Store.setState({
        messages,
        isSending: false,
        activeConversationId: activeId,
      });

      this.onRender();
    
    }

    // ─── Stop ────────────────────────────────────────────────────────
    stop() {
      this._requestId++;

      if (this._abortController) {
        this._abortController.abort();
        this._abortController = null;
      }

      Store.setState({ isSending: false });
      this.onRender();
    }

    // ─── Regenerate ──────────────────────────────────────────────────
    async retry(botIndex) {
      const state = Store.getState();
      if (state.isSending) return;

      const targetMessage = state.messages[botIndex];
      if (!targetMessage || targetMessage.role !== 'assistant') return;

      const priorUser = state.messages
        .slice(0, botIndex)
        .filter((m) => m.role === 'user')
        .pop();

      if (!priorUser) return;

      const requestId = ++this._requestId;

      Store.setState({
        error: null,
        isSending: true,
      });
      this.onRender();

      const conversation = state.messages
        .slice(0, botIndex)
        .filter((m) => m.role === 'user' || m.role === 'assistant')
        .slice(-CFG.MAX_CONVERSATION_TURNS)
        .map((m) => ({
          role: m.role === 'user' ? 'user' : 'assistant',
          content: m.text,
        }));

      try {
        this._abortController = new AbortController();

        const data = await Api.chat(
          state.token,
          {
            query: priorUser.text,
            conversation,
            conversation_id: state.activeConversationId,
          },
          this._abortController.signal,
        );

        if (requestId !== this._requestId) return;
        this._abortController = null;

        const fullAnswer = data.answer || '';
        const citations = data.citations || [];
        const priorMessages = state.messages;
        const activeId = state.activeConversationId;

        this._commit(
          fullAnswer,
          citations,
          priorMessages,
          activeId,
          requestId,
        );

        this.onConversationsChanged();
      } catch (err) {
        if (requestId !== this._requestId) return;

        if (
          err &&
          err.name === 'NetworkError' &&
          err.cause &&
          err.cause.name === 'AbortError'
        ) {
          return;
        }

        this._abortController = null;
        this._handleError(err);
      }
    }

    async copy(text) {
      try {
        await navigator.clipboard.writeText(text);
      } catch (_) {
        /* clipboard blocked — no-op */
      }
    }

    _handleError(err) {
      let message = CFG.MESSAGES.GENERIC_ERROR;

      if (err && err.name === 'UnauthorizedError') {
        message = CFG.MESSAGES.SESSION_EXPIRED;
        Store.clearSession();
      } else if (err && err.name === 'RateLimitedError') {
        message = `Too many requests. Please wait ${err.retryAfter} seconds and try again.`;
      } else if (err && err.name === 'NetworkError') {
        message = CFG.MESSAGES.OFFLINE;
      } else if (err && err.message) {
        message = err.message;
      }

      Store.setState({
        isSending: false,
        error: message,
      });

      this.onRender();
    }
  }

  window.AskLTChat = { ChatController };
})();