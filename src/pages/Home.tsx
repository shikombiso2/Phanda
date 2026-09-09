import { useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { AppNav, BOTTOM_NAV_SPACER_CLASS } from "../components/AppNav";
import { Button } from "../components/Button";
import { ProgressState } from "../components/ProgressState";
import { BellIcon, DiggingSearchIcon } from "../components/icons";
import { api } from "../lib/api";
import { ApiError } from "../lib/apiError";
import { buildQueryString } from "../lib/queryString";
import { useAuthStore } from "../store/authStore";
import { firstName, initials } from "../lib/initials";
import type { ListingType, MatchedListing, Page, ProfileOut } from "../types/api";

const MATCHES_SAMPLE_SIZE = 10;
const ROW_COUNT = 3;
const SKILLS_TARGET = 5;

interface OnboardingIssueState {
  onboardingIssue?: "profile" | "cv" | "both";
}

const ISSUE_MESSAGES: Record<"profile" | "cv" | "both", string> = {
  profile: "Your account is ready, but we couldn't save your profile answers. You can add them from your Profile tab.",
  cv: "Your account is ready, but we couldn't process your CV. You can upload it again from your Profile tab.",
  both: "Your account is ready, but we couldn't save your profile or your CV. You can finish both from your Profile tab.",
};

/** Ranked, specific next actions -- up to 3, not a wall of every empty
 * field at once. Experience level is deliberately not included: the field
 * always has a value ("none" is a real answer, "no experience yet", not an
 * unset sentinel), so there's no reliable way to tell "the user left this
 * at its default" from "the user told us they have no experience". */
function nextProfileGaps(profile: ProfileOut): string[] {
  const gaps: string[] = [];
  if (!profile.location) gaps.push("Add your location");
  if (profile.skills.length === 0) gaps.push("Add your skills to get matched");
  else if (profile.skills.length < SKILLS_TARGET) {
    const remaining = SKILLS_TARGET - profile.skills.length;
    gaps.push(`Add ${remaining} more skill${remaining === 1 ? "" : "s"} to improve matches`);
  }
  if (!profile.education_level) gaps.push("Add your education level");
  if (profile.industries.length === 0) gaps.push("Add industries you're interested in");
  if (profile.desired_salary_min == null && profile.desired_salary_max == null) gaps.push("Add your desired salary");
  return gaps.slice(0, 3);
}

const LISTING_TYPE_LABELS: Record<ListingType, string> = {
  job: "Job",
  internship: "Internship",
  learnership: "Learnership",
  apprenticeship: "Apprenticeship",
  bursary: "Bursary",
};

/** Tag chips for an opportunity card -- only ever built from fields the
 * listing actually carries. There's no explicit "remote" flag on a listing
 * (open_to_remote lives on the *profile*, not the listing), so "Remote OK"
 * is inferred the same way the matching engine already does it elsewhere
 * (app/recommendations/features.py's location_compatibility): the listing's
 * location text mentioning "remote". Full-time/part-time isn't included --
 * that's a candidate preference (JobType), not a field listings are tagged
 * with, so there's no honest way to show it here. */
function listingTags(listing: MatchedListing): string[] {
  const tags = [LISTING_TYPE_LABELS[listing.listing_type]];
  if (listing.location?.toLowerCase().includes("remote")) tags.push("Remote OK");
  return tags;
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
  const shownIds = new Set(opportunities.map((listing) => listing.id));
  // Distinct from Opportunities for you, not just re-sorted -- the same 10-item
  // batch re-sorted by recency used to reproduce the top rows verbatim.
  const newest = matches
    .filter((listing) => !shownIds.has(listing.id))
    .sort((a, b) => (b.posted_at ?? "").localeCompare(a.posted_at ?? ""))
    .slice(0, ROW_COUNT);
  // "Close the gap" needs a listing with an actual skill gap to talk about --
  // many top-ranked matches carry no tagged required_skills at all (the
  // listing's overall score comes from location/experience/job-type instead),
  // so missing_skills is genuinely empty for match #1 more often than not.
  // Walk the fetched batch for the first one that has something to show,
  // rather than assuming the single top-scored listing always does.
  const gapMatch = matches.find((listing) => listing.match.missing_skills.length > 0) ?? null;
  const profileGaps = isEmpty ? [] : nextProfileGaps(profile);
  const name = firstName(profile.email);

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
          <div className="flex items-center justify-between gap-3">
            <div className="flex items-center gap-3">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-phanda-green/15 font-body text-sm font-bold text-phanda-green-dark">
                {initials(profile.email)}
              </span>
              <div>
                <p className="font-body text-[15px] font-semibold text-ink">{name ? `Sawubona, ${name}` : "Sawubona"}</p>
                <p className="font-body text-xs text-ink/60">Let's find your next move.</p>
              </div>
            </div>
            <button
              aria-label="Notifications"
              title="Notifications are coming soon"
              className="flex h-9 w-9 shrink-0 cursor-default items-center justify-center rounded-full bg-mist text-ink/60"
            >
              <BellIcon className="h-4 w-4" />
            </button>
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
              <OpportunityCarousel listings={opportunities} />
            )}

            {(profileGaps.length > 0 || newest.length > 0) && <SectionDivider />}

            {profileGaps.length > 0 && <ProfileNudgeCard completeness={profile.profile_completeness} gaps={profileGaps} />}

            {!loadingMatches && !matchesError && newest.length > 0 && (
              <>
                {profileGaps.length > 0 && <SectionDivider />}
                <SectionHeader title="New opportunities" />
                <div className="flex flex-col gap-2.5">
                  {newest.map((listing) => (
                    <NewListingRow key={listing.id} listing={listing} />
                  ))}
                </div>
              </>
            )}

            {gapMatch && (
              <>
                <SectionDivider />
                <CloseTheGapSection topMatch={gapMatch} batch={matches} />
              </>
            )}
          </div>
        </main>
      )}
    </div>
  );
}

