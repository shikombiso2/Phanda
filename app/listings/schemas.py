import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.models import ApplyMethod, ListingType


class ListingOut(BaseModel):
    id: uuid.UUID
    source: str
    source_listing_id: str
    title: str
    company: str | None
    location: str | None
    listing_type: ListingType
    salary_min: int | None
    salary_max: int | None
    description: str
    required_skills: list[str]
    apply_method: ApplyMethod
    apply_target: str
    posted_at: datetime | None
    ingested_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}


class MatchBreakdown(BaseModel):
    score: int
    matched_skills: list[str]
    missing_skills: list[str]


class ListingMatchOut(ListingOut):
    match: MatchBreakdown

