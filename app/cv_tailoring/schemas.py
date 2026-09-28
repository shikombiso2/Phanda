from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from app.core.models import TailoredDocumentStatus


class SourceSpan(BaseModel):
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    excerpt: str = Field(min_length=1, max_length=600)


class CandidateFact(BaseModel):
    id: str = Field(pattern=r"^fact_[a-zA-Z0-9_-]+$")
    category: str = Field(pattern=r"^(experience|education|skill|project|certification|contact)$")
    normalized_value: str = Field(min_length=1, max_length=1000)
    source_spans: list[SourceSpan] = Field(min_length=1)
    confidence: float = Field(ge=0, le=1)


class CandidateFacts(BaseModel):
    facts: list[CandidateFact] = Field(default_factory=list)


class JobRequirement(BaseModel):
    id: str = Field(pattern=r"^job_[a-zA-Z0-9_-]+$")
    category: str
    text: str = Field(min_length=1, max_length=1000)
    required: bool = True


class JobRequirements(BaseModel):
    requirements: list[JobRequirement] = Field(default_factory=list)


class MatchingStrategy(BaseModel):
    emphasize_fact_ids: list[str] = Field(default_factory=list)
    allowed_job_requirement_ids: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AnalysisPlan(BaseModel):
    candidate_facts: CandidateFacts
    job_requirements: JobRequirements
    strategy: MatchingStrategy


class CvClaim(BaseModel):
    text: str = Field(min_length=1, max_length=1500)
    source_fact_ids: list[str] = Field(min_length=1)
    job_requirement_ids: list[str] = Field(default_factory=list)


class CvSection(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    claims: list[CvClaim] = Field(default_factory=list)


class TailoredCv(BaseModel):
    sections: list[CvSection] = Field(min_length=1)
    cover_letter: list[CvClaim] = Field(min_length=1)
    # A plain sign-off ("Kind regards, <candidate name>"), not a CvClaim: it
    # doesn't cite a candidate fact the way a body claim does, it just names
    # the candidate -- who they are, not a claim about them. Required so a
    # generated cover letter can never end abruptly on a body claim with no
    # closing at all (confirmed live: the pre-fix output did exactly that).
    cover_letter_closing: str = Field(min_length=1, max_length=200)


class ValidationIssue(BaseModel):
    code: str
    detail: str
    section: str | None = None


class TailoringRequestIn(BaseModel):
    listing_id: uuid.UUID
    cv_version_id: uuid.UUID | None = None


class TailoringAllowanceOut(BaseModel):
    included_remaining: int
    rewarded_credits_available: int
    premium_active: bool
    premium_remaining: int | None
    should_offer_ad: bool
    should_show_paywall: bool

    model_config = {"from_attributes": True}


class TailoredDocumentOut(BaseModel):
    id: uuid.UUID
    listing_id: uuid.UUID
    cv_version_id: uuid.UUID
    status: TailoredDocumentStatus
    failure_code: str | None
    created_at: datetime
    ready_at: datetime | None

    model_config = {"from_attributes": True}