function SectionHeader({ title, seeAllTo }: { title: string; seeAllTo?: string }) {
  return (
    <div className="flex items-center justify-between">
      <h2 className="font-body text-sm font-semibold text-ink/70">{title}</h2>
      {seeAllTo && (
        <Link to={seeAllTo} className="font-body text-xs font-semibold text-phanda-green-dark hover:underline">
          See all
        </Link>
      )}
    </div>
  );
}

function SectionDivider() {
  return <hr className="border-t border-hairline" />;
}

function OpportunityCarousel({ listings }: { listings: MatchedListing[] }) {
  return (
    <section>
      <SectionHeader title="Opportunities for you" seeAllTo="/find" />
      <div className="scrollbar-hide -mx-5 mt-3 flex gap-2 overflow-x-auto px-5 pb-1 sm:-mx-8 sm:px-8">
        {listings.map((listing) => (
          <OpportunityCard key={listing.id} listing={listing} />
        ))}
      </div>
    </section>
  );
}

function OpportunityCard({ listing }: { listing: MatchedListing }) {
  const tags = listingTags(listing);
  return (
    <Link
      to={`/listings/${listing.id}`}
      state={{ match: listing.match }}
      className="flex w-[168px] shrink-0 flex-col rounded-2xl border border-hairline bg-mist p-3 transition-colors hover:border-ink/25"
    >
      <span className="mb-2 inline-block self-start rounded-full bg-phanda-green/15 px-2.5 py-1 font-body text-[11px] font-semibold text-phanda-green-dark">
        {listing.match.score}% match
      </span>
      <p className="font-body text-[13px] font-semibold leading-snug text-ink">{listing.title}</p>
      <p className="mt-1 truncate font-body text-[11px] text-ink/60">
        {[listing.company, listing.location].filter(Boolean).join(" · ")}
      </p>
      {tags.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {tags.map((tag) => (
            <span
              key={tag}
              className="rounded-[6px] border border-hairline bg-paper px-1.5 py-0.5 font-body text-[10px] text-ink/60"
            >
              {tag}
            </span>
          ))}
        </div>
      )}
    </Link>
  );
}

