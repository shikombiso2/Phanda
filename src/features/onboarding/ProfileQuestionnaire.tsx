import { type ReactNode, useState } from "react";
import { Button } from "../../components/Button";
import { TextField } from "../../components/TextField";
import { ChevronLeftIcon } from "../../components/icons";
import type { ExperienceLevel, JobType } from "../../types/api";
import type { ProfileAnswers } from "./profileAnswers";

const JOB_TYPES: { value: JobType; label: string }[] = [
  { value: "any", label: "Anything that fits" },
  { value: "learnership", label: "Learnership" },
  { value: "internship", label: "Internship" },
  { value: "full_time", label: "Full-time" },
  { value: "part_time", label: "Part-time" },
];

const EXPERIENCE_LEVELS: { value: ExperienceLevel; label: string }[] = [
  { value: "none", label: "No work experience yet" },
  { value: "under_1_year", label: "Under a year" },
  { value: "1_to_3_years", label: "1 to 3 years" },
  { value: "3_plus_years", label: "3+ years" },
];

const TOTAL_STEPS = 4;

interface ProfileQuestionnaireProps {
  values: ProfileAnswers;
  onChange: (next: ProfileAnswers) => void;
  /** Called from the last internal step's primary button. */
  onFinish: () => void;
  /** Called from "Skip for now", available on every internal step. */
  onSkip: () => void;
  /** "Save profile" for the authenticated edit flow, "Continue" when this
   * is just one part of a larger signup wizard and nothing is saved yet. */
  finishLabel?: string;
  saving?: boolean;
  error?: string | null;
}

/**
 * The profile field-collection UI, by itself -- no persistence, no
 * navigation. Used both by ProfileWizard (which PUTs on finish, for an
 * already-authenticated user editing their profile) and by SignupWizard
 * (which holds the answers in local state until an account exists to save
 * them to). Lifting this out means the design and copy exist in one place.
 */
