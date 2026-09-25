/**
 * Ask La Trobe — markdown + citation rendering.
 *
 * Wraps `marked` for parsing and `DOMPurify` for sanitization.
 * Renders text and citations into DOM elements for safe insertion.
 */
(function () {
  'use strict';

  // Configure marked once, at module load, if the library is present.
  if (window.marked) {
    window.marked.setOptions({
      gfm: true,
      breaks: true,
    });
  }

  /** Allowed tags for markdown output. Strict allowlist. */
  const ALLOWED_TAGS = [
    'p', 'br', 'strong', 'em', 'u', 's', 'del', 'ins',
    'a', 'ul', 'ol', 'li', 'blockquote',
    'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
    'code', 'pre',
    'hr', 'table', 'thead', 'tbody', 'tr', 'th', 'td',
  ];

  const ALLOWED_ATTR = ['href', 'title', 'target', 'rel'];

  /**
   * Renders a markdown string into a sanitized HTML string.
   *
   * When `citations` is supplied, inline citation markers like `[C1]`
   * are rewritten into clickable anchor tags that point at the source
   * policy URL. Markers inside code spans/blocks are left as literal
   * text.
   */
function renderMarkdown(text, citations) {
    if (!text) return '';
    if (!window.marked || !window.DOMPurify) return escapeHtml(text);

    let html = window.marked.parse(text);

    if (Array.isArray(citations) && citations.length > 0) {
      html = linkifyInlineCitations(html, citations);
    }

    return window.DOMPurify.sanitize(html, {
      ALLOWED_TAGS,
      ALLOWED_ATTR,
      ADD_ATTR: ['target', 'rel'], // 🛡️ Ensures target="_blank" is never stripped
      ALLOWED_URI_REGEXP: /^(?:https?:|mailto:)/i,
    });
  }

  /**
   * Rewrites bare `[C1]` markers into `<a>` links, skipping anything
   * inside `<code>` / `<pre>` blocks so literal occurrences stay literal.
   */
  function linkifyInlineCitations(html, citations) {
    // Build the id → { url, title } map once.
    const byId = new Map();
    for (const c of citations) {
      if (!c || !c.citation_id) continue;
      byId.set(c.citation_id, {
        url: c.url || '',
        title: c.title || '',
      });
    }
    if (byId.size === 0) return html;

    // Split on code/pre segments so we don't rewrite inside them.
    return html
      .split(/(<(?:code|pre)\b[\s\S]*?<\/(?:code|pre)>)/gi)
      .map((segment, i) => {
        // Odd indices are the code/pre chunks; leave them untouched.
        if (i % 2 === 1) return segment;
        return segment.replace(/\[(C\d+)\]/g, (match, id) => {
          const meta = byId.get(id);
          if (!meta || !meta.url) return match;
          const safeUrl = escapeAttr(meta.url);
          const safeTitle = escapeAttr(meta.title || id);
          return (
            `<a class="cite-inline" href="${safeUrl}" ` +
            `title="${safeTitle}" target="_blank" ` +
            `rel="noopener noreferrer">[${id}]</a>`
          );
        });
      })
      .join('');
  }

  /** Escapes a string for safe inclusion inside an HTML attribute value. */
  function escapeAttr(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;');
  }

  /** Escapes plain text for safe insertion. */
  function escapeHtml(text) {
    return String(text)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  /** Builds the citations list element for a message. */
  function buildCitationsElement(citations) {
    if (!Array.isArray(citations) || citations.length === 0) return null;

    const wrap = document.createElement('div');
    wrap.className = 'citations';

    const label = document.createElement('span');
    label.className = 'citations__label';
    label.textContent = 'Sources';
    wrap.appendChild(label);

    const list = document.createElement('ul');
    list.className = 'citations__list';

    for (const c of citations) {
      const item = document.createElement('li');
      item.className = 'citations__item';

      const id = document.createElement('span');
      id.className = 'citations__id';
      id.textContent = c.citation_id || '';
      item.appendChild(id);

      const body = document.createElement('span');
      body.className = 'citations__body';

      const title = document.createElement('span');
      title.className = 'citations__title';
      title.textContent = c.title || '';
      body.appendChild(title);

      if (c.section) {
        const section = document.createElement('span');
        section.className = 'citations__section';
        section.textContent = c.section;
        body.appendChild(section);
      }

      if (c.url) {
        const link = document.createElement('a');
        link.className = 'citations__link';
        link.href = c.url;
        link.target = '_blank';
        link.rel = 'noopener noreferrer';
        link.textContent = 'View policy ↗';
        body.appendChild(link);
      }

      item.appendChild(body);
      list.appendChild(item);
    }

    wrap.appendChild(list);
    return wrap;
  }

/**
   * Applies sanitized markdown HTML to an element's innerHTML.
   *
   * Pass `citations` to make inline `[C1]` markers clickable.
   */
  function applyMarkdownToElement(el, text, citations) {
    if (!el) return;
    if (!text) {
      el.innerHTML = '';
      return;
    }
    el.innerHTML = renderMarkdown(text, citations);

    // Force external-link behaviour and stop event hijacking
    const links = el.querySelectorAll('a.cite-inline');
    for (const a of links) {
      a.target = '_blank';
      a.rel = 'noopener noreferrer';
      
      // Stop parent containers or routers from intercepting the click
      a.addEventListener('click', (e) => {
        e.stopPropagation();
      });
    }
  }

  window.AskLTMarkdown = Object.freeze({
    render: renderMarkdown,
    escapeHtml,
    buildCitationsElement,
    applyMarkdownToElement,
  });
})();