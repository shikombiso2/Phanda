import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { AppNav, BOTTOM_NAV_SPACER_CLASS } from "../components/AppNav";
import { Button } from "../components/Button";
import { ProgressState } from "../components/ProgressState";
import { ChevronLeftIcon, HeartIcon } from "../components/icons";
import { api } from "../lib/api";
import { ApiError } from "../lib/apiError";
import { formatSalary } from "../lib/salary";
import { useSavedStore } from "../store/savedStore";
import type { ApplyOut, Listing, MatchExplanation } from "../types/api";

const LISTING_TYPE_LABEL: Record<string, string> = {
  job: "Job",
  internship: "Internship",
  learnership: "Learnership",
  apprenticeship: "Apprenticeship",
  bursary: "Bursary",
};

interface LocationState {
  match?: MatchExplanation;
}

export function ListingDetail() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const match = (location.state as LocationState | null)?.match;

  const isSaved = useSavedStore((s) => (id ? s.isSaved(id) : false));
  const toggleSaved = useSavedStore((s) => s.toggle);

  const [listing, setListing] = useState<Listing | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [applyState, setApplyState] = useState<
    { phase: "idle" } | { phase: "applying" } | { phase: "done"; result: ApplyOut } | { phase: "error"; message: string; status: number }
  >({ phase: "idle" });

  useEffect(() => {
    if (!id) return;
    setLoading(true);
    setLoadError(null);
    api
      .get<Listing>(`/listings/${id}`)
      .then(setListing)
      .catch((err) => setLoadError(err instanceof ApiError ? err.displayMessage : "Couldn't load this listing."))
      .finally(() => setLoading(false));
  }, [id]);

  async function handleApply() {
    if (!id) return;
    setApplyState({ phase: "applying" });
    try {
      const result = await api.post<ApplyOut>(`/applications/${id}/apply`, undefined, {
        headers: { "Idempotency-Key": crypto.randomUUID() },
      });
      setApplyState({ phase: "done", result });
    } catch (err) {
      const apiError = err instanceof ApiError ? err : null;
      setApplyState({
        phase: "error",
        message: apiError?.displayMessage ?? "Couldn't apply right now. Try again.",
        status: apiError?.status ?? 0,
      });
    }
  }

  if (loading) {
    return (
      <div className="min-h-screen bg-paper">
        <AppNav />
        <main className={`mx-auto max-w-2xl px-5 py-12 sm:px-8 ${BOTTOM_NAV_SPACER_CLASS}`}>
          <ProgressState label="Loading listing..." />
        </main>
      </div>
    );
  }

  if (loadError || !listing) {
    return (
      <div className="min-h-screen bg-paper">
        <AppNav />
        <main className={`mx-auto max-w-2xl px-5 py-12 text-center sm:px-8 ${BOTTOM_NAV_SPACER_CLASS}`}>
          <p className="font-body text-[15px] font-semibold text-ink">
            {loadError ?? "This listing isn't available anymore."}
          </p>
          <Button variant="secondary" className="mt-4" onClick={() => navigate("/home")}>
            Back to Find
          </Button>
        </main>
      </div>
    );
  }

  const salary = formatSalary(listing.salary_min, listing.salary_max, listing.salary_period, listing.salary_currency);

  return (
    <div className="min-h-screen bg-paper">
      <AppNav />
      <main className={`mx-auto max-w-2xl px-5 py-8 sm:px-8 ${BOTTOM_NAV_SPACER_CLASS}`}>
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1 font-body text-sm font-medium text-ink/60 hover:text-ink"
        >
          <ChevronLeftIcon className="h-4 w-4" />
          Back
        </button>

        <div className="mt-4 flex items-start justify-between gap-4">
          <div>
            {match && (
              <span className="mb-2 inline-block rounded-full bg-phanda-green/10 px-2.5 py-1 font-body text-xs font-bold text-phanda-green-dark">
                {match.score}% match
              </span>
            )}
            <h1 className="font-display text-2xl font-black tracking-tight text-ink sm:text-3xl">{listing.title}</h1>
            <p className="mt-1 font-body text-[15px] text-ink/60">
              {[listing.company, listing.location].filter(Boolean).join(" · ")}
            </p>
          </div>
          <button
            onClick={() => toggleSaved(listing.id).catch(() => {})}
            aria-label={isSaved ? "Remove from saved" : "Save this listing"}
            aria-pressed={isSaved}
            className={`shrink-0 rounded-full p-2 transition-colors ${isSaved ? "text-phanda-green" : "text-ink/30 hover:text-ink/60"}`}
          >
            <HeartIcon className="h-6 w-6" filled={isSaved} />
          </button>
        </div>

        <div className="mt-3 flex flex-wrap items-center gap-x-4 gap-y-1">
          <span className="font-body text-sm font-medium text-ink/50">
            {LISTING_TYPE_LABEL[listing.listing_type] ?? listing.listing_type}
          </span>
          {salary && <span className="font-body text-sm font-medium text-ink/50">{salary}</span>}
        </div>

        {match && <MatchBreakdown match={match} />}

        {listing.required_skills.length > 0 && (
          <div className="mt-6">
            <h2 className="font-body text-sm font-semibold text-ink">Skills</h2>
            <div className="mt-2 flex flex-wrap gap-1.5">
              {listing.required_skills.map((skill) => (
                <span key={skill} className="rounded-full bg-mist px-2.5 py-1 font-body text-xs text-ink/70">
                  {skill}
                </span>
              ))}
            </div>
          </div>
        )}

        <div className="mt-6">
          <h2 className="font-body text-sm font-semibold text-ink">About this role</h2>
          <p className="mt-2 whitespace-pre-line font-body text-[15px] leading-relaxed text-ink/75">
            {listing.description}
          </p>
        </div>

        <div className="mt-8 border-t border-hairline pt-6">
          {applyState.phase === "done" ? (
            <ApplyConfirmation result={applyState.result} />
          ) : (
            <>
              <Button className="w-full" loading={applyState.phase === "applying"} onClick={handleApply}>
                Apply
              </Button>
              {applyState.phase === "error" && (
                <div className="mt-3 rounded-[10px] bg-signal-soft px-4 py-3">
                  <p className="font-body text-sm font-medium text-signal">{applyState.message}</p>
                  {applyState.status === 400 && (
                    <Link to="/onboarding/cv" className="mt-1 inline-block font-body text-sm font-semibold text-signal underline">
                      Upload a CV
                    </Link>
                  )}
                </div>
              )}
            </>
          )}
        </div>
      </main>
    </div>
  );
}

