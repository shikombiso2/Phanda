import { Link } from "react-router-dom";
import { AppHeader } from "../components/AppHeader";
import { Button } from "../components/Button";
import { CheckIcon, DiggingSearchIcon } from "../components/icons";
import { useAuthStore } from "../store/authStore";

export function Home() {
  const profile = useAuthStore((s) => s.profile);

  const hasProfile = (profile?.profile_completeness ?? 0) > 0;
  const hasCv = Boolean(profile?.active_cv_version_id);
  const hasNeither = !hasProfile && !hasCv;

  return (
    <div className="min-h-screen bg-paper">
      <AppHeader />

      <main className="mx-auto flex max-w-2xl flex-col items-center px-5 py-20 text-center sm:px-8">
        {hasNeither ? (
          <>
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
          </>
        ) : (
          <>
            <h1 className="font-display text-2xl font-black tracking-tight text-ink sm:text-3xl">
              You're set up. Matches are next.
            </h1>
            <p className="mt-3 max-w-sm font-body text-[15px] leading-relaxed text-ink/65">
              Personalised job matching is coming in the next update. Here's where things stand:
            </p>

            <div className="mt-8 flex w-full flex-col gap-3 text-left">
              <ChecklistRow
                done={hasProfile}
                label="Profile"
                detail={hasProfile ? "Complete" : "Not started"}
                actionLabel={hasProfile ? "Edit profile" : "Complete profile"}
                to="/onboarding/profile"
              />
              <ChecklistRow
                done={hasCv}
                label="CV"
                detail={hasCv ? "Uploaded" : "Not uploaded"}
                actionLabel={hasCv ? "Replace CV" : "Upload CV"}
                to="/onboarding/cv"
              />
            </div>
          </>
        )}
      </main>
    </div>
  );
}

function ChecklistRow({
  done,
  label,
  detail,
  actionLabel,
  to,
}: {
  done: boolean;
  label: string;
  detail: string;
  actionLabel: string;
  to: string;
}) {
  return (
    <div className="flex items-center justify-between rounded-[10px] border border-hairline px-4 py-3.5">
      <div className="flex items-center gap-3">
        <span
          className={`flex h-6 w-6 items-center justify-center rounded-full ${
            done ? "bg-phanda-green text-white" : "bg-mist text-ink/30"
          }`}
        >
          <CheckIcon className="h-3.5 w-3.5" />
        </span>
        <div>
          <p className="font-body text-[15px] font-semibold text-ink">{label}</p>
          <p className="font-body text-sm text-ink/55">{detail}</p>
        </div>
      </div>
      <Link to={to} className="font-body text-sm font-semibold text-phanda-green-dark hover:underline">
        {actionLabel}
      </Link>
    </div>
  );
}
