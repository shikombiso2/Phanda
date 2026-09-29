import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { AppNav, BOTTOM_NAV_SPACER_CLASS } from "../components/AppNav";
import { ApplyCvChoiceModal } from "../components/ApplyCvChoiceModal";
import { Button } from "../components/Button";
import { ProgressState } from "../components/ProgressState";
import { ChevronLeftIcon, HeartIcon } from "../components/icons";
import { api } from "../lib/api";
import { ApiError } from "../lib/apiError";
import { renderMarkdown } from "../lib/markdown";
import { parseMultiLocation, parseMultiOfficeApplyTarget } from "../lib/multiLocation";
import { formatSalary } from "../lib/salary";
import { useAuthStore } from "../store/authStore";
import { useSavedStore } from "../store/savedStore";
import type { ApplyOut, CvVersionOut, Listing, MatchExplanation } from "../types/api";

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
  const profile = useAuthStore((s) => s.profile);

  const [listing, setListing] = useState<Listing | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  const [applyState, setApplyState] = useState<
    { phase: "idle" } | { phase: "applying" } | { phase: "done"; result: ApplyOut } | { phase: "error"; message: string; status: number }
  >({ phase: "idle" });

  // Whether the CV-choice popup should even be an option -- null while
  // still checking. false covers BOTH "no CV at all" and "CV not ready
  // yet"; either way there's only one usable path (today's existing
  // upload-a-CV fallback), so the popup must never appear offering a choice
  // between something usable and something that isn't.
  const [cvReady, setCvReady] = useState<boolean | null>(null);
  const [showCvChoice, setShowCvChoice] = useState(false);

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

  useEffect(() => {
    if (!profile) return;
    if (!profile.active_cv_version_id) {
      setCvReady(false);
      return;
    }
    api
      .get<CvVersionOut>(`/profile/cv-versions/${profile.active_cv_version_id}`)
      .then((version) => setCvReady(version.status === "ready"))
      .catch(() => setCvReady(false));
  }, [profile]);

  async function handleApply(tailoredDocumentId?: string) {
    if (!id) return;
    setApplyState({ phase: "applying" });
    try {
      const result = await api.post<ApplyOut>(
        `/applications/${id}/apply`,
        tailoredDocumentId ? { tailored_document_id: tailoredDocumentId } : undefined,
        { headers: { "Idempotency-Key": crypto.randomUUID() } },
      );
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

  // Universal across every apply_method -- email/ats_link's "Apply" and
  // manual/DPSA's "Mark as applied" both go through the same CV-choice
  // popup before anything is submitted. Skipped entirely (falls straight
  // to today's existing behaviour) when there's no ready CV to choose
  // between at all.
  function handleApplyButtonClick() {
    if (cvReady) {
      setShowCvChoice(true);
    } else {
      handleApply();
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
          <Button variant="secondary" className="mt-4" onClick={() => navigate("/find")}>
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
            <ListingLocationLine company={listing.company} location={listing.location} />
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

        {listing.apply_method === "manual" && (
          <div className="mt-6 rounded-2xl border border-phanda-gold-dark/30 bg-phanda-gold/10 p-4">
            <p className="font-body text-[15px] font-semibold text-phanda-gold-dark">Government application form required</p>
            <p className="mt-1 font-body text-sm leading-relaxed text-ink/70">
              This post requires the official Z83 government application form, not just a CV -- Phanda can't submit this
              one for you. Complete the Z83 (linked below) and send it yourself to the address shown.
            </p>
            <ApplyTargetBox target={listing.apply_target} />
          </div>
        )}

        <div className="mt-6">
          <h2 className="font-body text-sm font-semibold text-ink">About this role</h2>
          <div className="mt-2">{renderMarkdown(listing.description)}</div>
        </div>

        <div className="mt-8 border-t border-hairline pt-6">
          {applyState.phase === "done" ? (
            <ApplyConfirmation result={applyState.result} />
          ) : (
            <>
              <Button className="w-full" loading={applyState.phase === "applying"} onClick={handleApplyButtonClick}>
                {listing.apply_method === "manual" ? "Mark as applied" : "Apply"}
              </Button>
              {listing.apply_method === "manual" && applyState.phase !== "applying" && (
                <p className="mt-2 text-center font-body text-xs text-ink/50">
                  Only tap this once you've actually sent your Z83 application yourself.
                </p>
              )}
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

      {showCvChoice && id && (
        <ApplyCvChoiceModal
          listingId={id}
          onClose={() => setShowCvChoice(false)}
          onContinueWithCurrent={() => {
            setShowCvChoice(false);
            handleApply();
          }}
          onTailoredReady={(tailoredDocumentId) => {
            setShowCvChoice(false);
            handleApply(tailoredDocumentId);
          }}
        />
      )}
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
  const confirmationCopy: Record<ApplyOut["apply_method"], string> = {
    email: "We've sent your application",
    ats_link: "Your application is on its way",
    // Deliberately makes no claim that anything was sent -- nothing was.
    // This just records that the user says they've completed it themselves.
    manual: "Marked as applied",
  };

  return (
    <div className="rounded-2xl border border-hairline bg-mist p-5 text-center">
      <p className="font-body text-[15px] font-semibold text-ink">{confirmationCopy[result.apply_method]}</p>
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
      {result.apply_method === "manual" && (
        <p className="mt-3 font-body text-xs text-ink/50">
          Update this to "Applied" in Track once you've actually sent your Z83 form.
        </p>
      )}
      <div className="mt-3">
        <Link to="/track" className="font-body text-sm font-semibold text-phanda-green-dark hover:underline">
          View in Track
        </Link>
      </div>
    </div>
  );
}

/**
 * DPSA-specific: some posts are filled at several named locations at once
 * (see lib/multiLocation.ts). Collapsed to a count by default -- the raw
 * concatenated string is unreadable as a single line -- with a toggle to
 * see each location's own reference number. Falls back to the plain
 * company/location line exactly as before when the pattern isn't detected.
 */
function ListingLocationLine({ company, location }: { company: string | null; location: string | null }) {
  const entries = parseMultiLocation(location);
  const [expanded, setExpanded] = useState(false);

  if (!entries) {
    return (
      <p className="mt-1 font-body text-[15px] text-ink/60">{[company, location].filter(Boolean).join(" · ")}</p>
    );
  }

  return (
    <div className="mt-1">
      <p className="font-body text-[15px] text-ink/60">
        {company && `${company} · `}
        <button
          onClick={() => setExpanded((v) => !v)}
          className="font-semibold text-ink underline decoration-dotted underline-offset-2"
        >
          {entries.length} locations available
        </button>
      </p>
      {expanded && (
        <ul className="mt-2 flex flex-col gap-1.5 rounded-[10px] border border-hairline bg-mist px-3.5 py-3">
          {entries.map((entry) => (
            <li key={`${entry.place}-${entry.refNo}`} className="font-body text-sm text-ink/75">
              <span className="font-semibold text-ink">{entry.place}</span> — Ref No: {entry.refNo}
              {entry.postCount != null && ` (${entry.postCount} post${entry.postCount === 1 ? "" : "s"})`}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

const APPLY_TARGET_COLLAPSE_THRESHOLD = 320;

/**
 * Same idea for apply_target: some DPSA posts concatenate a separate full
 * office address per province (e.g. one address for a Gauteng-based slot,
 * another for a Limpopo-based one). Recognised cases collapse behind an
 * "N offices" toggle; anything merely long but unrecognised still collapses
 * behind a plain "Show full details" toggle rather than dumping the raw
 * block -- only a short, ordinary target renders unchanged.
 */
function ApplyTargetBox({ target }: { target: string | null }) {
  const offices = parseMultiOfficeApplyTarget(target);
  const [expanded, setExpanded] = useState(false);

  if (!target) return null;

  if (offices) {
    return (
      <div className="mt-3 rounded-[10px] border border-hairline bg-paper px-3.5 py-3">
        <div className="flex items-center justify-between gap-3">
          <p className="font-body text-xs font-semibold uppercase tracking-wide text-ink/40">Send your application to</p>
          <button
            onClick={() => setExpanded((v) => !v)}
            className="shrink-0 font-body text-xs font-semibold text-phanda-gold-dark underline"
          >
            {expanded ? "Hide" : `${offices.length} offices`}
          </button>
        </div>
        {expanded ? (
          <div className="mt-2 flex flex-col gap-3">
            {offices.map((office) => (
              <div key={office.province}>
                <p className="font-body text-xs font-bold uppercase tracking-wide text-ink/50">{office.province}</p>
                <p className="mt-0.5 font-body text-sm font-medium text-ink">
                  {office.text.replace(new RegExp(`^${office.province}\\s*:\\s*`), "")}
                </p>
              </div>
            ))}
          </div>
        ) : (
          <p className="mt-1 font-body text-sm text-ink/60">
            Depends on which location's post you applied for -- tap to see all {offices.length}.
          </p>
        )}
      </div>
    );
  }

  const isLong = target.length > APPLY_TARGET_COLLAPSE_THRESHOLD;
  return (
    <div className="mt-3 rounded-[10px] border border-hairline bg-paper px-3.5 py-3">
      <div className="flex items-center justify-between gap-3">
        <p className="font-body text-xs font-semibold uppercase tracking-wide text-ink/40">Send your application to</p>
        {isLong && (
          <button
            onClick={() => setExpanded((v) => !v)}
            className="shrink-0 font-body text-xs font-semibold text-phanda-gold-dark underline"
          >
            {expanded ? "Show less" : "Show full details"}
          </button>
        )}
      </div>
      <p className={`mt-1 font-body text-sm font-medium text-ink ${!expanded && isLong ? "line-clamp-3" : ""}`}>
        {target}
      </p>
    </div>
  );
}
