/**
 * Ask La Trobe — Auth0 authentication.
 *
 * Wraps Auth0 SPA SDK for login/logout/token management.
 * Other modules consume `window.AskLTAuth`.
 */
(function () {
  'use strict';

  const CFG = window.ASK_LT_CONFIG;
  const Store = window.AskLTStore;

  let auth0Client = null;
  let initPromise = null;

  /** Initialise Auth0 client (once). */
async function init() {
  if (auth0Client) return auth0Client;
  if (initPromise) return initPromise;

  initPromise = (async () => {
    // Auth0 SDK v2.1 exposes the factory as window.auth0.createAuth0Client
    const factory =
      (window.auth0 && typeof window.auth0.createAuth0Client === 'function' && window.auth0.createAuth0Client) ||
      (typeof window.createAuth0Client === 'function' && window.createAuth0Client);

    if (!factory) {
      throw new Error(
        'Auth0 SDK not loaded. Expected window.auth0.createAuth0Client.'
      );
    }

    auth0Client = await factory({
      domain: CFG.AUTH0_DOMAIN,
      clientId: CFG.AUTH0_CLIENT_ID,
      authorizationParams: {
        redirect_uri: CFG.AUTH0_REDIRECT_URI,
        audience: CFG.AUTH0_AUDIENCE,
        scope: 'openid profile email offline_access',
      },
      useRefreshTokens: true,
      cacheLocation: 'localstorage',
    });
    return auth0Client;
  })();

  return initPromise;
}

  /** Handle the redirect callback from Auth0. */
  async function handleRedirectCallback() {
    const client = await init();
    const params = new URLSearchParams(window.location.search);
    if (params.has('code') && params.has('state')) {
      try {
        await client.handleRedirectCallback();
        // Clean the URL after callback.
        window.history.replaceState({}, document.title, window.location.pathname);
      } catch (err) {
        console.error('[auth] callback failed:', err);
      }
    }
  }

  /** Get the current access token (silent). */
  async function getToken() {
    const client = await init();
    try {
      return await client.getTokenSilently();
    } catch (err) {
      console.warn('[auth] getTokenSilently failed:', err);
      return null;
    }
  }

  /** Get the current user info from Auth0. */
  async function getUser() {
    const client = await init();
    if (!(await client.isAuthenticated())) return null;
    return await client.getUser();
  }

  /** Check if user is authenticated. */
  async function isAuthenticated() {
    const client = await init();
    return await client.isAuthenticated();
  }

  /** Login — redirect to Auth0 Universal Login. */
  async function login() {
    const client = await init();
    await client.loginWithRedirect();
  }

  /** Logout — redirect to Auth0 logout. */
  async function logout() {
    const client = await init();
    await client.logout({
      logoutParams: { returnTo: CFG.AUTH0_REDIRECT_URI },
    });
    Store.clearSession();
  }

  window.AskLTAuth = Object.freeze({
    init,
    handleRedirectCallback,
    getToken,
    getUser,
    isAuthenticated,
    login,
    logout,
  });
})();