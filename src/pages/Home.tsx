import { useEffect, useState, type ReactNode } from "react";
import { Link, useLocation } from "react-router-dom";
import { AppNav, BOTTOM_NAV_SPACER_CLASS } from "../components/AppNav";
import { Button } from "../components/Button";
import { ProgressState } from "../components/ProgressState";
import { DiggingSearchIcon, SpinnerIcon } from "../components/icons";
import { api } from "../lib/api";
import { ApiError } from "../lib/apiError";
import { buildQueryString } from "../lib/queryString";
import { useAuthStore } from "../store/authStore";
import type { MatchedListing, Page, ProfileOut, RoadmapOut } from "../types/api";

const MATCHES_SAMPLE_SIZE = 10;
const ROW_COUNT = 3;

interface OnboardingIssueState {
  onboardingIssue?: "profile" | "cv" | "both";
}

const ISSUE_MESSAGES: Record<"profile" | "cv" | "both", string> = {
  profile: "Your account is ready, but we couldn't save your profile answers. You can add them from your Profile tab.",
  cv: "Your account is ready, but we couldn't process your CV. You can upload it again from your Profile tab.",
  both: "Your account is ready, but we couldn't save your profile or your CV. You can finish both from your Profile tab.",
};

function initials(email: string): string {
  const name = email.split("@")[0] ?? "";
  const parts = name.split(/[._-]+/).filter(Boolean);
  const pair = parts.length >= 2 ? `${parts[0][0]}${parts[1][0]}` : name.slice(0, 2);
  return (pair || "?").toUpperCase();
}

/** The single most useful thing to add next, in a fixed priority order --
 * not every empty field at once, which would just be a wall of text. */
function nextProfileGap(profile: ProfileOut): string | null {
  if (!profile.location) return "your location";
  if (profile.skills.length === 0) return "your skills";
  if (!profile.education_level) return "your education level";
  if (profile.industries.length === 0) return "industries you're interested in";
  if (profile.desired_salary_min == null && profile.desired_salary_max == null) return "your desired salary";
  return null;
}

