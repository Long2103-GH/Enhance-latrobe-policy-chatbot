/**
 * Ask La Trobe — chat controller (server-side conversations).
 */
(function () {
  "use strict";

  const CFG = window.ASK_LT_CONFIG;
  const Store = window.AskLTStore;
  const Api = window.AskLTApi;
  const Shortcuts = window.AskLTShortcuts;

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
      this._streamTimer = null;
      this._abortController = null;
      this._requestId = 0;
    }

    async send(query) {
      const state = Store.getState();
      if (state.isSending) return;

      const requestId = ++this._requestId;

      const q = (query || "").trim();
      if (!q) {
        Store.setState({ error: CFG.MESSAGES.EMPTY_QUERY });
        return;
      }

      const shortcut = Shortcuts ? Shortcuts.match(q) : null;
      if (shortcut) {
        if (typeof this.onUserSent === "function") this.onUserSent();
        if (typeof this.onAssistantCommitted === "function")
          this.onAssistantCommitted();
        this._replyInstantly(q, shortcut);
        return;
      }

      const conversation = state.messages
        .slice(-CFG.MAX_CONVERSATION_TURNS)
        .map((m) => ({
          role: m.role === "user" ? "user" : "assistant",
          content: m.text,
        }));

      const userMessage = { role: "user", text: q };
      const messages = state.messages.concat([userMessage]);

      if (typeof this.onUserSent === "function") {
        this.onUserSent();
      }

      Store.setState({
        messages,
        isSending: true,
        streamBuffer: "",
        error: null,
      });

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

        const fullAnswer = data.answer || "";
        const citations = data.citations || [];
        const returnedConversationId = data.conversation_id;

        if (
          returnedConversationId &&
          returnedConversationId !== state.activeConversationId
        ) {
          Store.setState({ activeConversationId: returnedConversationId });

          const title = q.length > 42 ? q.slice(0, 42).trim() + "…" : q;

          Store.addConversationLocal({
            id: returnedConversationId,
            title,
            when: "Today",
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

        this._stream(
          fullAnswer,
          citations,
          messages,
          returnedConversationId,
          requestId,
        );

        this.onConversationsChanged();
      } catch (err) {
        if (requestId !== this._requestId) return;
        if (err?.name === "NetworkError" && err?.cause?.name === "AbortError") {
          return;
        }
        this._abortController = null;
        this._handleError(err);
      }
    }

    _replyInstantly(query, reply) {
      const state = Store.getState();
      const userMessage = { role: "user", text: query };
      const botMessage = {
        role: "assistant",
        text: reply,
        citations: [],
      };

      const messages = state.messages.concat([userMessage, botMessage]);

      if (typeof this.onAssistantCommitted === "function") {
        this.onAssistantCommitted();
      }

      Store.setState({
        messages,
        isSending: false,
        streamBuffer: "",
        error: null,
      });
    }

    _stream(fullText, citations, priorMessages, activeId, requestId) {
      const parts = fullText.split(/(\s+)/);
      let i = 0;

      clearInterval(this._streamTimer);

      const stride = CFG.STREAM_CHARS_PER_TICK;
      let timerId = null;

      timerId = setInterval(() => {
        if (requestId !== this._requestId) {
          clearInterval(timerId);
          if (this._streamTimer === timerId) this._streamTimer = null;
          return;
        }

        i += stride;

        if (i >= parts.length) {
          clearInterval(timerId);
          if (this._streamTimer === timerId) this._streamTimer = null;

          this._commit(fullText, citations, priorMessages, activeId, requestId);
        } else {
          Store.setState({
            streamBuffer: parts.slice(0, i).join(""),
          });
        }
      }, CFG.STREAM_TICK_MS);

      this._streamTimer = timerId;
    }

    _commit(text, citations, priorMessages, activeId, requestId) {
      if (requestId !== this._requestId) return;

      const botMessage = {
        role: "assistant",
        text,
        citations,
      };

      const messages = priorMessages.concat([botMessage]);

      if (typeof this.onAssistantCommitted === "function") {
        this.onAssistantCommitted();
      }

      Store.setState({
        messages,
        streamBuffer: "",
        isSending: false,
        activeConversationId: activeId,
      });
    }

    stop() {
      this._requestId++;
      clearInterval(this._streamTimer);
      this._streamTimer = null;

      if (this._abortController) {
        this._abortController.abort();
        this._abortController = null;
      }

      const state = Store.getState();
      const partial = state.streamBuffer;

      if (partial) {
        const botMessage = {
          role: "assistant",
          text: partial + " …[stopped]",
          citations: [],
        };

        const messages = state.messages.concat([botMessage]);

        if (typeof this.onAssistantCommitted === "function") {
          this.onAssistantCommitted();
        }

        Store.setState({
          messages,
          streamBuffer: "",
          isSending: false,
        });
      } else {
        Store.setState({ isSending: false });
      }
    }

    async retry(botIndex) {
      const state = Store.getState();
      if (state.isSending) return;

      const targetMessage = state.messages[botIndex];
      if (!targetMessage || targetMessage.role !== "assistant") return;

      const priorUser = state.messages
        .slice(0, botIndex)
        .filter((m) => m.role === "user")
        .pop();

      if (!priorUser) return;

      const requestId = ++this._requestId;

      clearInterval(this._streamTimer);
      this._streamTimer = null;

      Store.setState({
        error: null,
        isSending: true,
        streamBuffer: "",
      });

      const conversation = state.messages
        .slice(0, botIndex)
        .filter((m) => m.role === "user" || m.role === "assistant")
        .slice(-CFG.MAX_CONVERSATION_TURNS)
        .map((m) => ({
          role: m.role === "user" ? "user" : "assistant",
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

        const fullAnswer = data.answer || "";
        const citations = data.citations || [];
        const priorMessages = state.messages;
        const activeId = state.activeConversationId;

        this._stream(fullAnswer, citations, priorMessages, activeId, requestId);
        this.onConversationsChanged();
      } catch (err) {
        if (requestId !== this._requestId) return;
        if (err?.name === "NetworkError" && err?.cause?.name === "AbortError") {
          return;
        }
        this._abortController = null;
        this._handleError(err);
      }
    }

    async copy(text) {
      try {
        await navigator.clipboard.writeText(text);
      } catch {
        // ignore
      }
    }

    _handleError(err) {
      clearInterval(this._streamTimer);
      this._streamTimer = null;

      let message = CFG.MESSAGES.GENERIC_ERROR;

      if (err && err.name === "UnauthorizedError") {
        message = CFG.MESSAGES.SESSION_EXPIRED;
        Store.clearSession();
      } else if (err && err.name === "RateLimitedError") {
        message = `Too many requests. Please wait ${err.retryAfter} seconds and try again.`;
      } else if (err && err.name === "NetworkError") {
        message = CFG.MESSAGES.OFFLINE;
      } else if (err && err.message) {
        message = err.message;
      }

      Store.setState({
        isSending: false,
        streamBuffer: "",
        error: message,
      });
    }
  }

  window.AskLTChat = { ChatController };
})();
