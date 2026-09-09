import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { AppNav, BOTTOM_NAV_SPACER_CLASS } from "../components/AppNav";
import { Button } from "../components/Button";
import { TextField } from "../components/TextField";
import { initials } from "../lib/initials";
import { api } from "../lib/api";
import { ApiError } from "../lib/apiError";
import { useAuthStore } from "../store/authStore";
import type { CvVersionOut, CvVersionStatus, ExperienceLevel, JobType, ProfileOut, ProfileUpdate } from "../types/api";

const JOB_TYPE_LABELS: Record<JobType, string> = {
  any: "Anything that fits",
  learnership: "Learnership",
  internship: "Internship",
  full_time: "Full-time",
  part_time: "Part-time",
};

const EXPERIENCE_LABELS: Record<ExperienceLevel, string> = {
  none: "No experience yet",
  some: "Some experience",
  experienced: "Experienced",
};

const CV_STATUS_LABELS: Record<CvVersionStatus, string> = {
  uploaded: "Uploaded",
  extracting: "Reading your CV...",
  ready: "Ready",
  failed: "Couldn't be read",
};

/** Every field PUT /profile expects, taken from the current profile as a
 * base -- the backend replaces the whole record on save, so every section's
 * edit only overrides its own fields and carries every other field forward
 * unchanged (see profileAnswersToUpdate.ts for the same rule in the
 * onboarding flow). */
function baseUpdate(profile: ProfileOut): ProfileUpdate {
  return {
    job_type: profile.job_type,
    location: profile.location,
    open_to_remote: profile.open_to_remote,
    skills: profile.skills,
    industries: profile.industries,
    education_level: profile.education_level,
    experience_level: profile.experience_level,
    desired_salary_min: profile.desired_salary_min,
    desired_salary_max: profile.desired_salary_max,
  };
}

/**
 * The returning user's read/edit view of their own profile -- distinct from
 * ProfileWizard, which is the step-by-step questionnaire used only during
 * signup and from "complete your profile" nudges. This is reachable from
 * the persistent Profile nav tab, so it needs to show what's saved, not
 * walk through collecting it again.
 */
export function ProfileView() {
  const profile = useAuthStore((s) => s.profile);
  const setProfile = useAuthStore((s) => s.setProfile);
  const [error, setError] = useState<string | null>(null);

  if (!profile) return null; // RequireAuth guarantees this renders only once a profile exists

  async function save(patch: ProfileUpdate) {
    setError(null);
    try {
      const updated = await api.put<ProfileOut>("/profile", { ...baseUpdate(profile!), ...patch });
      setProfile(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.displayMessage : "Couldn't save that change. Try again.");
    }
  }

  return (
    <div className="min-h-screen bg-paper">
      <AppNav />
      <main className={`mx-auto flex max-w-2xl flex-col gap-5 px-5 py-6 sm:px-8 ${BOTTOM_NAV_SPACER_CLASS}`}>
        <ProfileHeader profile={profile} />

        {error && (
          <p role="alert" className="rounded-[10px] bg-signal-soft px-4 py-3 font-body text-sm font-medium text-signal">
            {error}
          </p>
        )}

        <SkillsCard skills={profile.skills} onSave={(skills) => save({ skills })} />
        <PreferencesCard profile={profile} onSave={save} />
        <ExperienceCard profile={profile} onSave={save} />
        <CvCard profile={profile} />
      </main>
    </div>
  );
}

function ProfileHeader({ profile }: { profile: ProfileOut }) {
  return (
    <div className="rounded-2xl border border-hairline p-5">
      <div className="flex items-center gap-4">
        <span className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full bg-phanda-green/15 font-body text-lg font-bold text-phanda-green-dark">
          {initials(profile.email)}
        </span>
        <div className="min-w-0">
          <p className="truncate font-body text-[15px] font-semibold text-ink">{profile.email}</p>
          <p className="font-body text-sm text-ink/60">{profile.location || "No location set"}</p>
        </div>
      </div>

      <div className="mt-5">
        <div className="flex items-center justify-between">
          <p className="font-body text-sm font-medium text-ink/70">Profile strength</p>
          <p className="font-body text-sm font-semibold text-ink">{profile.profile_completeness}%</p>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-mist">
          <div
            className="h-full rounded-full bg-phanda-green transition-[width]"
            style={{ width: `${profile.profile_completeness}%` }}
          />
        </div>
      </div>
    </div>
  );
}