export function Home() {
  const location = useLocation();
  const profile = useAuthStore((s) => s.profile);
  const onboardingIssue = (location.state as OnboardingIssueState | null)?.onboardingIssue;
  const [dismissedNotice, setDismissedNotice] = useState(false);

  const [matches, setMatches] = useState<MatchedListing[]>([]);
  const [matchesError, setMatchesError] = useState<string | null>(null);
  const [loadingMatches, setLoadingMatches] = useState(true);

  const isEmpty = (profile?.profile_completeness ?? 0) === 0;

  useEffect(() => {
    if (!profile || isEmpty) {
      setLoadingMatches(false);
      return;
    }
    setLoadingMatches(true);
    setMatchesError(null);
    api
      .get<Page<MatchedListing>>(`/listings/matches${buildQueryString({ limit: MATCHES_SAMPLE_SIZE, offset: 0 })}`)
      .then((page) => setMatches(page.items))
      .catch((err) => setMatchesError(err instanceof ApiError ? err.displayMessage : "Couldn't load your matches."))
      .finally(() => setLoadingMatches(false));
    // Re-runs when profile_completeness changes (e.g. the user just
    // finished the profile wizard in another tab of this flow) -- the
    // match set depends on profile fields, not just its existence.
  }, [profile, isEmpty]);

  if (!profile) return null; // RequireAuth guarantees this renders only once a profile exists

  // Already sorted by match score, descending, by the backend.
  const opportunities = matches.slice(0, ROW_COUNT);
  const newest = [...matches].sort((a, b) => (b.posted_at ?? "").localeCompare(a.posted_at ?? "")).slice(0, ROW_COUNT);
  const topMatch = matches[0] ?? null;
  const profileGap = isEmpty ? null : nextProfileGap(profile);

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

      {isEmpty ? (
        <main className={`mx-auto flex max-w-2xl flex-col items-center px-5 py-20 text-center sm:px-8 ${BOTTOM_NAV_SPACER_CLASS}`}>
          <div className="flex h-20 w-20 items-center justify-center rounded-full bg-mist text-ink/40">
            <DiggingSearchIcon />
          </div>
          <h1 className="mt-6 font-display text-2xl font-black tracking-tight text-ink sm:text-3xl">
            You don't have any job listings yet
          </h1>
          <p className="mt-3 max-w-sm font-body text-[15px] leading-relaxed text-ink/65">
            Complete your profile to get personalised job matches.
          </p>
          <Link to="/onboarding/profile" className="mt-7">
            <Button variant="primary" className="px-6 py-3.5 text-base">
              Complete your profile
            </Button>
          </Link>
          <Link to="/onboarding/cv" className="mt-3 font-body text-sm font-medium text-ink/60 hover:text-ink">
            Or just upload your CV
          </Link>
        </main>
      ) : (
        <main className={`mx-auto max-w-3xl px-5 py-6 sm:px-8 ${BOTTOM_NAV_SPACER_CLASS}`}>
          <div className="flex items-center justify-between">
            <h1 className="font-display text-2xl font-black tracking-tight text-ink">Home</h1>
            <Link
              to="/onboarding/profile"
              aria-label="Your profile"
              className="flex h-10 w-10 items-center justify-center rounded-full bg-phanda-green/15 font-body text-sm font-bold text-phanda-green-dark"
            >
              {initials(profile.email)}
            </Link>
          </div>

          <div className="mt-6 flex flex-col gap-5">
            {loadingMatches && <ProgressState label="Finding opportunities for you..." />}

            {!loadingMatches && matchesError && (
              <div className="rounded-2xl border border-hairline px-5 py-6 text-center">
                <p className="font-body text-sm text-ink/60">{matchesError}</p>
              </div>
            )}

            {!loadingMatches && !matchesError && opportunities.length === 0 && (
              <div className="rounded-2xl border border-hairline px-5 py-10 text-center">
                <p className="font-body text-[15px] font-semibold text-ink">No opportunities yet</p>
                <p className="mt-1 font-body text-sm text-ink/60">Check back soon, or browse everything in Find.</p>
                <Link to="/find" className="mt-3 inline-block">
                  <Button variant="secondary">Go to Find</Button>
                </Link>
              </div>
            )}

            {!loadingMatches && !matchesError && opportunities.length > 0 && (
              <Section title="Opportunities for you">
                {opportunities.map((listing) => (
                  <CompactMatchRow key={listing.id} listing={listing} />
                ))}
              </Section>
            )}

            {!loadingMatches && !matchesError && newest.length > 0 && (
              <Section title="New for you">
                {newest.map((listing) => (
                  <CompactMatchRow key={listing.id} listing={listing} />
                ))}
              </Section>
            )}

            {profileGap && <ProfileNudgeCard completeness={profile.profile_completeness} gapLabel={profileGap} />}

            {topMatch && topMatch.match.missing_skills.length > 0 && <CloseTheGapCard topMatch={topMatch} />}
          </div>
        </main>
      )}
    </div>
  );
}

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section>
      <h2 className="font-body text-sm font-semibold text-ink/70">{title}</h2>
      <div className="mt-3 flex flex-col gap-2.5">{children}</div>
    </section>
  );
}

function CompactMatchRow({ listing }: { listing: MatchedListing }) {
  return (
    <Link
      to={`/listings/${listing.id}`}
      state={{ match: listing.match }}
      className="flex items-center justify-between gap-3 rounded-2xl border border-hairline px-4 py-3.5 transition-colors hover:border-ink/25"
    >
      <div className="min-w-0">
        <p className="truncate font-body text-[15px] font-semibold text-ink">{listing.title}</p>
        <p className="truncate font-body text-sm text-ink/60">
          {[listing.company, listing.location].filter(Boolean).join(" · ")}
        </p>
      </div>
      <span className="shrink-0 rounded-full bg-phanda-green/10 px-2.5 py-1 font-body text-xs font-bold text-phanda-green-dark">
        {listing.match.score}%
      </span>
    </Link>
  );
}

