import uuid

from pydantic import BaseModel, Field

from app.core.models import ExperienceLevel, JobType


class ProfileBase(BaseModel):
    job_type: JobType = JobType.any
    location: str | None = None
    open_to_remote: bool = False
    skills: list[str] = Field(default_factory=list)
    industries: list[str] = Field(default_factory=list)
    education_level: str | None = None
    experience_level: ExperienceLevel = ExperienceLevel.none
    desired_salary_min: int | None = None
    desired_salary_max: int | None = None


class ProfileUpdate(ProfileBase):
    email: str | None = None


class ProfileOut(ProfileBase):
    user_id: uuid.UUID
    cv_file_url: str | None
    profile_completeness: int

    model_config = {"from_attributes": True}


class CvUploadOut(BaseModel):
    cv_file_url: str
    profile_completeness: int