function Card({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="rounded-2xl border border-hairline p-5">
      <div className="flex items-center justify-between">
        <h2 className="font-body text-[15px] font-semibold text-ink">{title}</h2>
        {action}
      </div>
      <div className="mt-4">{children}</div>
    </section>
  );
}

function EditToggle({ editing, onToggle }: { editing: boolean; onToggle: () => void }) {
  return (
    <button onClick={onToggle} className="font-body text-sm font-semibold text-phanda-green-dark hover:underline">
      {editing ? "Cancel" : "Edit"}
    </button>
  );
}

function SkillsCard({ skills, onSave }: { skills: string[]; onSave: (skills: string[]) => Promise<void> }) {
  const [adding, setAdding] = useState(false);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);

  async function remove(skill: string) {
    setBusy(true);
    await onSave(skills.filter((s) => s !== skill));
    setBusy(false);
  }

  async function add() {
    const value = draft.trim();
    if (!value) {
      setAdding(false);
      return;
    }
    setBusy(true);
    await onSave(skills.some((s) => s.toLowerCase() === value.toLowerCase()) ? skills : [...skills, value]);
    setBusy(false);
    setDraft("");
    setAdding(false);
  }

  return (
    <Card title="Skills">
      {skills.length === 0 && !adding && (
        <p className="font-body text-sm text-ink/60">No skills added yet -- add a few to improve your matches.</p>
      )}
      <div className="flex flex-wrap gap-2">
        {skills.map((skill) => (
          <span
            key={skill}
            className="flex items-center gap-1.5 rounded-full bg-mist px-3 py-1.5 font-body text-sm text-ink"
          >
            {skill}
            <button
              onClick={() => remove(skill)}
              disabled={busy}
              aria-label={`Remove ${skill}`}
              className="text-ink/40 hover:text-signal disabled:opacity-40"
            >
              &times;
            </button>
          </span>
        ))}

        {adding ? (
          <span className="flex items-center gap-1.5">
            <input
              autoFocus
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && add()}
              placeholder="e.g. Excel"
              className="w-32 rounded-full border border-phanda-green px-3 py-1.5 font-body text-sm text-ink outline-none"
            />
            <button onClick={add} disabled={busy} className="font-body text-sm font-semibold text-phanda-green-dark">
              Add
            </button>
          </span>
        ) : (
          <button
            onClick={() => setAdding(true)}
            className="rounded-full border border-dashed border-hairline px-3 py-1.5 font-body text-sm text-ink/60 hover:border-phanda-green hover:text-phanda-green-dark"
          >
            + Add
          </button>
        )}
      </div>
    </Card>
  );
}

