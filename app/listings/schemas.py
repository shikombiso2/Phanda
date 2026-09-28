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
    category: str | None
    salary_min: int | None
    salary_max: int | None
    salary_period: str | None
    salary_currency: str | None
    description: str
    required_skills: list[str]
    apply_method: ApplyMethod
    apply_target: str
    posted_at: datetime | None
    ingested_at: datetime
    is_active: bool

    model_config = {"from_attributes": True}


class ListingSummaryOut(BaseModel):
    """Trimmed shape for list views: no `description`, which can run to
    several thousand characters and has no place in a scrollable list."""

    id: uuid.UUID
    title: str
    company: str | None
    location: str | None
    listing_type: ListingType
    salary_min: int | None
    salary_max: int | None
    salary_period: str | None
    salary_currency: str | None
    required_skills: list[str]
    apply_method: ApplyMethod
    """Needed even in the trimmed list shape: a manual (e.g. DPSA) listing
    needs to be flagged as such before the user ever taps into it, not just
    on the detail view."""
    posted_at: datetime | None

    model_config = {"from_attributes": True}

