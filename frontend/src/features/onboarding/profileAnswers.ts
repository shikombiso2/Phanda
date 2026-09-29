import type { ExperienceLevel, JobType, ProfileOut, ProfileUpdate } from "../../types/api";

/**
 * The profile questionnaire's field-collection state, shared between the
 * authenticated edit flow (ProfileWizard) and the pre-account signup wizard
 * (SignupWizard). Kept as raw strings for the list/number fields (not
 * string[] / number | null) because that's what a text input naturally
 * produces -- parsing only happens once, at the point each flow actually
 * sends a payload.
 */
export interface ProfileAnswers {
  jobType: JobType;
  location: string;
  openToRemote: boolean;
  experienceLevel: ExperienceLevel;
  educationLevel: string;
  skillsInput: string;
  industriesInput: string;
  salaryMin: string;
  salaryMax: string;
}

export const emptyProfileAnswers: ProfileAnswers = {
  jobType: "any",
  location: "",
  openToRemote: false,
  experienceLevel: "none",
  educationLevel: "",
  skillsInput: "",
  industriesInput: "",
  salaryMin: "",
  salaryMax: "",
};

/** Seeds the questionnaire from an existing profile, so reopening it to
 * edit one field doesn't blank out everything else (see profileAnswersToUpdate). */
export function profileAnswersFromProfile(profile: ProfileOut): ProfileAnswers {
  return {
    jobType: profile.job_type,
    location: profile.location ?? "",
    openToRemote: profile.open_to_remote,
    experienceLevel: profile.experience_level,
    educationLevel: profile.education_level ?? "",
    skillsInput: profile.skills.join(", "),
    industriesInput: profile.industries.join(", "),
    salaryMin: profile.desired_salary_min?.toString() ?? "",
    salaryMax: profile.desired_salary_max?.toString() ?? "",
  };
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

/** Every ProfileUpdate field, always -- PUT /profile is a full replace on
 * the backend (confirmed against the live API: it calls payload.model_dump()
 * with no exclude_unset, and every field has a hard default), so a payload
 * missing a field doesn't leave it untouched, it resets it. */
export function profileAnswersToUpdate(answers: ProfileAnswers): ProfileUpdate {
  return {
    job_type: answers.jobType,
    location: answers.location.trim() || null,
    open_to_remote: answers.openToRemote,
    experience_level: answers.experienceLevel,
    education_level: answers.educationLevel.trim() || null,
    skills: parseList(answers.skillsInput),
    industries: parseList(answers.industriesInput),
    desired_salary_min: parseSalary(answers.salaryMin),
    desired_salary_max: parseSalary(answers.salaryMax),
  };
}

/** True if every field is still at its default -- i.e. the user skipped
 * the questionnaire (or answered nothing) rather than filling anything in.
 * Used to decide whether a pre-account signup flow needs to call
 * PUT /profile at all after the account is created. */
export function isProfileAnswersEmpty(answers: ProfileAnswers): boolean {
  return (
    answers.jobType === emptyProfileAnswers.jobType &&
    answers.location.trim() === "" &&
    answers.openToRemote === false &&
    answers.experienceLevel === emptyProfileAnswers.experienceLevel &&
    answers.educationLevel.trim() === "" &&
    parseList(answers.skillsInput).length === 0 &&
    parseList(answers.industriesInput).length === 0 &&
    answers.salaryMin.trim() === "" &&
    answers.salaryMax.trim() === ""
  );
}
