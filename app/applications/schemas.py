import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.models import AppliedVia, ApplicationStatus, ApplyMethod
from app.listings.schemas import ListingSummaryOut


class ApplicationCreate(BaseModel):
    tailored_document_id: uuid.UUID | None = None


class ApplicationStatusUpdate(BaseModel):
    status: ApplicationStatus


class ApplyOut(BaseModel):
    id: uuid.UUID
    listing_id: uuid.UUID
    status: ApplicationStatus
    tailored_document_id: uuid.UUID | None
    applied_via: AppliedVia
    applied_at: datetime
    apply_method: ApplyMethod
    apply_target: str | None
    """The employer's own application URL when apply_method is ats_link --
    the Android client opens this to let the user finish applying. Null for
    apply_method=email, where Phanda has already sent the application on the
    user's behalf and there is nothing further for the client to open."""

    model_config = {"from_attributes": True}


class ApplicationOut(BaseModel):
    id: uuid.UUID
    listing_id: uuid.UUID
    listing: ListingSummaryOut
    status: ApplicationStatus
    tailored_document_id: uuid.UUID | None
    applied_via: AppliedVia
    applied_at: datetime

    model_config = {"from_attributes": True}
