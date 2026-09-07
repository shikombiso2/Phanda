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
export type ExperienceLevel = "none" | "under_1_year" | "1_to_3_years" | "3_plus_years";

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

export interface ListingSummary {
  id: string;
  title: string;
  company: string | null;
  location: string | null;
  listing_type: string | null;
}