function NewListingRow({ listing }: { listing: MatchedListing }) {
  return (
    <Link
      to={`/listings/${listing.id}`}
      state={{ match: listing.match }}
      className="flex items-center justify-between gap-3 rounded-2xl bg-mist px-4 py-3.5 transition-colors hover:bg-hairline/40"
    >
      <div className="min-w-0">
        <p className="truncate font-body text-[15px] font-semibold text-ink">{listing.title}</p>
        <p className="truncate font-body text-sm text-ink/60">
          {[listing.company, listing.location].filter(Boolean).join(" · ")}
        </p>
      </div>
      <span className="shrink-0 rounded-full bg-phanda-green/15 px-2.5 py-1 font-body text-[11px] font-semibold text-phanda-green-dark">
        New
      </span>
    </Link>
  );
}

function ProfileNudgeCard({ completeness, gaps }: { completeness: number; gaps: string[] }) {
  return (
    <div className="rounded-2xl bg-mist p-4">
      <div className="flex items-center justify-between">
        <p className="font-body text-[13px] font-semibold text-ink">Your profile is {completeness}% complete</p>
        <span className="font-body text-xs font-semibold text-ink">{completeness}%</span>
      </div>
      <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-hairline">
        <div className="h-full rounded-full bg-phanda-green" style={{ width: `${completeness}%` }} />
      </div>
      <ul className="mt-3 list-disc pl-4 font-body text-xs leading-relaxed text-ink/70">
        {gaps.map((gap) => (
          <li key={gap}>{gap}</li>
        ))}
      </ul>
      <Link
        to="/onboarding/profile"
        className="mt-1 inline-block font-body text-xs font-semibold text-phanda-green-dark hover:underline"
      >
        Complete your profile &rarr;
      </Link>
    </div>
  );
}

function normalizeSkill(value: string): string {
  return value.trim().toLowerCase();
}

/**
 * No API call happens here at all -- the quota-protected roadmap fetch
 * (3 calls/month, shared across every skill, confirmed live against the
 * backend) lives entirely in SkillGapDetail, gated per-skill behind its own
 * "Get resources" button. This card only ever counts and links; the tap
 * that actually spends quota happens one screen later, and only for the
 * one skill the user picks there.
 */
function CloseTheGapSection({ topMatch, batch }: { topMatch: MatchedListing; batch: MatchedListing[] }) {
  const missingSkills = topMatch.match.missing_skills;
  const primarySkill = missingSkills[0];
  const chipSkills = missingSkills.slice(0, 5);

  // How many of the *already-fetched* matches this skill would help with --
  // not a new API call, just a count over the same batch already on screen.
  const rolesAffected = batch.filter((listing) =>
    (listing.required_skills ?? []).some((skill) => normalizeSkill(skill) === normalizeSkill(primarySkill)),
  ).length;

  return (
    <section>
      <h2 className="mb-3 font-body text-sm font-semibold text-ink/70">Close the gap</h2>
      <div className="rounded-2xl border border-phanda-violet-border bg-phanda-violet-soft p-4">
        <p className="font-body text-[13px] font-semibold leading-relaxed text-phanda-violet">
          {rolesAffected > 1
            ? `You're missing skills that appear in ${rolesAffected} of your target roles`
            : `${primarySkill} shows up in listings that match what you're looking for`}
        </p>
        <p className="mt-1 font-body text-xs leading-relaxed text-ink/60">
          Adding these could unlock significantly more matches for you.
        </p>

        <div className="mt-3 flex flex-wrap gap-1.5">
          {chipSkills.map((skill) => (
            <span
              key={skill}
              className="rounded-full border border-hairline bg-paper px-2.5 py-1 font-body text-xs text-ink"
            >
              {skill}
            </span>
          ))}
        </div>

        <Link
          to="/skill-gap"
          state={{ listingTitle: topMatch.title, missingSkills }}
          className="mt-3 inline-block font-body text-xs font-semibold text-phanda-violet hover:underline"
        >
          Explore free learnerships &rarr;
        </Link>
      </div>
    </section>
  );
}
