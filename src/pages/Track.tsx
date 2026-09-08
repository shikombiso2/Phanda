import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AppNav, BOTTOM_NAV_SPACER_CLASS } from "../components/AppNav";
import { Button } from "../components/Button";
import { ProgressState } from "../components/ProgressState";
import { TrackIcon } from "../components/icons";
import { api } from "../lib/api";
import { ApiError } from "../lib/apiError";
import { buildQueryString } from "../lib/queryString";
import type { ApplicationOut, ApplicationStatus, Page } from "../types/api";

const PAGE_SIZE = 20;

const STATUS_LABEL: Record<ApplicationStatus, string> = {
  prepared: "Prepared",
  external_started: "Started",
  applied: "Applied",
  interview: "Interview",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

const STATUS_OPTIONS = Object.keys(STATUS_LABEL) as ApplicationStatus[];

export function Track() {
  const [rows, setRows] = useState<ApplicationOut[]>([]);
  const [total, setTotal] = useState(0);
  const [hasMore, setHasMore] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [rowErrors, setRowErrors] = useState<Record<string, string>>({});

  const fetchPage = useCallback(async (offset: number, replace: boolean) => {
    const page = await api.get<Page<ApplicationOut>>(`/applications${buildQueryString({ limit: PAGE_SIZE, offset })}`);
    setRows((prev) => (replace ? page.items : [...prev, ...page.items]));
    setTotal(page.total);
    setHasMore(page.has_more);
  }, []);

  useEffect(() => {
    setLoading(true);
    fetchPage(0, true)
      .catch((err) => setError(err instanceof ApiError ? err.displayMessage : "Couldn't load your applications."))
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

  async function changeStatus(applicationId: string, status: ApplicationStatus) {
    const previous = rows.find((r) => r.id === applicationId)?.status;
    setRows((prev) => prev.map((r) => (r.id === applicationId ? { ...r, status } : r)));
    setRowErrors((prev) => ({ ...prev, [applicationId]: "" }));
    try {
      await api.patch(`/applications/${applicationId}`, { status });
    } catch (err) {
      if (previous) setRows((prev) => prev.map((r) => (r.id === applicationId ? { ...r, status: previous } : r)));
      setRowErrors((prev) => ({
        ...prev,
        [applicationId]: err instanceof ApiError ? err.displayMessage : "Couldn't update status.",
      }));
    }
  }

  return (
    <div className="min-h-screen bg-paper">
      <AppNav />
      <main className={`mx-auto max-w-3xl px-5 py-6 sm:px-8 ${BOTTOM_NAV_SPACER_CLASS}`}>
        <h1 className="font-display text-2xl font-black tracking-tight text-ink">Track</h1>

        <div className="mt-6 flex flex-col gap-3">
          {loading && <ProgressState label="Loading your applications..." />}

          {!loading && error && (
            <div className="flex flex-col items-center gap-3 rounded-2xl border border-hairline px-6 py-12 text-center">
              <p className="font-body text-sm text-ink/60">{error}</p>
            </div>
          )}

          {!loading && !error && rows.length === 0 && (
            <div className="flex flex-col items-center gap-3 rounded-2xl border border-hairline px-6 py-16 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-mist text-ink/40">
                <TrackIcon className="h-8 w-8" />
              </div>
              <h2 className="mt-2 font-display text-xl font-black tracking-tight text-ink">
                You haven't applied to anything yet
              </h2>
              <p className="max-w-xs font-body text-[15px] text-ink/65">
                Once you apply to a listing, you'll be able to follow its progress here.
              </p>
              <Link to="/home">
                <Button variant="secondary">Find opportunities</Button>
              </Link>
            </div>
          )}

          {!loading &&
            !error &&
            rows.map((application) => (
              <div key={application.id} className="rounded-2xl border border-hairline p-4 sm:p-5">
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div>
                    <Link
                      to={`/listings/${application.listing_id}`}
                      className="font-body text-[15px] font-semibold text-ink hover:underline"
                    >
                      {application.listing.title}
                    </Link>
                    <p className="mt-0.5 font-body text-sm text-ink/60">
                      {[application.listing.company, application.listing.location].filter(Boolean).join(" · ")}
                    </p>
                  </div>
                  <select
                    value={application.status}
                    onChange={(e) => changeStatus(application.id, e.target.value as ApplicationStatus)}
                    aria-label={`Status for ${application.listing.title}`}
                    className="rounded-[10px] border border-hairline bg-paper px-3 py-2 font-body text-sm text-ink outline-none focus:border-phanda-green"
                  >
                    {STATUS_OPTIONS.map((status) => (
                      <option key={status} value={status}>
                        {STATUS_LABEL[status]}
                      </option>
                    ))}
                  </select>
                </div>
                {rowErrors[application.id] && (
                  <p className="mt-2 font-body text-sm font-medium text-signal">{rowErrors[application.id]}</p>
                )}
              </div>
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
