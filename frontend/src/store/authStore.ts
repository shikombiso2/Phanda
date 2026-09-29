import { create } from "zustand";
import { api } from "../lib/api";
import { ApiError } from "../lib/apiError";
import { clearTokens, hasSession, storeTokens } from "../lib/tokenStorage";
import { onSessionExpired, resetSessionExpiry, signalSessionExpired } from "../lib/sessionEvents";
import type { AuthTokens, ProfileOut } from "../types/api";

type Status = "checking" | "anonymous" | "authenticated";

interface AuthState {
  status: Status;
  profile: ProfileOut | null;
  error: string | null;
  bootstrap: () => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  login: (email: string, password: string) => Promise<void>;
  logout: () => void;
  setProfile: (profile: ProfileOut) => void;
  reloadProfile: () => Promise<void>;
  clearError: () => void;
}

export const useAuthStore = create<AuthState>((set) => {
  // Registered once, at store creation: when the api client's single-flight
  // refresh fails outright, this is the one place that reacts, no matter
  // how many in-flight requests were waiting on it.
  onSessionExpired(() => {
    set({ status: "anonymous", profile: null });
  });

  async function afterAuthSuccess(tokens: AuthTokens) {
    storeTokens(tokens);
    resetSessionExpiry();
    const profile = await api.get<ProfileOut>("/profile");
    set({ status: "authenticated", profile, error: null });
  }

  return {
    status: "checking",
    profile: null,
    error: null,

    async bootstrap() {
      if (!hasSession()) {
        set({ status: "anonymous" });
        return;
      }
      try {
        // No access token survives a reload (by design -- see
        // tokenStorage.ts), so this call goes out unauthenticated, gets a
        // 401, and the api client's existing refresh path handles it. No
        // separate "restore session" code path needed.
        const profile = await api.get<ProfileOut>("/profile");
        set({ status: "authenticated", profile });
      } catch (err) {
        if (err instanceof ApiError && err.isUnauthorized) {
          clearTokens();
          set({ status: "anonymous" });
        } else {
          // Offline or the backend is down at launch: don't destroy a
          // session over a network blip. Land on the login screen; the
          // user can retry once connectivity is back.
          set({ status: "anonymous" });
        }
      }
    },

    async register(email, password) {
      set({ error: null });
      try {
        const tokens = await api.post<AuthTokens>(
          "/auth/register",
          { email, password, confirm_password: password },
          { auth: false },
        );
        await afterAuthSuccess(tokens);
      } catch (err) {
        set({ error: err instanceof ApiError ? err.displayMessage : "Something went wrong. Try again." });
        throw err;
      }
    },

    async login(email, password) {
      set({ error: null });
      try {
        const tokens = await api.post<AuthTokens>("/auth/login", { email, password }, { auth: false });
        await afterAuthSuccess(tokens);
      } catch (err) {
        set({ error: err instanceof ApiError ? err.displayMessage : "Something went wrong. Try again." });
        throw err;
      }
    },

    logout() {
      clearTokens();
      signalSessionExpired();
    },

    setProfile(profile) {
      set({ profile });
    },

    async reloadProfile() {
      const profile = await api.get<ProfileOut>("/profile");
      set({ profile });
    },

    clearError() {
      set({ error: null });
    },
  };
});
