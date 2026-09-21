/**
 * Ask La Trobe Policy DB Chatbot — non-question shortcuts.
 *
 * Matches greetings, thanks, farewells, and other non-policy messages
 * and returns an instant canned reply. Saves an LLM call and improves
 * perceived speed for the most common chit-chat inputs.
 *
 * Matching strategy:
 *   1. Normalize the input (lowercase, collapse whitespace, strip trailing punctuation).
 *   2. For each rule, test the START of the input (prefix match) rather than
 *      requiring the ENTIRE input to match. This allows "thanks bye bye tata"
 *      to be caught as a "thanks" (the first intent wins).
 *   3. Rules are ordered so more specific intents are checked first.
 */
(function () {
  'use strict';

  /**
   * Ordered list of { test, reply }. The FIRST match wins.
   * Each `test` is a function that receives the normalized input
   * and returns true/false.
   */
  const RULES = [
    // ── Gratitude ────────────────────────────────────────────────────
    {
      test: (n) => /^(thanks?|thank ?you|thankyou|cheers|ta|ty|thx|appreciate(d)?( it)?)(\b|$)/i.test(n),
      reply: "You're welcome! Let me know if you have any other questions.",
    },

    // ── Farewell ─────────────────────────────────────────────────────
    {
      test: (n) => /^(bye( bye)*|good ?bye|see (ya|you)|cya|catch ya|good ?night|tata|ta ta|farewell)(\b|$)/i.test(n),
      reply: 'Goodbye! Come back any time.',
    },

    // ── Greeting ─────────────────────────────────────────────────────
    {
      test: (n) => /^(hi+|hello+|hey+|heya|g'?day|greetings|good (morning|afternoon|evening)|yo)(\b|$)/i.test(n),
      reply: 'Hi! What would you like to know about La Trobe policies?',
    },

    // ── Acknowledgment ───────────────────────────────────────────────
    {
      test: (n) => /^(ok(ay)?|k|cool|got it|understood|alright|right|fine|sure|no worries|gotcha|yep|yeah|yup|nope)\.?$/i.test(n),
      reply: 'Glad to help. Anything else?',
    },

    // ── Help requests ────────────────────────────────────────────────
    {
      test: (n) => /^(help( me)?|i need help|can you help( me)?|assist me|i need assistance|what can you do)(\b|$)/i.test(n),
      reply: "I'm here to help with La Trobe policies, procedures and staff documentation. What would you like to know?",
    },

    // ── Meta / identity ──────────────────────────────────────────────
    {
      test: (n) => /^(who are you|what are you|who am i talking to)(\b|$)/i.test(n),
      reply: "I'm Ask La Trobe — an assistant for La Trobe policy, procedure and staff documentation. Ask me anything about those topics.",
    },

    // ── Test / ping ──────────────────────────────────────────────────
    {
      test: (n) => /^(test(ing)?|ping|are you there|are you working)(\b|$)/i.test(n),
      reply: 'Systems running. Ask me anything about La Trobe policies.',
    },
  ];

  /** Normalize input for matching. */
  function normalize(text) {
    return String(text || '')
      .toLowerCase()
      .replace(/\s+/g, ' ')
      .trim()
      .replace(/[!.?,;:]+$/, '');
  }

  /**
   * Returns a canned reply if the input matches a shortcut intent,
   * or null if it should go through the normal RAG pipeline.
   */
  function match(query) {
    const n = normalize(query);
    if (!n) return null;

    for (const rule of RULES) {
      if (rule.test(n)) {
        return rule.reply;
      }
    }
    return null;
  }

  window.AskLTShortcuts = Object.freeze({ match, normalize });
})();