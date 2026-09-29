import { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { AppNav, BOTTOM_NAV_SPACER_CLASS } from "../components/AppNav";
import { Button } from "../components/Button";
import { ChevronLeftIcon, SpinnerIcon } from "../components/icons";
import { api } from "../lib/api";
import { ApiError } from "../lib/apiError";
import type { RoadmapOut } from "../types/api";

interface LocationState {
  listingTitle?: string;
  missingSkills?: string[];
}

type SkillState =
  | { phase: "idle" }
  | { phase: "loading" }
  | { phase: "done"; roadmap: RoadmapOut }
  | { phase: "blocked"; message: string };

/**
 * Reached only from Home's "Close the gap" card, via router state -- there
 * is nothing here to reload from a direct URL, since the underlying data
 * (a specific listing's missing skills) is ephemeral match context, not a
 * saved resource. Each skill fetches its own roadmap on demand, not all at
 * once on mount: the endpoint's free tier is 3 calls per month for this
 * account, total, across every skill, so eagerly fetching N rows on page
 * load could burn the whole month's quota in one visit.
 */
export function SkillGapDetail() {
  const location = useLocation();
  const navigate = useNavigate();
  const state = location.state as LocationState | null;
  const missingSkills = state?.missingSkills ?? [];

  const [rowStates, setRowStates] = useState<Record<string, SkillState>>({});

  async function reveal(skill: string) {
    setRowStates((prev) => ({ ...prev, [skill]: { phase: "loading" } }));
    try {
      const roadmap = await api.post<RoadmapOut>(`/skill-gap/roadmap/${encodeURIComponent(skill)}`);
      setRowStates((prev) => ({ ...prev, [skill]: { phase: "done", roadmap } }));
    } catch (err) {
      setRowStates((prev) => ({
        ...prev,
        [skill]: { phase: "blocked", message: err instanceof ApiError ? err.displayMessage : "Couldn't load resources right now." },
      }));
    }
  }

  if (!state || missingSkills.length === 0) {
    return (
      <div className="min-h-screen bg-paper">
        <AppNav />
        <main className={`mx-auto max-w-xl px-5 py-12 text-center sm:px-8 ${BOTTOM_NAV_SPACER_CLASS}`}>
          <p className="font-body text-[15px] font-semibold text-ink">Nothing to show here</p>
          <p className="mt-1 font-body text-sm text-ink/60">Head back to Home and open "Close the gap" on a match.</p>
          <Link to="/home" className="mt-4 inline-block">
            <Button variant="secondary">Back to Home</Button>
          </Link>
        </main>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-paper">
      <AppNav />
      <main className={`mx-auto max-w-xl px-5 py-8 sm:px-8 ${BOTTOM_NAV_SPACER_CLASS}`}>
        <button
          onClick={() => navigate(-1)}
          className="flex items-center gap-1 font-body text-sm font-medium text-ink/60 hover:text-ink"
        >
          <ChevronLeftIcon className="h-4 w-4" />
          Back
        </button>

        <h1 className="mt-4 font-display text-2xl font-black tracking-tight text-ink">Close the gap</h1>
        {state.listingTitle && (
          <p className="mt-1 font-body text-sm text-ink/60">Skills {state.listingTitle} is looking for that aren't on your profile yet.</p>
        )}

        <div className="mt-6 flex flex-col gap-3">
          {missingSkills.map((skill) => {
            const rowState = rowStates[skill] ?? { phase: "idle" };
            return (
              <div key={skill} className="rounded-2xl border border-hairline p-4">
                <div className="flex items-center justify-between gap-3">
                  <p className="font-body text-[15px] font-semibold capitalize text-ink">{skill}</p>
                  {rowState.phase === "idle" && (
                    <Button variant="secondary" onClick={() => reveal(skill)}>
                      Get resources
                    </Button>
                  )}
                  {rowState.phase === "loading" && <SpinnerIcon className="h-5 w-5 text-phanda-violet" />}
                </div>

                {rowState.phase === "blocked" && (
                  <p className="mt-2 font-body text-sm text-signal">{rowState.message}</p>
                )}

                {rowState.phase === "done" &&
                  (rowState.roadmap.resources.length === 0 ? (
                    <p className="mt-2 font-body text-sm text-ink/60">We don't have study resources for {skill} yet.</p>
                  ) : (
                    <ul className="mt-2 flex flex-col gap-1">
                      {rowState.roadmap.resources.map((resource) => (
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
                  ))}
              </div>
            );
          })}
        </div>
      </main>
    </div>
  );
}
