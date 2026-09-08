import { useCallback, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { AppNav, BOTTOM_NAV_SPACER_CLASS } from "../components/AppNav";
import { Button } from "../components/Button";
import { ListingCard } from "../components/ListingCard";
import { ListingFilters, type ListingFilterValues } from "../components/ListingFilters";
import { ProgressState } from "../components/ProgressState";
import { DiggingSearchIcon } from "../components/icons";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import { api } from "../lib/api";
import { ApiError } from "../lib/apiError";
import { buildQueryString } from "../lib/queryString";
import { useAuthStore } from "../store/authStore";
import { useSavedStore } from "../store/savedStore";
import type { ListingSummary, MatchedListing, Page } from "../types/api";

const PAGE_SIZE = 20;
const EMPTY_FILTERS: ListingFilterValues = { q: "", type: "", location: "", remote: false };

interface OnboardingIssueState {
  onboardingIssue?: "profile" | "cv" | "both";
}

const ISSUE_MESSAGES: Record<"profile" | "cv" | "both", string> = {
  profile: "Your account is ready, but we couldn't save your profile answers. You can add them from your Profile tab.",
  cv: "Your account is ready, but we couldn't process your CV. You can upload it again from your Profile tab.",
  both: "Your account is ready, but we couldn't save your profile or your CV. You can finish both from your Profile tab.",
};

type Row = ListingSummary | MatchedListing;

function hasMatch(row: Row): row is MatchedListing {
  return "match" in row;
}

export function Find() {
  const location = useLocation();
  const profile = useAuthStore((s) => s.profile);
  const savedIds = useSavedStore((s) => s.ids);
  const ensureSavedLoaded = useSavedStore((s) => s.ensureLoaded);
  const toggleSaved = useSavedStore((s) => s.toggle);

  const [dismissedNotice, setDismissedNotice] = useState(false);
  const onboardingIssue = (location.state as OnboardingIssueState | null)?.onboardingIssue;

  const [filters, setFilters] = useState<ListingFilterValues>(EMPTY_FILTERS);
  const debouncedQ = useDebouncedValue(filters.q, 400);

  const hasSkills = (profile?.skills.length ?? 0) > 0;
  const hasActiveFilters = debouncedQ.trim() !== "" || filters.type !== "" || filters.location.trim() !== "" || filters.remote;
  // Personalised matching only exists on GET /listings/matches, and that
  // endpoint takes no q/type/location/remote params at all -- it can't be
  // searched or filtered server-side. So the moment the user searches or
  // sets a filter, this switches to the plain listings endpoint, which
  // does support them. Matching is the resting state; searching is its
  // own mode. See the chat report for why matches has no filter support.
  const mode: "matches" | "search" = !hasActiveFilters && hasSkills ? "matches" : "search";

  const [rows, setRows] = useState<Row[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    ensureSavedLoaded();
  }, [ensureSavedLoaded]);

  const fetchPage = useCallback(
    async (offset: number, replace: boolean) => {
      const path =
        mode === "matches"
          ? `/listings/matches${buildQueryString({ limit: PAGE_SIZE, offset })}`
          : `/listings${buildQueryString({
              q: debouncedQ.trim() || undefined,
              type: filters.type || undefined,
              location: filters.location.trim() || undefined,
              remote: filters.remote || undefined,
              limit: PAGE_SIZE,
              offset,
            })}`;

      const page = await api.get<Page<Row>>(path);
      setRows((prev) => (replace ? page.items : [...prev, ...page.items]));
      setTotal(page.total);
      setHasMore(page.has_more);
    },
    [mode, debouncedQ, filters.type, filters.location, filters.remote],
  );

  useEffect(() => {
    setLoading(true);
    setError(null);
    fetchPage(0, true)
      .catch((err) => setError(err instanceof ApiError ? err.displayMessage : "Couldn't load listings. Try again."))
      .finally(() => setLoading(false));
  }, [fetchPage]);

  async function loadMore() {
    setLoadingMore(true);
    try {
      await fetchPage(rows.length, false);
    } catch (err) {
      setError(err instanceof ApiError ? err.displayMessage : "Couldn't load more listings. Try again.");
    } finally {
      setLoadingMore(false);
    }
  }

  async function handleToggleSave(listingId: string) {
    try {
      await toggleSaved(listingId);
    } catch {
      // The store already reverted the optimistic change; nothing further
      // to reconcile. A silent failure here (try again by tapping once
      // more) is preferable to interrupting a scroll session with a toast.
    }
  }

  return (
    <div className="min-h-screen bg-paper">
      <AppNav />

      {onboardingIssue && !dismissedNotice && (
        <div className="mx-auto mt-6 flex max-w-3xl items-start justify-between gap-4 rounded-[10px] bg-signal-soft px-5 py-4">
          <p className="font-body text-sm font-medium text-signal">{ISSUE_MESSAGES[onboardingIssue]}</p>
          <button
            onClick={() => setDismissedNotice(true)}
            aria-label="Dismiss"
            className="shrink-0 font-body text-sm font-medium text-signal/70 hover:text-signal"
          >
            Dismiss
          </button>
        </div>
      )}

      {!hasSkills && (
        <div className="mx-auto mt-6 flex max-w-3xl flex-wrap items-center justify-between gap-3 rounded-[10px] bg-mist px-5 py-4">
          <p className="font-body text-sm text-ink/70">Add your skills for job matches picked just for you.</p>
          <Link to="/onboarding/profile" className="shrink-0 font-body text-sm font-semibold text-phanda-green-dark hover:underline">
            Complete profile
          </Link>
        </div>
      )}

      <main className={`mx-auto max-w-3xl px-5 py-6 sm:px-8 ${BOTTOM_NAV_SPACER_CLASS}`}>
        <h1 className="font-display text-2xl font-black tracking-tight text-ink">
          {mode === "matches" ? "Matched for you" : "Find work"}
        </h1>

        <div className="mt-4">
          <ListingFilters values={filters} onChange={setFilters} />
        </div>

        <div className="mt-6 flex flex-col gap-4">
          {loading && <ProgressState label="Finding listings..." />}

          {!loading && error && (
            <div className="flex flex-col items-center gap-3 rounded-2xl border border-hairline px-6 py-12 text-center">
              <p className="font-body text-[15px] font-semibold text-ink">Couldn't load listings</p>
              <p className="font-body text-sm text-ink/60">{error}</p>
              <Button
                variant="secondary"
                onClick={() => {
                  setLoading(true);
                  setError(null);
                  fetchPage(0, true)
                    .catch((err) => setError(err instanceof ApiError ? err.displayMessage : "Couldn't load listings. Try again."))
                    .finally(() => setLoading(false));
                }}
              >
                Try again
              </Button>
            </div>
          )}

          {!loading && !error && rows.length === 0 && (
            <div className="flex flex-col items-center gap-3 rounded-2xl border border-hairline px-6 py-16 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-mist text-ink/40">
                <DiggingSearchIcon className="h-9 w-9" />
              </div>
              <h2 className="mt-2 font-display text-xl font-black tracking-tight text-ink">
                {hasActiveFilters ? "No listings match that search" : "Nothing here yet"}
              </h2>
              <p className="max-w-xs font-body text-[15px] text-ink/65">
                {hasActiveFilters
                  ? "Try a broader search, or clear your filters to see everything available."
                  : "Check back soon -- new listings are added regularly."}
              </p>
              {hasActiveFilters && (
                <Button variant="secondary" onClick={() => setFilters(EMPTY_FILTERS)}>
                  Clear filters
                </Button>
              )}
            </div>
          )}

          {!loading &&
            !error &&
            rows.map((row) => (
              <ListingCard
                key={row.id}
                listing={row}
                match={hasMatch(row) ? row.match : undefined}
                saved={savedIds.has(row.id)}
                onToggleSave={() => handleToggleSave(row.id)}
              />
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
