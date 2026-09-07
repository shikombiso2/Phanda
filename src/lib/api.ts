import type { AuthTokens, ErrorEnvelope } from "../types/api";
import { ApiError } from "./apiError";
import { clearTokens, getAccessToken, getRefreshToken, storeTokens } from "./tokenStorage";
import { signalSessionExpired } from "./sessionEvents";

const BASE_URL = import.meta.env.VITE_API_BASE_URL as string;

if (!BASE_URL) {
  // Fails loudly at import time rather than as a confusing network error
  // on the first click -- a missing .env is a setup mistake, not a runtime one.
  throw new Error("VITE_API_BASE_URL is not set. Copy .env.example to .env and fill it in.");
}

/**
 * Single-flight refresh, the JS equivalent of the mutex-plus-comparison
 * pattern: one shared module-level variable holds the in-flight refresh
 * Promise. Every caller that hits a 401 checks this variable; the first one
 * finds it empty and starts the refresh, every other one finds it already
 * set and awaits the *same* Promise instead of starting its own.
 *
 * This works without an explicit lock because JavaScript has no preemptive
 * concurrency: the "is refreshPromise set?" check and the "set it" write
 * happen in the same synchronous tick, with no `await` between them where
 * another caller could interleave. A Kotlin/JVM equivalent needs a real
 * Mutex because multiple threads can genuinely race there; here, the event
 * loop itself serialises that check-and-set.
 */
let refreshPromise: Promise<string> | null = null;

async function refreshAccessToken(): Promise<string> {
  if (refreshPromise) return refreshPromise;

  refreshPromise = (async () => {
    const refreshToken = getRefreshToken();
    if (!refreshToken) throw new ApiError(401, null);

    let response: Response;
    try {
      response = await fetch(`${BASE_URL}/auth/token/refresh`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ refresh_token: refreshToken }),
      });
    } catch (cause) {
      // A network failure during refresh says nothing about whether the
      // refresh token itself is still valid -- don't sign the user out for
      // being offline for a moment.
      throw ApiError.network(cause);
    }

    if (!response.ok) {
      const envelope = await readEnvelope(response);
      if (response.status === 401) {
        clearTokens();
        signalSessionExpired();
      }
      throw new ApiError(response.status, envelope);
    }

    const tokens = (await response.json()) as AuthTokens;
    storeTokens(tokens);
    return tokens.access_token;
  })();

  try {
    return await refreshPromise;
  } finally {
    refreshPromise = null;
  }
}

async function readEnvelope(response: Response): Promise<ErrorEnvelope | null> {
  try {
    return (await response.json()) as ErrorEnvelope;
  } catch {
    return null;
  }
}

interface RequestOptions extends Omit<RequestInit, "body"> {
  body?: unknown;
  /** false for register/login/refresh -- endpoints that must never carry
   * (or trigger a refresh of) a bearer token. */
  auth?: boolean;
}

async function request<T>(path: string, options: RequestOptions = {}, isRetry = false): Promise<T> {
  const { auth = true, body, headers, ...rest } = options;

  const finalHeaders = new Headers(headers);
  const isFormData = body instanceof FormData;
  if (body !== undefined && !isFormData) finalHeaders.set("Content-Type", "application/json");

  if (auth) {
    const token = getAccessToken();
    if (token) finalHeaders.set("Authorization", `Bearer ${token}`);
  }

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...rest,
      headers: finalHeaders,
      body: body === undefined ? undefined : isFormData ? body : JSON.stringify(body),
    });
  } catch (cause) {
    throw ApiError.network(cause);
  }

  if (response.status === 401 && auth && !isRetry) {
    try {
      await refreshAccessToken();
    } catch (refreshFailure) {
      throw refreshFailure;
    }
    return request<T>(path, options, true);
  }

  if (!response.ok) {
    const envelope = await readEnvelope(response);
    throw new ApiError(response.status, envelope);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  get: <T>(path: string, options?: RequestOptions) => request<T>(path, { ...options, method: "GET" }),
  post: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "POST", body }),
  put: <T>(path: string, body?: unknown, options?: RequestOptions) =>
    request<T>(path, { ...options, method: "PUT", body }),
};
