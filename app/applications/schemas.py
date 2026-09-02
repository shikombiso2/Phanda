import uuid
from datetime import datetime

from pydantic import BaseModel

from app.core.models import AppliedVia, ApplicationStatus


class ApplicationCreate(BaseModel):
    tailored_document_id: uuid.UUID | None = None


class ApplyOut(BaseModel):
    id: uuid.UUID
    listing_id: uuid.UUID
    status: ApplicationStatus
    tailored_document_id: uuid.UUID | None
    applied_via: AppliedVia
    applied_at: datetime

    model_config = {"from_attributes": True}


class ApplicationOut(BaseModel):
    id: uuid.UUID
    listing_id: uuid.UUID
    status: ApplicationStatus
    tailored_document_id: uuid.UUID | None
    applied_via: AppliedVia
    applied_at: datetime

    model_config = {"from_attributes": True}
