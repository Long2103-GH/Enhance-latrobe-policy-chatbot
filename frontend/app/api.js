/**
 * Ask La Trobe — backend API client.
 *
 * Thin wrapper over fetch() with JWT handling, timeouts, and typed errors.
 * All backend communication goes through this module.
 */
(function () {
  'use strict';

  const CFG = window.ASK_LT_CONFIG;

  /** Typed error for API failures. */
  class ApiError extends Error {
    constructor(message, { status = 0, code = 'API_ERROR', requestId = null, cause = null } = {}) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
      this.code = code;
      this.requestId = requestId;
      this.cause = cause;
    }
  }

  /** Thrown when the session is invalid/expired — callers should redirect to login. */
  class UnauthorizedError extends ApiError {
    constructor(message, opts = {}) {
      super(message, { ...opts, status: 401, code: 'UNAUTHORIZED' });
      this.name = 'UnauthorizedError';
    }
  }

  class RateLimitedError extends ApiError {
    constructor(message, { retryAfter = 60, ...opts } = {}) {
      super(message, { ...opts, status: 429, code: 'RATE_LIMITED' });
      this.name = 'RateLimitedError';
      this.retryAfter = retryAfter;
    }
  }

  class NetworkError extends ApiError {
    constructor(message, cause = null) {
      super(message, { code: 'NETWORK_ERROR', cause });
      this.name = 'NetworkError';
    }
  }

  /** Wraps fetch with timeout + JSON parsing + error mapping. */
  async function request(path, { method = 'GET', body = null, token = null, signal = null } = {}) {
    const url = CFG.API_BASE_URL + path;

    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), CFG.REQUEST_TIMEOUT_MS);

    if (signal) {
      signal.addEventListener('abort', () => controller.abort(), { once: true });
    }

    const headers = { Accept: 'application/json' };
    if (body !== null) headers['Content-Type'] = 'application/json';
    if (token) headers['Authorization'] = `Bearer ${token}`;

    let response;
    try {
      response = await fetch(url, {
        method,
        headers,
        body: body !== null ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
    } catch (err) {
      clearTimeout(timeoutId);
      if (err && err.name === 'AbortError') {
        throw new NetworkError('The request timed out. Please try again.', err);
      }
      throw new NetworkError(CFG.MESSAGES.OFFLINE, err);
    } finally {
      clearTimeout(timeoutId);
    }

    const requestId = response.headers.get('X-Request-ID') || null;

    // Try to parse JSON regardless of status — backend returns structured errors.
    let payload = null;
    const contentType = response.headers.get('Content-Type') || '';
    if (contentType.includes('application/json')) {
      try {
        payload = await response.json();
      } catch (_) {
        payload = null;
      }
    }

    // 204 No Content — return null, nothing to parse.
    if (response.status === 204) return null;

    if (response.ok) {
      return payload;
    }

    // Map status codes to typed errors.
    const message =
      (payload && (payload.message || payload.error || payload.detail)) ||
      CFG.MESSAGES.GENERIC_ERROR;

    if (response.status === 401) {
      throw new UnauthorizedError(payload?.message || CFG.MESSAGES.SESSION_EXPIRED, { requestId });
    }

    if (response.status === 429) {
      const retryAfter = parseInt(response.headers.get('Retry-After') || '60', 10);
      throw new RateLimitedError(CFG.MESSAGES.RATE_LIMITED, { retryAfter, requestId });
    }

    throw new ApiError(message, {
      status: response.status,
      code: payload?.error || 'API_ERROR',
      requestId,
    });
  }

  window.AskLTApi = Object.freeze({
    ApiError,
    UnauthorizedError,
    RateLimitedError,
    NetworkError,

    /**
     * POST /auth/login
     * @returns {Promise<{access_token: string, token_type: string}>}
     */
    async login(email, password) {
      return request('/auth/login', {
        method: 'POST',
        body: { email, password },
      });
    },

    /**
     * GET /auth/me
     * @returns {Promise<{id: number, email: string, full_name: string, role: string}>}
     */
    async me(token) {
      return request('/auth/me', { token });
    },

    /**
     * POST /chat
     * @param {string} token
     * @param {{query: string, conversation: Array<{role: string, content: string}>, conversation_id: number|null}} payload
     * @returns {Promise<{answer, citations, grounded, confidence, escalation_required, disclaimer, request_id, conversation_id}>}
     */
    async chat(token, payload, signal = null) {
      return request('/chat', {
        method: 'POST',
        body: payload,
        token,
        signal,
      });
    },

    /**
     * GET /conversations — list current user's conversations.
     * @returns {Promise<{conversations: Array<{id,title,created_at,updated_at,message_count}>}>}
     */
    async listConversations(token) {
      return request('/conversations', { token });
    },

    /**
     * POST /conversations — create a new empty conversation.
     * @returns {Promise<{id,title,created_at,updated_at,message_count}>}
     */
    async createConversation(token, title = null) {
      return request('/conversations', {
        method: 'POST',
        body: { title },
        token,
      });
    },

    /**
     * GET /conversations/{id} — load full conversation with messages.
     * @returns {Promise<{id,title,created_at,updated_at,messages:Array}>}
     */
    async loadConversation(token, conversationId) {
      return request(`/conversations/${conversationId}`, { token });
    },

    /**
     * PATCH /conversations/{id} — rename a conversation.
     * @returns {Promise<{id,title,created_at,updated_at,message_count}>}
     */
    async renameConversation(token, conversationId, title) {
      return request(`/conversations/${conversationId}`, {
        method: 'PATCH',
        body: { title },
        token,
      });
    },

    /**
     * DELETE /conversations/{id}
     */
    async deleteConversation(token, conversationId) {
      return request(`/conversations/${conversationId}`, {
        method: 'DELETE',
        token,
      });
    },

    /**
     * GET /health
     */
    async health() {
      return request('/health');
    },
  });
})();