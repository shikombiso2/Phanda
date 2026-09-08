import { Link } from "react-router-dom";
import { formatSalary } from "../lib/salary";
import type { ListingSummary, MatchExplanation } from "../types/api";
import { HeartIcon } from "./icons";

const LISTING_TYPE_LABEL: Record<string, string> = {
  job: "Job",
  internship: "Internship",
  learnership: "Learnership",
  apprenticeship: "Apprenticeship",
  bursary: "Bursary",
};

interface ListingCardProps {
  listing: ListingSummary;
  match?: MatchExplanation;
  saved: boolean;
  onToggleSave: () => void;
}

/** One listing, everywhere a listing appears -- Find, Saved, and (without
 * `match`) the plain search view. Reused rather than re-styled per screen. */
export function ListingCard({ listing, match, saved, onToggleSave }: ListingCardProps) {
  const salary = formatSalary(listing.salary_min, listing.salary_max, listing.salary_period, listing.salary_currency);
  const skills = listing.required_skills.slice(0, 4);
  const extraSkillCount = listing.required_skills.length - skills.length;

  return (
    <div className="relative rounded-2xl border border-hairline p-4 sm:p-5">
      <button
        onClick={(e) => {
          e.preventDefault();
          onToggleSave();
        }}
        aria-label={saved ? "Remove from saved" : "Save this listing"}
        aria-pressed={saved}
        className={`absolute right-4 top-4 rounded-full p-1.5 transition-colors ${
          saved ? "text-phanda-green" : "text-ink/30 hover:text-ink/60"
        }`}
      >
        <HeartIcon className="h-5 w-5" filled={saved} />
      </button>

      <Link to={`/listings/${listing.id}`} state={match ? { match } : undefined} className="block pr-8">
        {match && (
          <div className="mb-2 flex items-center gap-2">
            <span className="rounded-full bg-phanda-green/10 px-2.5 py-1 font-body text-xs font-bold text-phanda-green-dark">
              {match.score}% match
            </span>
          </div>
        )}

        <p className="font-body text-[15px] font-semibold leading-snug text-ink">{listing.title}</p>
        <p className="mt-0.5 font-body text-sm text-ink/60">
          {[listing.company, listing.location].filter(Boolean).join(" · ")}
        </p>

        <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
          <span className="font-body text-xs font-medium text-ink/50">
            {LISTING_TYPE_LABEL[listing.listing_type] ?? listing.listing_type}
          </span>
          {salary && <span className="font-body text-xs font-medium text-ink/50">{salary}</span>}
        </div>

        {match && (
          <p className="mt-2 font-body text-sm text-ink/70">{match.summary}</p>
        )}

        {skills.length > 0 && (
          <div className="mt-3 flex flex-wrap gap-1.5">
            {skills.map((skill) => {
              const isMissing = match?.missing_skills.includes(skill);
              return (
                <span
                  key={skill}
                  className={`rounded-full px-2.5 py-1 font-body text-xs ${
                    isMissing ? "bg-mist text-ink/40" : "bg-mist text-ink/70"
                  }`}
                >
                  {skill}
                </span>
              );
            })}
            {extraSkillCount > 0 && (
              <span className="rounded-full px-2.5 py-1 font-body text-xs text-ink/40">+{extraSkillCount} more</span>
            )}
          </div>
        )}
      </Link>
    </div>
  );
}
