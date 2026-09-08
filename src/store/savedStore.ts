import { create } from "zustand";
import { api } from "../lib/api";
import { buildQueryString } from "../lib/queryString";
import type { Listing, Page } from "../types/api";

interface SavedState {
  ids: Set<string>;
  loaded: boolean;
  loading: boolean;
  /** Loads every saved listing id once per session, so Find/Search cards
   * know whether to show a filled or outline heart without an API round
   * trip per card. Saved lists are small at this product's stage (a
   * handful to a few dozen), so paging through all of them once is cheap;
   * this is not meant to scale to thousands. */
  ensureLoaded: () => Promise<void>;
  isSaved: (listingId: string) => boolean;
  /** Optimistic: flips local state immediately, then confirms with the
   * server. Reverts on failure and rethrows so the caller can show an
   * inline error. */
  toggle: (listingId: string) => Promise<void>;
}

export const useSavedStore = create<SavedState>((set, get) => ({
  ids: new Set(),
  loaded: false,
  loading: false,

  async ensureLoaded() {
    if (get().loaded || get().loading) return;
    set({ loading: true });
    try {
      const ids = new Set<string>();
      let offset = 0;
      const limit = 100;
      // The saved list is public browsing history for one user, not a
      // dataset -- a handful of pages at most in practice.
      for (let guard = 0; guard < 50; guard++) {
        const page = await api.get<Page<Listing>>(`/saved-opportunities${buildQueryString({ limit, offset })}`);
        for (const listing of page.items) ids.add(listing.id);
        if (!page.has_more) break;
        offset += limit;
      }
      set({ ids, loaded: true, loading: false });
    } catch {
      // Leave `loaded` false so a later call retries; hearts just default
      // to "not saved" in the meantime rather than blocking the page.
      set({ loading: false });
    }
  },

  isSaved(listingId) {
    return get().ids.has(listingId);
  },

  async toggle(listingId) {
    const wasSaved = get().ids.has(listingId);
    set((state) => {
      const next = new Set(state.ids);
      if (wasSaved) next.delete(listingId);
      else next.add(listingId);
      return { ids: next };
    });
    try {
      if (wasSaved) await api.del(`/saved-opportunities/${listingId}`);
      else await api.post(`/saved-opportunities/${listingId}`);
    } catch (err) {
      // Revert the optimistic flip.
      set((state) => {
        const next = new Set(state.ids);
        if (wasSaved) next.add(listingId);
        else next.delete(listingId);
        return { ids: next };
      });
      throw err;
    }
  },
}));