function PreferencesCard({ profile, onSave }: { profile: ProfileOut; onSave: (patch: ProfileUpdate) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [jobType, setJobType] = useState<JobType>(profile.job_type);
  const [openToRemote, setOpenToRemote] = useState(profile.open_to_remote);
  const [industriesInput, setIndustriesInput] = useState(profile.industries.join(", "));
  const [saving, setSaving] = useState(false);

  function startEditing() {
    setJobType(profile.job_type);
    setOpenToRemote(profile.open_to_remote);
    setIndustriesInput(profile.industries.join(", "));
    setEditing(true);
  }

  async function save() {
    setSaving(true);
    await onSave({
      job_type: jobType,
      open_to_remote: openToRemote,
      industries: industriesInput
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean),
    });
    setSaving(false);
    setEditing(false);
  }

  return (
    <Card
      title="Job preferences"
      action={<EditToggle editing={editing} onToggle={() => (editing ? setEditing(false) : startEditing())} />}
    >
      {!editing ? (
        <dl className="flex flex-col gap-3 font-body text-[15px]">
          <Row label="Looking for" value={JOB_TYPE_LABELS[profile.job_type]} />
          <Row label="Remote work" value={profile.open_to_remote ? "Open to it" : "Not right now"} />
          <Row label="Industries" value={profile.industries.length > 0 ? profile.industries.join(", ") : "Not set"} />
        </dl>
      ) : (
        <div className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="font-body text-sm font-medium text-ink">Looking for</span>
            <select
              value={jobType}
              onChange={(e) => setJobType(e.target.value as JobType)}
              className="rounded-[10px] border border-hairline bg-paper px-4 py-3 font-body text-[15px] text-ink outline-none focus:border-phanda-green"
            >
              {Object.entries(JOB_TYPE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <label className="flex items-center gap-2.5 font-body text-[15px] text-ink">
            <input
              type="checkbox"
              className="h-4 w-4 accent-phanda-green"
              checked={openToRemote}
              onChange={(e) => setOpenToRemote(e.target.checked)}
            />
            I'm open to remote work
          </label>
          <TextField
            label="Industries"
            placeholder="e.g. retail, logistics, hospitality"
            value={industriesInput}
            onChange={(e) => setIndustriesInput(e.target.value)}
          />
          <Button onClick={save} loading={saving} className="self-start">
            Save changes
          </Button>
        </div>
      )}
    </Card>
  );
}

function ExperienceCard({ profile, onSave }: { profile: ProfileOut; onSave: (patch: ProfileUpdate) => Promise<void> }) {
  const [editing, setEditing] = useState(false);
  const [experienceLevel, setExperienceLevel] = useState<ExperienceLevel>(profile.experience_level);
  const [educationLevel, setEducationLevel] = useState(profile.education_level ?? "");
  const [saving, setSaving] = useState(false);

  function startEditing() {
    setExperienceLevel(profile.experience_level);
    setEducationLevel(profile.education_level ?? "");
    setEditing(true);
  }

  async function save() {
    setSaving(true);
    await onSave({ experience_level: experienceLevel, education_level: educationLevel.trim() || null });
    setSaving(false);
    setEditing(false);
  }

  return (
    <Card
      title="Experience"
      action={<EditToggle editing={editing} onToggle={() => (editing ? setEditing(false) : startEditing())} />}
    >
      {!editing ? (
        <dl className="flex flex-col gap-3 font-body text-[15px]">
          <Row label="Work experience" value={EXPERIENCE_LABELS[profile.experience_level]} />
          <Row label="Education" value={profile.education_level || "Not set"} />
        </dl>
      ) : (
        <div className="flex flex-col gap-4">
          <label className="flex flex-col gap-1.5">
            <span className="font-body text-sm font-medium text-ink">Work experience</span>
            <select
              value={experienceLevel}
              onChange={(e) => setExperienceLevel(e.target.value as ExperienceLevel)}
              className="rounded-[10px] border border-hairline bg-paper px-4 py-3 font-body text-[15px] text-ink outline-none focus:border-phanda-green"
            >
              {Object.entries(EXPERIENCE_LABELS).map(([value, label]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </select>
          </label>
          <TextField
            label="Highest level of education"
            placeholder="e.g. Matric, National Diploma"
            value={educationLevel}
            onChange={(e) => setEducationLevel(e.target.value)}
          />
          <Button onClick={save} loading={saving} className="self-start">
            Save changes
          </Button>
        </div>
      )}
    </Card>
  );
}

function CvCard({ profile }: { profile: ProfileOut }) {
  const [version, setVersion] = useState<CvVersionOut | null>(null);

  useEffect(() => {
    if (!profile.active_cv_version_id) {
      setVersion(null);
      return;
    }
    let cancelled = false;
    api
      .get<CvVersionOut>(`/profile/cv-versions/${profile.active_cv_version_id}`)
      .then((result) => !cancelled && setVersion(result))
      .catch(() => !cancelled && setVersion(null));
    return () => {
      cancelled = true;
    };
  }, [profile.active_cv_version_id]);

  return (
    <Card title="CV">
      {profile.active_cv_version_id ? (
        <div className="flex items-center justify-between gap-4">
          <div>
            <p className="font-body text-[15px] font-semibold text-ink">
              {version ? CV_STATUS_LABELS[version.status] : "Loading status..."}
            </p>
            {version && (
              <p className="font-body text-sm text-ink/60">
                Uploaded {new Date(version.created_at).toLocaleDateString("en-ZA", { day: "numeric", month: "short", year: "numeric" })}
              </p>
            )}
          </div>
          <Link to="/onboarding/cv">
            <Button variant="secondary">Replace</Button>
          </Link>
        </div>
      ) : (
        <div className="flex items-center justify-between gap-4">
          <p className="font-body text-sm text-ink/60">No CV uploaded yet.</p>
          <Link to="/onboarding/cv">
            <Button variant="secondary">Upload a CV</Button>
          </Link>
        </div>
      )}
    </Card>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <dt className="text-ink/60">{label}</dt>
      <dd className="text-right font-medium text-ink">{value}</dd>
    </div>
  );
}
