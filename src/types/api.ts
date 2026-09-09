export interface ErrorEnvelope {
  code: string;
  message: string;
  details?: unknown;
}

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
  has_more: boolean;
}

export interface AuthTokens {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  is_new_user: boolean;
}

export type CvVersionStatus = "uploaded" | "extracting" | "ready" | "failed";

export interface CvVersionOut {
  id: string;
  status: CvVersionStatus;
  failure_code: string | null;
  created_at: string;
}

export interface CvUploadOut {
  cv_version_id: string;
  status: CvVersionStatus;
  profile_completeness: number;
}

export type JobType = "any" | "learnership" | "internship" | "full_time" | "part_time";
export type ExperienceLevel = "none" | "some" | "experienced";

export interface ProfileOut {
  email: string;
  job_type: JobType;
  location: string | null;
  open_to_remote: boolean;
  skills: string[];
  industries: string[];
  education_level: string | null;
  experience_level: ExperienceLevel;
  desired_salary_min: number | null;
  desired_salary_max: number | null;
  cv_file_url: string | null;
  active_cv_version_id: string | null;
  profile_completeness: number;
}

/** Every field optional: this is a PATCH-shaped body, and PUT /profile
 * never accepts email -- the backend rejects it outright if sent. */
export interface ProfileUpdate {
  job_type?: JobType;
  location?: string | null;
  open_to_remote?: boolean;
  skills?: string[];
  industries?: string[];
  education_level?: string | null;
  experience_level?: ExperienceLevel;
  desired_salary_min?: number | null;
  desired_salary_max?: number | null;
}

export type ListingType = "job" | "internship" | "learnership" | "apprenticeship" | "bursary";
export type ApplyMethod = "ats_link" | "email";
export type AppliedVia = "phanda_email" | "external_link";
export type ApplicationStatus =
  | "prepared"
  | "external_started"
  | "applied"
  | "interview"
  | "offer"
  | "rejected"
  | "withdrawn";

/**
 * salary_period/salary_currency are typed as plain `string | null`, not a
 * literal union, on purpose: the database column is a free String(20)/
 * String(8), not a backend-enforced enum (confirmed in app/core/models.py --
 * ingestion stores whatever the source says, e.g. Himalayas' raw
 * `salaryPeriod`/`currency` values, unconverted). Assuming a fixed set of
 * values here would silently swallow anything outside it.
 *
 * Note these two fields are declared on the Listing model but are NOT
 * currently included in ListingOut / ListingSummaryOut (verified by reading
 * app/listings/schemas.py directly) -- the live API does not send them
 * today. They're kept here, and every salary renderer already refuses to
 * show an amount when either is missing, so this is forward-compatible
 * with zero risk: today it just means salary never renders, which is the
 * correct behaviour per the "never show an amount without its units" rule,
 * not a bug to work around.
 */
export interface ListingSummary {
  id: string;
  title: string;
  company: string | null;
  location: string | null;
  listing_type: ListingType;
  salary_min: number | null;
  salary_max: number | null;
  salary_period?: string | null;
  salary_currency?: string | null;
  required_skills: string[];
  posted_at: string | null;
}

export interface Listing {
  id: string;
  source: string;
  source_listing_id: string;
  title: string;
  company: string | null;
  location: string | null;
  listing_type: ListingType;
  category: string | null;
  salary_min: number | null;
  salary_max: number | null;
  salary_period?: string | null;
  salary_currency?: string | null;
  description: string;
  required_skills: string[];
  apply_method: ApplyMethod;
  apply_target: string;
  posted_at: string | null;
  ingested_at: string;
  is_active: boolean;
}

export interface CompatibilityFactor {
  key: string;
  label: string;
  probability: number;
  weight: number;
  detail: string | null;
}

export interface MatchExplanation {
  score: number;
  matched_skills: string[];
  missing_skills: string[];
  factors: CompatibilityFactor[];
  summary: string;
}

export interface MatchedListing extends Listing {
  match: MatchExplanation;
}

export interface ApplyOut {
  id: string;
  listing_id: string;
  status: ApplicationStatus;
  tailored_document_id: string | null;
  applied_via: AppliedVia;
  applied_at: string;
  apply_method: ApplyMethod;
  /** The employer's own application page when apply_method is "ats_link".
   * Null for "email", where Phanda has already sent it on the user's
   * behalf -- there's nothing left for the client to open. */
  apply_target: string | null;
}

export interface ApplicationOut {
  id: string;
  listing_id: string;
  listing: ListingSummary;
  status: ApplicationStatus;
  tailored_document_id: string | null;
  applied_via: AppliedVia;
  applied_at: string;
}

export interface SkillGapOut {
  missing_skills: string[];
}

export interface SkillResource {
  title: string;
  url: string;
}

export interface RoadmapOut {
  skill: string;
  /** Empty, not absent, when the skill has no curated resources yet --
   * app/skill_gap/resources.py only covers a handful of skills today. Not
   * an error case; render it as "nothing here yet", not a failure. */
  resources: SkillResource[];
  /** "free_quota" | "boost_token" on success. A blocked call (quota used
   * up) doesn't reach this type at all -- it's a 402 ApiError instead,
   * with code "watch_ad_available" or "paywall_required". */
  access_reason: string;
}
