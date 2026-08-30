import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.models import AppliedVia, ApplicationStatus


class ApplyOut(BaseModel):
    id: uuid.UUID
    listing_id: uuid.UUID
    status: ApplicationStatus
    tailored_cv_url: str | None
    tailored_cover_letter_url: str | None
    applied_via: AppliedVia
    applied_at: datetime
    next_step_url: str | None = None
    access_reason: str

    model_config = {"from_attributes": True}


class ApplicationOut(BaseModel):
    id: uuid.UUID
    listing_id: uuid.UUID
    status: ApplicationStatus
    tailored_cv_url: str | None
    tailored_cover_letter_url: str | None
    applied_via: AppliedVia
    applied_at: datetime

    model_config = {"from_attributes": True}