export function ProfileQuestionnaire({
  values,
  onChange,
  onFinish,
  onSkip,
  finishLabel = "Save profile",
  saving = false,
  error = null,
}: ProfileQuestionnaireProps) {
  const [step, setStep] = useState(1);

  function set<K extends keyof ProfileAnswers>(key: K, value: ProfileAnswers[K]) {
    onChange({ ...values, [key]: value });
  }

  return (
    <div>
      <div className="mb-8 flex items-center justify-between">
        {step > 1 ? (
          <button
            onClick={() => setStep((s) => s - 1)}
            className="flex items-center gap-1 font-body text-sm font-medium text-ink/60 hover:text-ink"
          >
            <ChevronLeftIcon className="h-4 w-4" />
            Back
          </button>
        ) : (
          <span />
        )}
        <button onClick={onSkip} className="font-body text-sm font-medium text-ink/50 hover:text-ink">
          Skip for now
        </button>
      </div>

      <ProgressDots current={step} total={TOTAL_STEPS} />

      {step === 1 && (
        <StepShell title="What kind of work are you after?" subtitle="You can change this any time.">
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 font-body text-sm font-medium text-ink">Type of work</legend>
            {JOB_TYPES.map((option) => (
              <label
                key={option.value}
                className={`flex cursor-pointer items-center gap-3 rounded-[10px] border px-4 py-3 text-[15px] transition-colors ${
                  values.jobType === option.value ? "border-phanda-green bg-phanda-green/5" : "border-hairline"
                }`}
              >
                <input
                  type="radio"
                  name="jobType"
                  className="accent-phanda-green"
                  checked={values.jobType === option.value}
                  onChange={() => set("jobType", option.value)}
                />
                {option.label}
              </label>
            ))}
          </fieldset>
          <TextField
            label="Where are you based?"
            placeholder="e.g. Gqeberha, Eastern Cape"
            value={values.location}
            onChange={(e) => set("location", e.target.value)}
            className="mt-5"
          />
          <label className="mt-4 flex items-center gap-2.5 font-body text-[15px] text-ink">
            <input
              type="checkbox"
              className="h-4 w-4 accent-phanda-green"
              checked={values.openToRemote}
              onChange={(e) => set("openToRemote", e.target.checked)}
            />
            I'm open to remote work
          </label>
          <Button className="mt-8 w-full" onClick={() => setStep(2)}>
            Continue
          </Button>
        </StepShell>
      )}

      {step === 2 && (
        <StepShell title="Your experience" subtitle="Be honest -- it helps us match you accurately.">
          <fieldset className="flex flex-col gap-2">
            <legend className="mb-1 font-body text-sm font-medium text-ink">Work experience</legend>
            {EXPERIENCE_LEVELS.map((option) => (
              <label
                key={option.value}
                className={`flex cursor-pointer items-center gap-3 rounded-[10px] border px-4 py-3 text-[15px] transition-colors ${
                  values.experienceLevel === option.value ? "border-phanda-green bg-phanda-green/5" : "border-hairline"
                }`}
              >
                <input
                  type="radio"
                  name="experienceLevel"
                  className="accent-phanda-green"
                  checked={values.experienceLevel === option.value}
                  onChange={() => set("experienceLevel", option.value)}
                />
                {option.label}
              </label>
            ))}
          </fieldset>
          <TextField
            label="Highest level of education"
            placeholder="e.g. Matric, National Diploma"
            value={values.educationLevel}
            onChange={(e) => set("educationLevel", e.target.value)}
            className="mt-5"
          />
          <Button className="mt-8 w-full" onClick={() => setStep(3)}>
            Continue
          </Button>
        </StepShell>
      )}

      {step === 3 && (
        <StepShell title="What are you good at?" subtitle="List a few skills, separated by commas.">
          <TextField
            label="Skills"
            placeholder="e.g. customer service, Excel, forklift licence"
            value={values.skillsInput}
            onChange={(e) => set("skillsInput", e.target.value)}
            hint="Don't worry about getting this perfect -- you can edit it later."
          />
          <TextField
            label="Industries you're interested in"
            placeholder="e.g. retail, logistics, hospitality"
            value={values.industriesInput}
            onChange={(e) => set("industriesInput", e.target.value)}
            className="mt-5"
          />
          <Button className="mt-8 w-full" onClick={() => setStep(4)}>
            Continue
          </Button>
        </StepShell>
      )}

      {step === 4 && (
        <StepShell title="One last thing" subtitle="Optional -- skip this if you'd rather not say.">
          <div className="grid grid-cols-2 gap-4">
            <TextField
              label="Minimum salary (R/month)"
              type="number"
              inputMode="numeric"
              placeholder="e.g. 6000"
              value={values.salaryMin}
              onChange={(e) => set("salaryMin", e.target.value)}
            />
            <TextField
              label="Maximum salary (R/month)"
              type="number"
              inputMode="numeric"
              placeholder="e.g. 12000"
              value={values.salaryMax}
              onChange={(e) => set("salaryMax", e.target.value)}
            />
          </div>
          {error && (
            <p role="alert" className="mt-4 rounded-[10px] bg-signal-soft px-4 py-3 text-sm font-medium text-signal">
              {error}
            </p>
          )}
          <Button className="mt-8 w-full" onClick={onFinish} loading={saving}>
            {finishLabel}
          </Button>
        </StepShell>
      )}
    </div>
  );
}

function StepShell({ title, subtitle, children }: { title: string; subtitle: string; children: ReactNode }) {
  return (
    <div>
      <h1 className="font-display text-2xl font-black tracking-tight text-ink">{title}</h1>
      <p className="mt-1.5 font-body text-[15px] text-ink/60">{subtitle}</p>
      <div className="mt-6">{children}</div>
    </div>
  );
}

function ProgressDots({ current, total }: { current: number; total: number }) {
  return (
    <div className="mb-8 flex gap-2" role="progressbar" aria-valuenow={current} aria-valuemin={1} aria-valuemax={total}>
      {Array.from({ length: total }, (_, i) => (
        <span key={i} className={`h-1.5 flex-1 rounded-full ${i < current ? "bg-phanda-green" : "bg-hairline"}`} />
      ))}
    </div>
  );
}