function MatchBreakdown({ match }: { match: MatchExplanation }) {
  return (
    <div className="mt-5 rounded-2xl border border-hairline p-4">
      <p className="font-body text-[15px] text-ink/75">{match.summary}</p>

      {match.matched_skills.length > 0 && (
        <div className="mt-3">
          <p className="font-body text-xs font-semibold uppercase text-ink/40">You have</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {match.matched_skills.map((skill) => (
              <span key={skill} className="rounded-full bg-phanda-green/10 px-2.5 py-1 font-body text-xs text-phanda-green-dark">
                {skill}
              </span>
            ))}
          </div>
        </div>
      )}

      {match.missing_skills.length > 0 && (
        <div className="mt-3">
          <p className="font-body text-xs font-semibold uppercase text-ink/40">Not on your profile yet</p>
          <div className="mt-1.5 flex flex-wrap gap-1.5">
            {match.missing_skills.map((skill) => (
              <span key={skill} className="rounded-full bg-mist px-2.5 py-1 font-body text-xs text-ink/50">
                {skill}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="mt-4 flex flex-col gap-2">
        {match.factors.map((factor) => (
          <div key={factor.key} className="flex items-center gap-3">
            <span className="w-28 shrink-0 font-body text-xs text-ink/60">{factor.label}</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-mist">
              <div
                className="h-full rounded-full bg-phanda-green"
                style={{ width: `${Math.round(factor.probability * 100)}%` }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}

function ApplyConfirmation({ result }: { result: ApplyOut }) {
  return (
    <div className="rounded-2xl border border-hairline bg-mist p-5 text-center">
      <p className="font-body text-[15px] font-semibold text-ink">
        {result.apply_method === "email" ? "We've sent your application" : "Your application is on its way"}
      </p>
      <p className="mt-1 font-body text-sm text-ink/60">Status: {result.status.replace("_", " ")}</p>
      {result.apply_method === "ats_link" && result.apply_target && (
        <a
          href={result.apply_target}
          target="_blank"
          rel="noreferrer"
          className="mt-4 inline-block rounded-[10px] bg-phanda-green px-5 py-2.5 font-body text-sm font-semibold text-white hover:bg-phanda-green-dark"
        >
          Finish on the employer's site
        </a>
      )}
      <div className="mt-3">
        <Link to="/track" className="font-body text-sm font-semibold text-phanda-green-dark hover:underline">
          View in Track
        </Link>
      </div>
    </div>
  );
}
