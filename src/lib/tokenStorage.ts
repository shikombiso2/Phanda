import type { AuthTokens } from "../types/api";

const REFRESH_KEY = "phanda.refresh_token";

/**
 * Where tokens live, and why -- this needs stating explicitly because every
 * option here has a real tradeoff, not an obviously-correct one.
 *
 * ACCESS TOKEN: kept only in memory (see accessToken below), never written
 * to any Web Storage. It lives 30 minutes; keeping it out of persistent
 * storage shrinks the window in which a successful XSS payload can lift it,
 * and it simply disappears on tab close or reload rather than sitting
 * around waiting to be read.
 *
 * REFRESH TOKEN: stored in localStorage. This is the one worth pushing
 * back on, so here is the actual reasoning rather than a shrug:
 *
 * 1. The backend contract returns the refresh token in a JSON response
 *    body, not as an httpOnly Set-Cookie header. That means browser JS
 *    necessarily holds the raw token at least once, on every login and
 *    every refresh -- there is no storage location that hides it from an
 *    XSS payload running on this page, because the payload runs in the
 *    same JS context that receives the token in the first place.
 * 2. Given that, localStorage vs sessionStorage vs IndexedDB is not a
 *    security decision, it's a persistence decision -- all three are
 *    equally readable by injected script. sessionStorage would force a
 *    full re-login every time an installed PWA is closed and reopened,
 *    which defeats a real point of installing it (open it like a native
 *    app, not like a bookmark you have to re-auth into constantly) for
 *    users who are also paying per megabyte for that repeated /auth/login
 *    round trip.
 * 3. The backend's single-use rotation already bounds the damage: a
 *    stolen refresh token is worth exactly one use before it's dead, and
 *    reusing an already-rotated one revokes the session per the documented
 *    contract. That doesn't prevent theft, but it caps what theft buys.
 *
 * The real fix -- and the thing to change if this app gets a second
 * pass -- is the backend issuing the refresh token as an httpOnly, Secure,
 * SameSite=strict cookie instead of a JSON field, with CSRF protection on
 * the refresh endpoint. That removes it from JS reach entirely. That's a
 * backend contract change, not something this client can retrofit, so it's
 * flagged here rather than silently worked around.
 */
let accessToken: string | null = null;

export function getAccessToken(): string | null {
  return accessToken;
}

export function getRefreshToken(): string | null {
  return localStorage.getItem(REFRESH_KEY);
}

export function storeTokens(tokens: AuthTokens): void {
  accessToken = tokens.access_token;
  localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  accessToken = null;
  localStorage.removeItem(REFRESH_KEY);
}

export function hasSession(): boolean {
  return getRefreshToken() !== null;
}
