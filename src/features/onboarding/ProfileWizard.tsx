import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { AppHeader } from "../../components/AppHeader";
import { Button } from "../../components/Button";
import { TextField } from "../../components/TextField";
import { ChevronLeftIcon } from "../../components/icons";
import { api } from "../../lib/api";
import { ApiError } from "../../lib/apiError";
import { useAuthStore } from "../../store/authStore";
import type { ExperienceLevel, JobType, ProfileOut, ProfileUpdate } from "../../types/api";

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

export function ProfileWizard() {
  const navigate = useNavigate();
  const profile = useAuthStore((s) => s.profile);
  const setProfile = useAuthStore((s) => s.setProfile);

  const [step, setStep] = useState(1);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Seeded from the existing profile, not blank defaults: PUT /profile is a
  // full replace on the backend (every ProfileUpdate field has a hard
  // default and the handler writes all of them, not just the ones present
  // in the request body). Starting from blanks would silently wipe
  // whatever the user had already saved the moment they reopened this to
  // tweak one field.
  const [jobType, setJobType] = useState<JobType>(profile?.job_type ?? "any");
  const [location, setLocation] = useState(profile?.location ?? "");
  const [openToRemote, setOpenToRemote] = useState(profile?.open_to_remote ?? false);
  const [experienceLevel, setExperienceLevel] = useState<ExperienceLevel>(profile?.experience_level ?? "none");
  const [educationLevel, setEducationLevel] = useState(profile?.education_level ?? "");
  const [skillsInput, setSkillsInput] = useState((profile?.skills ?? []).join(", "));
  const [industriesInput, setIndustriesInput] = useState((profile?.industries ?? []).join(", "));
  const [salaryMin, setSalaryMin] = useState(profile?.desired_salary_min?.toString() ?? "");
  const [salaryMax, setSalaryMax] = useState(profile?.desired_salary_max?.toString() ?? "");

  function goToHome() {
    navigate("/home", { replace: true });
  }

  function parseList(value: string): string[] {
    return value
      .split(",")
      .map((s) => s.trim())
      .filter(Boolean);
  }

  function parseSalary(value: string): number | null {
    const n = Number(value.trim());
    return value.trim() && Number.isFinite(n) ? n : null;
  }

  async function finish() {
    setSaving(true);
    setError(null);
    // Every field the schema defines, even ones this wizard doesn't have a
    // dedicated step for -- see the comment on the state above for why.
    const payload: ProfileUpdate = {
      job_type: jobType,
      location: location.trim() || null,
      open_to_remote: openToRemote,
      experience_level: experienceLevel,
      education_level: educationLevel.trim() || null,
      skills: parseList(skillsInput),
      industries: parseList(industriesInput),
      desired_salary_min: parseSalary(salaryMin),
      desired_salary_max: parseSalary(salaryMax),
    };
    try {
      const updated = await api.put<ProfileOut>("/profile", payload);
      setProfile(updated);
      navigate("/onboarding/cv");
    } catch (err) {
      setError(err instanceof ApiError ? err.displayMessage : "Couldn't save your profile. Try again.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="min-h-screen bg-paper">
      <AppHeader />
      <main className="mx-auto max-w-md px-5 py-12 sm:px-8">
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
          <button onClick={goToHome} className="font-body text-sm font-medium text-ink/50 hover:text-ink">
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
                    jobType === option.value ? "border-phanda-green bg-phanda-green/5" : "border-hairline"
                  }`}
                >
                  <input
                    type="radio"
                    name="jobType"
                    className="accent-phanda-green"
                    checked={jobType === option.value}
                    onChange={() => setJobType(option.value)}
                  />
                  {option.label}
                </label>
              ))}
            </fieldset>
            <TextField
              label="Where are you based?"
              placeholder="e.g. Gqeberha, Eastern Cape"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              className="mt-5"
            />
            <label className="mt-4 flex items-center gap-2.5 font-body text-[15px] text-ink">
              <input
                type="checkbox"
                className="h-4 w-4 accent-phanda-green"
                checked={openToRemote}
                onChange={(e) => setOpenToRemote(e.target.checked)}
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
                    experienceLevel === option.value ? "border-phanda-green bg-phanda-green/5" : "border-hairline"
                  }`}
                >
                  <input
                    type="radio"
                    name="experienceLevel"
                    className="accent-phanda-green"
                    checked={experienceLevel === option.value}
                    onChange={() => setExperienceLevel(option.value)}
                  />
                  {option.label}
                </label>
              ))}
            </fieldset>
            <TextField
              label="Highest level of education"
              placeholder="e.g. Matric, National Diploma"
              value={educationLevel}
              onChange={(e) => setEducationLevel(e.target.value)}
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
              value={skillsInput}
              onChange={(e) => setSkillsInput(e.target.value)}
              hint="Don't worry about getting this perfect -- you can edit it later."
            />
            <TextField
              label="Industries you're interested in"
              placeholder="e.g. retail, logistics, hospitality"
              value={industriesInput}
              onChange={(e) => setIndustriesInput(e.target.value)}
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
                value={salaryMin}
                onChange={(e) => setSalaryMin(e.target.value)}
              />
              <TextField
                label="Maximum salary (R/month)"
                type="number"
                inputMode="numeric"
                placeholder="e.g. 12000"
                value={salaryMax}
                onChange={(e) => setSalaryMax(e.target.value)}
              />
            </div>
            {error && (
              <p role="alert" className="mt-4 rounded-[10px] bg-signal-soft px-4 py-3 text-sm font-medium text-signal">
                {error}
              </p>
            )}
            <Button className="mt-8 w-full" onClick={finish} loading={saving}>
              Save profile
            </Button>
          </StepShell>
        )}
      </main>
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
        <span
          key={i}
          className={`h-1.5 flex-1 rounded-full ${i < current ? "bg-phanda-green" : "bg-hairline"}`}
        />
      ))}
    </div>
  );
}