function ProfileNudgeCard({ completeness, gapLabel }: { completeness: number; gapLabel: string }) {
  return (
    <div className="rounded-2xl border border-hairline bg-phanda-violet-soft p-5">
      <p className="font-body text-[15px] font-semibold text-ink">Your profile is {completeness}% complete</p>
      <p className="mt-1 font-body text-sm text-ink/70">Add {gapLabel} to finish.</p>
      <Link
        to="/onboarding/profile"
        className="mt-3 inline-block font-body text-sm font-semibold text-phanda-violet hover:underline"
      >
        Complete profile
      </Link>
    </div>
  );
}

type GapState =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "done"; roadmap: RoadmapOut }
  | { phase: "blocked"; message: string };

/**
 * Deliberately NOT auto-fetched on mount, even though the spec describes a
 * loading state as if the card fetches eagerly. The free tier for this
 * endpoint is 3 roadmap calls per month, shared across every skill
 * (confirmed live against the backend) -- auto-firing one every time this
 * card renders would exhaust a user's whole month's quota in three visits
 * to their own home screen. Gating it behind one explicit tap costs
 * nothing (the resources aren't time-sensitive) and means the quota is
 * spent only when the user actually wants it.
 */
function CloseTheGapCard({ topMatch }: { topMatch: MatchedListing }) {
  const [state, setState] = useState<GapState>({ phase: "idle" });
  const missingSkills = topMatch.match.missing_skills;
  const primarySkill = missingSkills[0];

  async function reveal() {
    setState({ phase: "loading" });
    try {
      const roadmap = await api.post<RoadmapOut>(`/skill-gap/roadmap/${encodeURIComponent(primarySkill)}`);
      setState({ phase: "done", roadmap });
    } catch (err) {
      setState({
        phase: "blocked",
        message: err instanceof ApiError ? err.displayMessage : "Couldn't load resources right now.",
      });
    }
  }

  return (
    <div className="rounded-2xl border border-hairline bg-phanda-violet-soft p-5">
      <p className="font-body text-[15px] font-semibold text-ink">Close the gap</p>
      <p className="mt-1 font-body text-sm text-ink/70">
        {missingSkills.length === 1
          ? `${topMatch.title} wants ${primarySkill}, which isn't on your profile yet.`
          : `${topMatch.title} wants ${missingSkills.length} skills you don't have yet, including ${primarySkill}.`}
      </p>

      {state.phase === "idle" && (
        <Button variant="secondary" className="mt-3" onClick={reveal}>
          Show me how
        </Button>
      )}

      {state.phase === "loading" && (
        <div className="mt-3 flex items-center gap-2 font-body text-sm text-ink/60">
          <SpinnerIcon className="h-4 w-4 text-phanda-violet" />
          Finding resources...
        </div>
      )}

      {state.phase === "blocked" && <p className="mt-3 font-body text-sm text-signal">{state.message}</p>}

      {state.phase === "done" && (
        <>
          {state.roadmap.resources.length === 0 ? (
            <p className="mt-3 font-body text-sm text-ink/60">We don't have study resources for {primarySkill} yet.</p>
          ) : (
            <ul className="mt-3 flex flex-col gap-1.5">
              {state.roadmap.resources.slice(0, 2).map((resource) => (
                <li key={resource.url}>
                  <a
                    href={resource.url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-body text-sm font-medium text-phanda-violet hover:underline"
                  >
                    {resource.title}
                  </a>
                </li>
              ))}
            </ul>
          )}
          <Link
            to="/skill-gap"
            state={{ listingTitle: topMatch.title, missingSkills }}
            className="mt-3 inline-block font-body text-sm font-semibold text-phanda-violet hover:underline"
          >
            See more
          </Link>
        </>
      )}
    </div>
  );
}
