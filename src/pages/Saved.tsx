import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AppNav, BOTTOM_NAV_SPACER_CLASS } from "../components/AppNav";
import { Button } from "../components/Button";
import { ListingCard } from "../components/ListingCard";
import { ProgressState } from "../components/ProgressState";
import { HeartIcon } from "../components/icons";
import { api } from "../lib/api";
import { ApiError } from "../lib/apiError";
import { buildQueryString } from "../lib/queryString";
import { useSavedStore } from "../store/savedStore";
import type { Listing, Page } from "../types/api";

const PAGE_SIZE = 20;

export function Saved() {
  const toggleSaved = useSavedStore((s) => s.toggle);

  const [rows, setRows] = useState<Listing[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchPage = useCallback(async (offset: number, replace: boolean) => {
    const page = await api.get<Page<Listing>>(`/saved-opportunities${buildQueryString({ limit: PAGE_SIZE, offset })}`);
    setRows((prev) => (replace ? page.items : [...prev, ...page.items]));
    setTotal(page.total);
    setHasMore(page.has_more);
  }, []);

  useEffect(() => {
    setLoading(true);
    fetchPage(0, true)
      .catch((err) => setError(err instanceof ApiError ? err.displayMessage : "Couldn't load your saved listings."))
      .finally(() => setLoading(false));
  }, [fetchPage]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      await fetchPage(rows.length, false);
    } catch (err) {
      setError(err instanceof ApiError ? err.displayMessage : "Couldn't load more.");
    } finally {
      setLoadingMore(false);
    }
  }

  async function handleUnsave(listingId: string) {
    // This list *is* "things you saved" -- unlike Find, removing the save
    // here should remove the card, not just swap the heart icon.
    const removed = rows.find((r) => r.id === listingId);
    setRows((prev) => prev.filter((r) => r.id !== listingId));
    setTotal((prev) => prev - 1);
    try {
      await toggleSaved(listingId);
    } catch {
      if (removed) {
        setRows((prev) => [removed, ...prev]);
        setTotal((prev) => prev + 1);
      }
    }
  }

  return (
    <div className="min-h-screen bg-paper">
      <AppNav />
      <main className={`mx-auto max-w-3xl px-5 py-6 sm:px-8 ${BOTTOM_NAV_SPACER_CLASS}`}>
        <h1 className="font-display text-2xl font-black tracking-tight text-ink">Saved</h1>

        <div className="mt-6 flex flex-col gap-4">
          {loading && <ProgressState label="Loading your saved listings..." />}

          {!loading && error && (
            <div className="flex flex-col items-center gap-3 rounded-2xl border border-hairline px-6 py-12 text-center">
              <p className="font-body text-sm text-ink/60">{error}</p>
            </div>
          )}

          {!loading && !error && rows.length === 0 && (
            <div className="flex flex-col items-center gap-3 rounded-2xl border border-hairline px-6 py-16 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-mist text-ink/40">
                <HeartIcon className="h-8 w-8" />
              </div>
              <h2 className="mt-2 font-display text-xl font-black tracking-tight text-ink">Nothing saved yet</h2>
              <p className="max-w-xs font-body text-[15px] text-ink/65">
                Tap the heart on any listing to keep it here for later.
              </p>
              <Link to="/find">
                <Button variant="secondary">Find listings</Button>
              </Link>
            </div>
          )}

          {!loading &&
            !error &&
            rows.map((listing) => (
              <ListingCard key={listing.id} listing={listing} saved onToggleSave={() => handleUnsave(listing.id)} />
            ))}

          {!loading && !error && rows.length > 0 && (
            <div className="mt-2 flex flex-col items-center gap-2">
              <p className="font-body text-sm text-ink/40">
                Showing {rows.length} of {total}
              </p>
              {hasMore && (
                <Button variant="secondary" loading={loadingMore} onClick={loadMore}>
                  Load more
                </Button>
              )}
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
