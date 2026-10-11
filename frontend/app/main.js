/**
 * Ask La Trobe — application bootstrap.
 *
 * Wires store + theme + views together. Renders the active screen
 * (login or chat) whenever store state changes.
 *
 * Conversations are server-side (user-scoped). The store holds an
 * in-memory cache fetched from the backend.
 *
 * Naming convention:
 *   - `ensureComposer()`             → returns the Composer INSTANCE
 *   - `getOrCreateComposerElement()` → returns the composer's DOM element
 */
(function () {
  'use strict';

  const CFG = window.ASK_LT_CONFIG;
  const Store = window.AskLTStore;
  const Theme = window.AskLTTheme;
  const Api = window.AskLTApi;
  const Thread = window.AskLTThread;
  const Composer = window.AskLTComposer.Composer;
  const Settings = window.AskLTSettings;
  const Chat = window.AskLTChat.ChatController;

  const IS_DEV = CFG.APP_ENV === 'development';

  const root = document.getElementById('app-root');

  // ─── Login form state ─────────────────────────────────────────────
  const loginState = {
    email: '',
    password: '',
    error: '',
    isSubmitting: false,
  };

  // ─── Composer instance ────────────────────────────────────────────
  let composerInstance = null;
  let settingsInstance = null;

  // ─── Scroll intent ────────────────────────────────────────────────
  // Set by chat callbacks; consumed once after the next render.
  //   'user'      → scroll to the top of the newest user message
  //   'assistant' → scroll to the top of the newest assistant message
  //   null        → restore the scroll position captured before the render
  let pendingScrollIntent = null;
  let lastKnownScrollTop = 0;

  const chatController = new Chat({
    onRender: () => render(),
    onConversationsChanged: () => {
      loadConversationsFromServer()
        .then(() => render())
        .catch(() => {});
    },
    onUserSent: () => {
      pendingScrollIntent = 'user';
    },
    onAssistantCommitted: () => {
      pendingScrollIntent = 'assistant';
    },
  });

  // ================================================================
  // SERVER-SIDE CONVERSATION HELPERS
  // ================================================================

  async function loadConversationsFromServer() {
    const state = Store.getState();
    if (!state.token) return;

    try {
      const data = await Api.listConversations(state.token);
      Store.setConversations(data.conversations || []);
    } catch (err) {
      if (err && err.name === 'UnauthorizedError') {
        Store.clearSession();
        render();
        return;
      }
      console.error('[conversations] failed to load', err);
    }
  }

  async function openConversationFromServer(conversationId) {
    const state = Store.getState();
    if (!state.token) return;

    try {
      const detail = await Api.loadConversation(state.token, conversationId);
      const messages = (detail.messages || []).map((m) => ({
        role: m.role,
        text: m.content,
        citations: m.citations || [],
      }));
      Store.setActiveConversation(conversationId, messages);
      render();
    } catch (err) {
      if (err && err.name === 'UnauthorizedError') {
        Store.clearSession();
      } else if (err && err.status === 404) {
        Store.removeConversationLocal(conversationId);
        await loadConversationsFromServer();
      } else {
        console.error('[conversations] failed to load one', err);
      }
      render();
    }
  }

  async function renameConversationOnServer(conversationId, newTitle) {
    const state = Store.getState();
    if (!state.token) return;

    if (IS_DEV)
      console.log('[rename] called. id=%s title=%r', conversationId, newTitle);
    try {
      const updated = await Api.renameConversation(
        state.token,
        conversationId,
        newTitle,
      );
      if (IS_DEV) console.log('[rename] API returned:', updated);
      Store.updateConversationLocal(conversationId, { title: updated.title });
      if (IS_DEV)
        console.log('[rename] store now:', Store.getState().conversations);
      render();
    } catch (err) {
      console.error('[rename] failed:', err);
      alert('Rename failed: ' + (err.message || 'unknown error'));
    }
  }

  async function deleteConversationOnServer(conversationId) {
    const state = Store.getState();
    if (!state.token) return;

    if (IS_DEV) console.log('[delete] called. id=%s', conversationId);
    try {
      const result = await Api.deleteConversation(state.token, conversationId);
      if (IS_DEV) console.log('[delete] API returned:', result);
      Store.removeConversationLocal(conversationId);
      if (IS_DEV)
        console.log('[delete] store now:', Store.getState().conversations);
      render();
    } catch (err) {
      console.error('[delete] failed:', err);
      alert('Delete failed: ' + (err.message || 'unknown error'));
    }
  }

  function formatWhen(isoString) {
    if (!isoString) return 'Earlier';
    const d = new Date(isoString);
    if (isNaN(d.getTime())) return 'Earlier';
    const now = new Date();
    const startOfDay = (dt) =>
      new Date(dt.getFullYear(), dt.getMonth(), dt.getDate());
    const days = Math.round((startOfDay(now) - startOfDay(d)) / 86400000);
    if (days === 0) return 'Today';
    if (days === 1) return 'Yesterday';
    if (days < 7) return 'Earlier this week';
    return 'Earlier';
  }

  // ================================================================
  // LOGIN SCREEN
  // ================================================================

  function renderLogin() {
    const wrap = document.createElement('div');
    wrap.className = 'login';

    const brand = document.createElement('div');
    brand.className = 'login__brand';
    brand.innerHTML = `
      <div class="login__logo">
        <img src="assets/latrobe-logo.png" alt="La Trobe University" />
      </div>
      <div class="login__hero">
        <div class="login__hero-rule"></div>
        <h1>Ask La&nbsp;Trobe</h1>
        <p>A conversational front door to internal policy, procedure and staff documentation. Sign in with your university account to begin.</p>
      </div>
      <p class="login__footnote">Student capstone prototype · CSE3PIT · Not an official university service</p>
    `;
    wrap.appendChild(brand);

    const formWrap = document.createElement('div');
    formWrap.className = 'login__form-wrap';

    const form = document.createElement('form');
    form.className = 'login__form';
    form.setAttribute('autocomplete', 'off');
    form.addEventListener('submit', (e) => {
      e.preventDefault();
      submitLogin();
    });

    const header = document.createElement('div');
    header.className = 'login__form-header';
    header.innerHTML = `
      <span class="login__form-eyebrow">Sign in</span>
      <h2 class="login__form-title">University account</h2>
    `;
    form.appendChild(header);

    const fields = document.createElement('div');
    fields.className = 'login__fields';

    fields.appendChild(
      buildField({
        label: 'Email',
        type: 'email',
        value: loginState.email,
        autocomplete: 'username',
        onChange: (v) => {
          loginState.email = v;
        },
      }),
    );

    fields.appendChild(
      buildField({
        label: 'Password',
        type: 'password',
        value: loginState.password,
        autocomplete: 'current-password',
        onChange: (v) => {
          loginState.password = v;
        },
        withPasswordToggle: true,
      }),
    );

    form.appendChild(fields);

    if (loginState.error) {
      const err = document.createElement('div');
      err.className = 'alert';
      err.textContent = loginState.error;
      form.appendChild(err);
    }

    const submitBtn = document.createElement('button');
    submitBtn.type = 'submit';
    submitBtn.className = 'btn btn--primary btn--full';
    submitBtn.textContent = loginState.isSubmitting ? 'Signing in…' : 'Sign in';
    submitBtn.disabled = loginState.isSubmitting;
    form.appendChild(submitBtn);

    const hint = document.createElement('p');
    hint.className = 'login__hint';
    hint.textContent = 'Sign in with your university credentials.';
    form.appendChild(hint);

    formWrap.appendChild(form);
    wrap.appendChild(formWrap);

    return wrap;
  }

  function buildField({
    label,
    type,
    value,
    autocomplete,
    onChange,
    withPasswordToggle,
  }) {
    const field = document.createElement('div');
    field.className = 'field';

    const labelEl = document.createElement('label');
    labelEl.className = 'field__label';
    labelEl.textContent = label;

    const inputId = 'field-' + Math.random().toString(36).slice(2, 9);
    labelEl.setAttribute('for', inputId);
    field.appendChild(labelEl);

    const wrap = document.createElement('div');
    wrap.className = 'field__input-wrap';

    const input = document.createElement('input');
    input.id = inputId;
    input.type = type;
    input.className = 'field__input';
    if (withPasswordToggle) input.classList.add('field__input--has-toggle');

    input.value = value || '';

    const isPassword = type === 'password';
    input.autocomplete = isPassword ? 'new-password' : autocomplete || 'off';
    input.setAttribute(
      'name',
      'field-' + Math.random().toString(36).slice(2, 9),
    );
    input.setAttribute('autocorrect', 'off');
    input.setAttribute('autocapitalize', 'off');
    input.setAttribute('spellcheck', 'false');
    input.setAttribute('data-lpignore', 'true');
    input.setAttribute('data-form-type', 'other');
    input.required = true;

    input.addEventListener('input', () => onChange(input.value));
    wrap.appendChild(input);

    if (withPasswordToggle && isPassword) {
      const toggle = document.createElement('button');
      toggle.type = 'button';
      toggle.className = 'field__toggle';
      toggle.setAttribute('aria-label', 'Show password');
      toggle.title = 'Show password';
      toggle.tabIndex = 0;

      const ICON_SHOW = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`;
      const ICON_HIDE = `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`;
      toggle.innerHTML = ICON_SHOW;

      let visible = false;
      toggle.addEventListener('click', () => {
        visible = !visible;
        input.type = visible ? 'text' : 'password';
        toggle.innerHTML = visible ? ICON_HIDE : ICON_SHOW;
        const lbl = visible ? 'Hide password' : 'Show password';
        toggle.setAttribute('aria-label', lbl);
        toggle.title = lbl;
        input.focus();
      });

      wrap.appendChild(toggle);
    }

    field.appendChild(wrap);
    return field;
  }

  // ================================================================
  // CHAT SCREEN
  // ================================================================

  function renderChat() {
    const state = Store.getState();
    const layout = state.layout || 'rail';

    const shell = document.createElement('div');
    shell.className = 'app-shell';

    let layoutEl;
    switch (layout) {
      case 'reading':
        layoutEl = renderReadingLayout(state);
        break;
      case 'console':
        layoutEl = renderConsoleLayout(state);
        break;
      case 'rail':
      default:
        layoutEl = renderRailLayout(state);
        break;
    }
    shell.appendChild(layoutEl);

    if (state.historyDrawerOpen && layout !== 'rail') {
      shell.appendChild(buildHistoryDrawer(state));
    }

    if (state.settingsOpen) {
      if (!settingsInstance) {
        settingsInstance = Settings.open(document.body, {
          onClose: () => {
            settingsInstance = null;
            Store.setState({ settingsOpen: false });
          },
          onClearHistory: async () => {
            const currentState = Store.getState();
            const list = currentState.conversations.slice();

            for (const conv of list) {
              try {
                await Api.deleteConversation(currentState.token, conv.id);
              } catch (_) {
                /* best-effort cleanup */
              }
            }

            Store.setConversations([]);
            Store.startNewConversation();
            render();
          },
          onSignOut: () => signOutUser(),
        });
      }
    } else if (settingsInstance) {
      settingsInstance.close();
    }

    return shell;
  }

  function buildHistoryDrawer(state) {
    const backdrop = document.createElement('div');
    backdrop.className = 'drawer-backdrop';
    backdrop.addEventListener('click', () =>
      Store.setState({ historyDrawerOpen: false }),
    );

    const panel = document.createElement('aside');
    panel.className = 'drawer-panel';
    panel.addEventListener('click', (e) => e.stopPropagation());

    const header = document.createElement('div');
    header.className = 'drawer-panel__header';
    header.innerHTML = `<span class="drawer-panel__title">History</span>`;

    const closeBtn = document.createElement('button');
    closeBtn.type = 'button';
    closeBtn.className = 'drawer-panel__close';
    closeBtn.setAttribute('aria-label', 'Close history');
    closeBtn.textContent = '×';
    closeBtn.addEventListener('click', () =>
      Store.setState({ historyDrawerOpen: false }),
    );
    header.appendChild(closeBtn);
    panel.appendChild(header);

    const list = document.createElement('div');
    list.className = 'drawer-panel__list';

    if (state.conversations.length === 0) {
      const empty = document.createElement('div');
      empty.style.padding = '20px 16px';
      empty.style.color = 'var(--fg-inverse-faint)';
      empty.style.fontSize = '13px';
      empty.textContent = 'No conversations yet.';
      list.appendChild(empty);
    } else {
      for (const c of state.conversations) {
        list.appendChild(
          buildDrawerConversationItem(c, state.activeConversationId),
        );
      }
    }
    panel.appendChild(list);

    const footer = document.createElement('div');
    footer.className = 'drawer-panel__footer';
    const newBtn = document.createElement('button');
    newBtn.type = 'button';
    newBtn.className = 'btn btn--primary btn--full';
    newBtn.textContent = 'New question';
    newBtn.addEventListener('click', () => {
      Store.setState({ historyDrawerOpen: false });
      newConversation();
    });
    footer.appendChild(newBtn);
    panel.appendChild(footer);

    backdrop.appendChild(panel);
    return backdrop;
  }

  function buildDrawerConversationItem(c) {
    const wrap = document.createElement('div');
    wrap.className = 'convo-item';

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'drawer-panel__item';
    btn.addEventListener('click', (e) => {
      if (e.target.closest('.convo-item__menu-btn')) return;
      Store.setState({ historyDrawerOpen: false });
      openConversation(c.id);
    });

    const title = document.createElement('span');
    title.className = 'drawer-panel__item-title';
    title.textContent = c.title || 'New enquiry';
    btn.appendChild(title);

    const when = document.createElement('span');
    when.className = 'drawer-panel__item-when';
    when.textContent = formatWhen(c.updated_at) || c.when || '';
    btn.appendChild(when);

    wrap.appendChild(btn);

    const menuBtn = document.createElement('button');
    menuBtn.type = 'button';
    menuBtn.className = 'convo-item__menu-btn';
    menuBtn.title = 'More options';
    menuBtn.setAttribute('aria-label', 'More options');
    menuBtn.textContent = '···';
    menuBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleConversationMenu(wrap);
    });
    wrap.appendChild(menuBtn);

    const menu = document.createElement('div');
    menu.className = 'convo-item__menu';
    menu.hidden = true;

    const renameBtn = document.createElement('button');
    renameBtn.type = 'button';
    renameBtn.className = 'convo-item__menu-action';
    renameBtn.textContent = 'Rename';
    renameBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      promptRename(c);
    });
    menu.appendChild(renameBtn);

    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className =
      'convo-item__menu-action convo-item__menu-action--danger';
    deleteBtn.textContent = 'Delete';
    deleteBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      deleteConversation(c.id);
    });
    menu.appendChild(deleteBtn);
    wrap.appendChild(menu);

    return wrap;
  }

  // ================================================================
  // RAIL LAYOUT
  // ================================================================

  function renderRailLayout(state) {
    const layout = document.createElement('div');
    layout.className = 'layout-rail';
    if (state.sidebarCollapsed)
      layout.classList.add('layout-rail--sidebar-collapsed');

    const sidebar = document.createElement('aside');
    sidebar.className = 'rail-sidebar';
    sidebar.appendChild(buildSidebarBrand());
    sidebar.appendChild(buildSidebarNewButton());
    sidebar.appendChild(buildSidebarList(state));
    sidebar.appendChild(buildSidebarFooter(state));
    layout.appendChild(sidebar);

    const main = document.createElement('main');
    main.className = 'rail-main';
    main.appendChild(
      buildSharedHeader(state, {
        title: state.activeConversationId
          ? state.conversations.find((c) => c.id === state.activeConversationId)
              ?.title || 'Enquiry'
          : 'New enquiry',
        showHistoryButton: false,
      }),
    );

    const scroll = document.createElement('div');
    scroll.className = 'rail-scroll';
    scroll.id = 'chat-scroll';
    const inner = document.createElement('div');
    inner.className = 'rail-scroll__inner';
    const threadContainer = document.createElement('div');
    threadContainer.className = 'thread';
    renderThreadInto(threadContainer, state);
    inner.appendChild(threadContainer);
    scroll.appendChild(inner);
    main.appendChild(scroll);

    const composerWrap = document.createElement('div');
    composerWrap.className = 'rail-composer-wrap';
    const composerInner = document.createElement('div');
    composerInner.className = 'rail-composer-wrap__inner';
    composerInner.appendChild(getOrCreateComposerElement());
    composerWrap.appendChild(composerInner);
    main.appendChild(composerWrap);

    layout.appendChild(main);
    return layout;
  }

  // ================================================================
  // READING LAYOUT
  // ================================================================

  function renderReadingLayout(state) {
    const layout = document.createElement('div');
    layout.className = 'layout-reading';

    layout.appendChild(
      buildSharedHeader(state, {
        title: state.activeConversationId
          ? state.conversations.find((c) => c.id === state.activeConversationId)
              ?.title || 'Enquiry'
          : 'New enquiry',
        showHistoryButton: true,
      }),
    );

    const scroll = document.createElement('div');
    scroll.className = 'reading-scroll';
    scroll.id = 'chat-scroll';
    const inner = document.createElement('div');
    inner.className = 'reading-scroll__inner';

    const titleBlock = document.createElement('div');
    titleBlock.className = 'reading-title-block';
    titleBlock.innerHTML = `
      <span class="reading-title-block__eyebrow">Enquiry</span>
      <h2 class="reading-title-block__title">${escapeHtml(
        state.activeConversationId
          ? state.conversations.find((c) => c.id === state.activeConversationId)
              ?.title || 'Enquiry'
          : 'New enquiry',
      )}</h2>
    `;
    inner.appendChild(titleBlock);

    const threadContainer = document.createElement('div');
    threadContainer.className = 'thread';
    renderThreadInto(threadContainer, state);
    inner.appendChild(threadContainer);

    scroll.appendChild(inner);
    layout.appendChild(scroll);

    const composerWrap = document.createElement('div');
    composerWrap.className = 'reading-composer-wrap';
    const composerInner = document.createElement('div');
    composerInner.className = 'reading-composer-wrap__inner';
    composerInner.appendChild(getOrCreateComposerElement());
    composerWrap.appendChild(composerInner);
    layout.appendChild(composerWrap);

    return layout;
  }

  // ================================================================
  // CONSOLE LAYOUT
  // ================================================================

  function renderConsoleLayout(state) {
    const layout = document.createElement('div');
    layout.className = 'layout-console';

    const rail = document.createElement('nav');
    rail.className = 'console-rail';
    rail.innerHTML = `<div class="console-rail__logo">LT</div>`;

    const railButtons = document.createElement('div');
    railButtons.className = 'console-rail__buttons';

    const askBtn = document.createElement('button');
    askBtn.type = 'button';
    askBtn.className = 'console-rail__btn console-rail__btn--primary';
    askBtn.textContent = 'ASK';
    askBtn.title = 'New question';
    askBtn.addEventListener('click', () => newConversation());
    railButtons.appendChild(askBtn);

    const histBtn = document.createElement('button');
    histBtn.type = 'button';
    histBtn.className = 'console-rail__btn';
    histBtn.textContent = 'HIST';
    histBtn.title = 'Show/hide history panel';
    histBtn.addEventListener('click', () => {
      Store.setState({
        historyDrawerOpen: !Store.getState().historyDrawerOpen,
      });
    });
    railButtons.appendChild(histBtn);

    const settingsBtn = document.createElement('button');
    settingsBtn.type = 'button';
    settingsBtn.className = 'console-rail__btn';
    settingsBtn.textContent = 'CONF';
    settingsBtn.title = 'Settings';
    settingsBtn.addEventListener('click', () => {
      Store.setState({ settingsOpen: !Store.getState().settingsOpen });
    });
    railButtons.appendChild(settingsBtn);

    const exitBtn = document.createElement('button');
    exitBtn.type = 'button';
    exitBtn.className = 'console-rail__btn';
    exitBtn.textContent = 'EXIT';
    exitBtn.title = 'Sign out';
    exitBtn.addEventListener('click', () => signOutUser());
    railButtons.appendChild(exitBtn);

    rail.appendChild(railButtons);
    layout.appendChild(rail);

    if (state.historyDrawerOpen) {
      const panel = document.createElement('aside');
      panel.className = 'console-panel';
      panel.innerHTML = `<div class="console-panel__header"><span class="console-panel__title">Recent enquiries</span></div>`;
      const panelList = document.createElement('div');
      panelList.className = 'console-panel__list';
      for (const c of state.conversations) {
        panelList.appendChild(
          buildConversationItem(c, state.activeConversationId, 'console-panel'),
        );
      }
      panel.appendChild(panelList);
      layout.appendChild(panel);
    }

    const main = document.createElement('main');
    main.className = 'console-main';

    const win = document.createElement('div');
    win.className = 'console-window';

    win.appendChild(
      buildSharedHeader(state, {
        title: state.activeConversationId
          ? state.conversations.find((c) => c.id === state.activeConversationId)
              ?.title || 'Enquiry'
          : 'New enquiry',
        showHistoryButton: true,
        extraRight: buildStatusBadge(state),
      }),
    );

    const scroll = document.createElement('div');
    scroll.className = 'console-window__scroll';
    scroll.id = 'chat-scroll';
    const inner = document.createElement('div');
    inner.className = 'console-window__scroll-inner';
    const threadContainer = document.createElement('div');
    threadContainer.className = 'thread';
    renderThreadInto(threadContainer, state);
    inner.appendChild(threadContainer);
    scroll.appendChild(inner);
    win.appendChild(scroll);

    const composerWrap = document.createElement('div');
    composerWrap.className = 'console-window__composer';
    const composerInner = document.createElement('div');
    composerInner.className = 'console-window__composer-inner';
    composerInner.appendChild(getOrCreateComposerElement());
    composerWrap.appendChild(composerInner);
    win.appendChild(composerWrap);

    main.appendChild(win);
    layout.appendChild(main);

    return layout;
  }

  function buildStatusBadge(state) {
    const el = document.createElement('span');
    el.className = 'console-window__status';
    el.innerHTML = `<span class="console-window__status-dot"></span>${state.isSending ? 'Responding' : 'Ready'}`;
    return el;
  }

  // ================================================================
  // SHARED HEADER
  // ================================================================

  function buildSharedHeader(state, opts) {
    const header = document.createElement('header');
    header.className = 'shared-header';

    const left = document.createElement('div');
    left.className = 'shared-header__left';

    if ((state.layout || 'rail') === 'rail') {
      const sidebarToggle = document.createElement('button');
      sidebarToggle.type = 'button';
      sidebarToggle.className = 'shared-header__icon-btn';
      sidebarToggle.title = state.sidebarCollapsed
        ? 'Show sidebar'
        : 'Hide sidebar';
      sidebarToggle.setAttribute('aria-label', sidebarToggle.title);
      sidebarToggle.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="18" height="18" rx="2"/><line x1="9" y1="3" x2="9" y2="21"/></svg>`;
      sidebarToggle.addEventListener('click', () => Store.toggleSidebar());
      left.appendChild(sidebarToggle);
    }

    if (opts.showHistoryButton) {
      const histBtn = document.createElement('button');
      histBtn.type = 'button';
      histBtn.className = 'shared-header__icon-btn';
      histBtn.title = 'History';
      histBtn.setAttribute('aria-label', 'Open history');
      histBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7L3 8"/><polyline points="3 3 3 8 8 8"/><polyline points="12 7 12 12 15 15"/></svg>`;
      histBtn.addEventListener('click', () =>
        Store.setState({ historyDrawerOpen: true }),
      );
      left.appendChild(histBtn);
    }

    const title = document.createElement('span');
    title.className = 'shared-header__title';
    title.textContent = opts.title;
    left.appendChild(title);

    header.appendChild(left);

    const right = document.createElement('div');
    right.className = 'shared-header__right';

    if (opts.extraRight) right.appendChild(opts.extraRight);

    const newBtn = document.createElement('button');
    newBtn.type = 'button';
    newBtn.className = 'shared-header__icon-btn';
    newBtn.title = 'New question';
    newBtn.setAttribute('aria-label', 'New question');
    newBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>`;
    newBtn.addEventListener('click', () => newConversation());
    right.appendChild(newBtn);

    const layoutBtn = document.createElement('button');
    layoutBtn.type = 'button';
    layoutBtn.className = 'shared-header__icon-btn';
    layoutBtn.title = 'Switch layout';
    layoutBtn.setAttribute('aria-label', 'Switch layout');
    layoutBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="3" width="7" height="7"/><rect x="14" y="3" width="7" height="7"/><rect x="14" y="14" width="7" height="7"/><rect x="3" y="14" width="7" height="7"/></svg>`;
    layoutBtn.addEventListener('click', () => {
      const current = Store.getState().layout || 'rail';
      const next =
        current === 'rail'
          ? 'reading'
          : current === 'reading'
            ? 'console'
            : 'rail';
      Store.setState({ layout: next });
    });
    right.appendChild(layoutBtn);

    const themeBtn = document.createElement('button');
    themeBtn.type = 'button';
    themeBtn.className = 'shared-header__icon-btn';
    const resolved = Theme.getResolvedTheme();
    const isDark = resolved === 'dark';
    themeBtn.title = isDark ? 'Switch to light mode' : 'Switch to dark mode';
    themeBtn.setAttribute('aria-label', themeBtn.title);
    themeBtn.innerHTML = isDark
      ? `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41"/></svg>`
      : `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/></svg>`;
    themeBtn.addEventListener('click', () => {
      const currentResolved = Theme.getResolvedTheme();
      const next = currentResolved === 'dark' ? 'light' : 'dark';
      Theme.setTheme(next);
    });
    right.appendChild(themeBtn);

    const settingsBtn = document.createElement('button');
    settingsBtn.type = 'button';
    settingsBtn.className = 'shared-header__icon-btn';
    settingsBtn.title = 'Settings';
    settingsBtn.setAttribute('aria-label', 'Settings');
    settingsBtn.innerHTML = `<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/></svg>`;
    settingsBtn.addEventListener('click', () => {
      Store.setState({ settingsOpen: !Store.getState().settingsOpen });
    });
    right.appendChild(settingsBtn);

    header.appendChild(right);
    return header;
  }

  // ================================================================
  // SIDEBAR PIECES
  // ================================================================

  function buildSidebarBrand() {
    const el = document.createElement('div');
    el.className = 'rail-sidebar__brand';
    el.innerHTML = `
      <span class="rail-sidebar__brand-primary">LA TROBE</span>
      <span class="rail-sidebar__brand-secondary">UNIVERSITY</span>
    `;
    return el;
  }

  function buildSidebarNewButton() {
    const wrap = document.createElement('div');
    wrap.className = 'rail-sidebar__new';
    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = 'btn btn--primary btn--full';
    btn.textContent = 'New question';
    btn.addEventListener('click', () => newConversation());
    wrap.appendChild(btn);
    return wrap;
  }

  function buildSidebarList(state) {
    const list = document.createElement('div');
    list.className = 'rail-sidebar__list';

    if (state.conversations.length === 0) return list;

    const groups = new Map();
    for (const c of state.conversations) {
      const key = formatWhen(c.updated_at) || c.when || 'Earlier';
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push(c);
    }

    for (const [label, items] of groups) {
      const group = document.createElement('div');
      group.className = 'rail-sidebar__group';

      const groupLabel = document.createElement('span');
      groupLabel.className = 'rail-sidebar__group-label';
      groupLabel.textContent = label;
      group.appendChild(groupLabel);

      for (const c of items) {
        group.appendChild(
          buildConversationItem(c, state.activeConversationId, 'rail-sidebar'),
        );
      }
      list.appendChild(group);
    }

    return list;
  }

  function buildConversationItem(c, activeId, baseClass) {
    const wrapper = document.createElement('div');
    wrapper.className = 'convo-item';
    wrapper.dataset.conversationId = c.id;

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.className = baseClass + '__item';
    if (c.id === activeId) btn.classList.add(baseClass + '__item--active');
    btn.addEventListener('click', (e) => {
      if (e.target.closest('.convo-item__menu-btn')) return;
      openConversation(c.id);
    });

    if (c.id === activeId) {
      const marker = document.createElement('span');
      marker.className = baseClass + '__item-marker';
      btn.appendChild(marker);
    }

    const title = document.createElement('span');
    title.className = baseClass + '__item-title';
    title.textContent = c.title || 'New enquiry';
    btn.appendChild(title);

    if (baseClass === 'console-panel') {
      const when = document.createElement('span');
      when.className = baseClass + '__item-when';
      when.textContent = formatWhen(c.updated_at) || c.when || '';
      btn.appendChild(when);
    }

    wrapper.appendChild(btn);

    const menuBtn = document.createElement('button');
    menuBtn.type = 'button';
    menuBtn.className = 'convo-item__menu-btn';
    menuBtn.title = 'More options';
    menuBtn.setAttribute('aria-label', 'More options');
    menuBtn.textContent = '···';
    menuBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleConversationMenu(wrapper);
    });
    wrapper.appendChild(menuBtn);

    const menu = document.createElement('div');
    menu.className = 'convo-item__menu';
    menu.hidden = true;

    const renameBtn = document.createElement('button');
    renameBtn.type = 'button';
    renameBtn.className = 'convo-item__menu-action';
    renameBtn.textContent = 'Rename';
    renameBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      promptRename(c);
    });
    menu.appendChild(renameBtn);

    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className =
      'convo-item__menu-action convo-item__menu-action--danger';
    deleteBtn.textContent = 'Delete';
    deleteBtn.addEventListener('click', (e) => {
      e.stopPropagation();
      deleteConversation(c.id);
    });
    menu.appendChild(deleteBtn);
    wrapper.appendChild(menu);

    return wrapper;
  }

  function toggleConversationMenu(wrapper) {
    const thisMenu = wrapper.querySelector('.convo-item__menu');
    if (!thisMenu) return;

    const wasOpen = !thisMenu.hidden;

    document.querySelectorAll('.convo-item__menu').forEach((m) => {
      m.hidden = true;
    });
    document
      .querySelectorAll('.convo-item--menu-open')
      .forEach((w) => w.classList.remove('convo-item--menu-open'));

    if (wasOpen) return;

    thisMenu.hidden = false;
    wrapper.classList.add('convo-item--menu-open');

    const closeOnOutside = (ev) => {
      if (!wrapper.contains(ev.target)) {
        thisMenu.hidden = true;
        wrapper.classList.remove('convo-item--menu-open');
        document.removeEventListener('click', closeOnOutside, true);
      }
    };
    setTimeout(
      () => document.addEventListener('click', closeOnOutside, true),
      0,
    );
  }

  function promptRename(conversation) {
    document.querySelectorAll('.convo-item__menu').forEach((m) => {
      m.hidden = true;
    });
    document
      .querySelectorAll('.convo-item--menu-open')
      .forEach((w) => w.classList.remove('convo-item--menu-open'));

    const overlay = document.createElement('div');
    overlay.className = 'rename-modal-backdrop';
    overlay.addEventListener('click', (e) => {
      if (e.target === overlay) close();
    });

    const modal = document.createElement('div');
    modal.className = 'rename-modal';
    modal.addEventListener('click', (e) => e.stopPropagation());

    const title = document.createElement('h3');
    title.className = 'rename-modal__title';
    title.textContent = 'Rename conversation';
    modal.appendChild(title);

    const input = document.createElement('input');
    input.type = 'text';
    input.className = 'rename-modal__input';
    input.value = conversation.title || '';
    input.maxLength = 200;
    input.setAttribute('autocomplete', 'off');
    input.setAttribute('spellcheck', 'false');
    modal.appendChild(input);

    const actions = document.createElement('div');
    actions.className = 'rename-modal__actions';

    const cancelBtn = document.createElement('button');
    cancelBtn.type = 'button';
    cancelBtn.className = 'btn btn--secondary';
    cancelBtn.textContent = 'Cancel';
    cancelBtn.addEventListener('click', () => close());
    actions.appendChild(cancelBtn);

    const saveBtn = document.createElement('button');
    saveBtn.type = 'button';
    saveBtn.className = 'btn btn--primary';
    saveBtn.textContent = 'Save';
    saveBtn.addEventListener('click', () => {
      const trimmed = input.value.trim();
      if (!trimmed || trimmed === conversation.title) {
        close();
        return;
      }
      close();
      renameConversationOnServer(conversation.id, trimmed);
    });
    actions.appendChild(saveBtn);

    modal.appendChild(actions);
    overlay.appendChild(modal);

    function close() {
      document.removeEventListener('keydown', onKey);
      overlay.remove();
    }

    function onKey(e) {
      if (e.key === 'Escape') close();
      else if (e.key === 'Enter' && document.activeElement === input) {
        saveBtn.click();
      }
    }

    document.addEventListener('keydown', onKey);
    document.body.appendChild(overlay);

    setTimeout(() => {
      input.focus();
      input.select();
    }, 10);
  }

  function deleteConversation(id) {
    document.querySelectorAll('.convo-item__menu').forEach((m) => {
      m.hidden = true;
    });
    document
      .querySelectorAll('.convo-item--menu-open')
      .forEach((w) => w.classList.remove('convo-item--menu-open'));
    deleteConversationOnServer(id);
  }

  function buildSidebarFooter(state) {
    const el = document.createElement('div');
    el.className = 'rail-sidebar__footer';

    const user = state.user || {};
    const info = document.createElement('div');
    info.className = 'rail-sidebar__user';
    info.innerHTML = `
      <span class="rail-sidebar__user-name">${escapeHtml(user.full_name || 'Signed in')}</span>
      <span class="rail-sidebar__user-role">${escapeHtml(user.role ? 'Role · ' + user.role : 'La Trobe University')}</span>
    `;
    el.appendChild(info);

    const signOut = document.createElement('button');
    signOut.type = 'button';
    signOut.className = 'rail-sidebar__signout';
    signOut.textContent = 'Sign out';
    signOut.addEventListener('click', () => signOutUser());
    el.appendChild(signOut);

    return el;
  }

  // ================================================================
  // THREAD + COMPOSER
  // ================================================================

  function renderThreadInto(container, state) {
    Thread.render(container, {
      messages: state.messages,
      suggestions: CFG.SUGGESTIONS,
      greeting: getGreeting(),
      isStreaming: state.isSending,
      error: state.error,
      handlers: {
        onSuggestion: (text) => {
          const composer = ensureComposer();
          composer.setValue(text);
          composer.focus();
        },
        onCopy: (text) => chatController.copy(text),
        onRetry: (i) => chatController.retry(i),
      },
    });
  }

  function ensureComposer() {
    if (composerInstance) return composerInstance;

    composerInstance = new Composer({
      onSubmit: (text) => {
        composerInstance.clear();
        chatController.send(text);
      },
      onStop: () => {
        chatController.stop();
      },
      onMic: () => {
        toggleVoice();
      },
    });

    return composerInstance;
  }

  function getOrCreateComposerElement() {
    return ensureComposer().el;
  }

  function getGreeting() {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning.';
    if (hour < 18) return 'Good afternoon.';
    return 'Good evening.';
  }

  // ================================================================
  // SCROLL
  // ================================================================

  /**
   * Applies the pending scroll intent, or restores the pre-render
   * scroll position when there is no intent. Must be called AFTER the
   * new DOM has been inserted so the target nodes exist.
   */
  function applyScrollIntent(previousScrollTop) {
    const el = document.getElementById('chat-scroll');
    if (!el) return;

    const intent = pendingScrollIntent;
    pendingScrollIntent = null;

    if (intent === 'user' || intent === 'assistant') {
      // Walk backwards over tagged messages; first match wins.
      const messages = Array.from(el.querySelectorAll('[data-message-index]'));
      let target = null;
      for (let i = messages.length - 1; i >= 0; i--) {
        const node = messages[i];
        const isUser = node.classList.contains('message--user');
        const isBot = node.classList.contains('message--bot');
        if (intent === 'user' && isUser) {
          target = node;
          break;
        }
        if (
          intent === 'assistant' &&
          isBot &&
          !node.classList.contains('message--loading')
        ) {
          target = node;
          break;
        }
      }

      if (target) {
        // Compute the target's position relative to the scroll container
        // and set scrollTop directly. scrollIntoView can be defeated by
        // the container's own scrolling behaviour and lands at 0.
        const containerRect = el.getBoundingClientRect();
        const targetRect = target.getBoundingClientRect();
        const offsetWithinScroll =
          targetRect.top - containerRect.top + el.scrollTop;

        const MARGIN = 12;
        const newTop = Math.max(0, offsetWithinScroll - MARGIN);

        const prefersReduced = window.matchMedia(
          '(prefers-reduced-motion: reduce)',
        ).matches;

        if (prefersReduced) {
          el.scrollTop = newTop;
        } else {
          el.scrollTo({ top: newTop, behavior: 'smooth' });
        }
        return;
      }
    }

    // No intent — restore the pre-render scroll position.
    if (typeof previousScrollTop === 'number') {
      el.scrollTop = previousScrollTop;
    }
  }
  
  

  // ================================================================
  // ACTIONS
  // ================================================================

  async function submitLogin() {
    if (loginState.isSubmitting) return;

    if (!loginState.email || !loginState.password) {
      loginState.error = 'Please enter both email and password.';
      render();
      return;
    }

    loginState.isSubmitting = true;
    loginState.error = '';
    render();

    try {
      const data = await Api.login(loginState.email, loginState.password);
      const token = data.access_token;
      if (!token) throw new Error('No token returned by backend.');

      const user = await Api.me(token);
      Store.setSession(token, user);

      loginState.email = '';
      loginState.password = '';
      loginState.isSubmitting = false;
      loginState.error = '';

      await loadConversationsFromServer();
    } catch (err) {
      loginState.isSubmitting = false;
      loginState.error =
        err && err.message ? err.message : CFG.MESSAGES.GENERIC_ERROR;
    }
    render();
  }

  function signOutUser() {
    Store.clearSession();
    if (composerInstance) composerInstance.clear();
    render();
  }

  function newConversation() {
    Store.startNewConversation();
    if (composerInstance) composerInstance.clear();
    render();
    setTimeout(() => {
      if (composerInstance) composerInstance.focus();
    }, 0);
  }

  function openConversation(id) {
    Store.setState({
      activeConversationId: id,
      messages: [],
      error: null,
    });
    render();
    openConversationFromServer(id);
  }

  function toggleVoice() {
    const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SR) {
      alert('Voice input requires Chrome or Edge.');
      return;
    }
    const listening = !Store.getState().isListening;
    Store.setState({ isListening: listening });
    if (composerInstance) composerInstance.setListening(listening);
    if (!listening) return;

    const rec = new SR();
    rec.lang = 'en-AU';
    rec.interimResults = false;
    rec.onresult = (e) => {
      const text = e.results[0][0].transcript;
      if (composerInstance) composerInstance.setValue(text);
    };
    rec.onend = () => {
      Store.setState({ isListening: false });
      if (composerInstance) composerInstance.setListening(false);
    };
    rec.onerror = () => {
      Store.setState({ isListening: false });
      if (composerInstance) composerInstance.setListening(false);
    };
    rec.start();
  }

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }

  // ================================================================
  // RENDER LOOP
  // ================================================================

  function render() {
    const currentComposer = composerInstance;
    const shouldRefocusComposer =
      currentComposer && document.activeElement === currentComposer.inputEl;

    // Snapshot scroll position before wiping the DOM.
    const scrollBefore = document.getElementById('chat-scroll');
    if (scrollBefore) lastKnownScrollTop = scrollBefore.scrollTop;
    const previousScrollTop = lastKnownScrollTop;

    root.innerHTML = '';
    const state = Store.getState();

    if (state.authStatus === 'authenticated') {
      root.appendChild(renderChat());

      const composer = ensureComposer();
      composer.setBusy(state.isSending);

      if (shouldRefocusComposer) {
        composer.focus();
      }

      // Set scrollTop directly to the newest message.
      //
      // We deliberately do NOT use applyScrollIntent here. In this codebase,
      // the scroll container is rebuilt from scratch on every render
      // (root.innerHTML = ''). Any scroll applied before the rebuild is lost,
      // and any scroll applied after needs to survive the composer re-focus
      // and the async conversation-list refresh that fires 100–300 ms later.
      //
      // Setting scrollTop inside a setTimeout(100ms) window is the most
      // reliable: by then the DOM is built, the composer has been focused,
      // and any early scroll resets have already happened.
      setTimeout(() => {
        const el = document.getElementById('chat-scroll');
        if (!el) return;

        const intent = pendingScrollIntent;
        pendingScrollIntent = null;

        const msgs = el.querySelectorAll('[data-message-index]');
        if (!msgs.length) return;

        let target = null;
        for (let i = msgs.length - 1; i >= 0; i--) {
          const node = msgs[i];
          const isUser = node.classList.contains('message--user');
          const isBot =
            node.classList.contains('message--bot') &&
            !node.classList.contains('message--loading');
          if (intent === 'user' && isUser) {
            target = node;
            break;
          }
          if (intent === 'assistant' && isBot) {
            target = node;
            break;
          }
        }

        if (target) {
          const containerTop = el.getBoundingClientRect().top;
          const targetTop = target.getBoundingClientRect().top;
          el.scrollTop = el.scrollTop + (targetTop - containerTop) - 12;
        }
      }, 100);




    } else if (state.authStatus === 'checking') {
      return;
    } else {
      root.appendChild(renderLogin());
    }
  }

  Store.subscribe(() => render());

  document.addEventListener('keydown', (e) => {
    if (e.key !== 'Escape') return;
    const s = Store.getState();
    if (s.settingsOpen) {
      Store.setState({ settingsOpen: false });
    } else if (s.historyDrawerOpen) {
      Store.setState({ historyDrawerOpen: false });
    }
  });

  async function bootstrap() {
    const state = Store.getState();
    if (state.token) {
      try {
        const user = await Api.me(state.token);
        Store.setSession(state.token, user);

        await loadConversationsFromServer();

        const lastId = Store.getState().activeConversationId;
        if (lastId) {
          await openConversationFromServer(lastId);
        }
      } catch (err) {
        if (err && err.name === 'UnauthorizedError') {
          Store.clearSession();
        } else {
          Store.setState({ authStatus: 'anonymous' });
        }
      }
    } else {
      Store.setState({ authStatus: 'anonymous' });
    }
    render();
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', bootstrap);
  } else {
    bootstrap();
  }
})();