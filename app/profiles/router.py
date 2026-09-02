import hashlib
import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import CvVersion, Profile, User
from app.core.security import get_current_user
from app.core.storage import put_bytes, read_upload
from app.cv_tailoring.extraction import CvExtractionError, validate_upload
from app.profiles.schemas import CvUploadOut, ProfileOut, ProfileUpdate
from app.profiles.service import compute_profile_completeness

router = APIRouter(prefix="/profile", tags=["profile"])


def get_or_create_profile(user: User, db: Session) -> Profile:
    profile = db.get(Profile, user.id)
    if not profile:
        profile = Profile(user_id=user.id)
        db.add(profile)
        db.flush()
    return profile


@router.get("", response_model=ProfileOut)
def get_profile(user: User = Depends(get_current_user), db: Session = Depends(get_db)) -> Profile:
    profile = get_or_create_profile(user, db)
    profile.profile_completeness = compute_profile_completeness(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.put("", response_model=ProfileOut)
def update_profile(
    payload: ProfileUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> Profile:
    profile = get_or_create_profile(user, db)
    user.email = payload.email
    for field, value in payload.model_dump(exclude={"email"}).items():
        setattr(profile, field, value)
    profile.profile_completeness = compute_profile_completeness(profile)
    db.commit()
    db.refresh(profile)
    return profile


@router.post("/cv-upload", response_model=CvUploadOut)
async def upload_cv(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> CvUploadOut:
    profile = get_or_create_profile(user, db)
    data = await read_upload(file, max_bytes=5 * 1024 * 1024)
    try:
        info = validate_upload(file.filename, file.content_type, data)
    except CvExtractionError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    file_hash = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(CvVersion).where(CvVersion.user_id == user.id, CvVersion.sha256 == file_hash))
    if existing:
        if existing.status.value == "ready":
            profile.active_cv_version_id = existing.id
            profile.profile_completeness = compute_profile_completeness(profile)
            db.commit()
        return CvUploadOut(
            cv_version_id=existing.id,
            status=existing.status.value,
            profile_completeness=profile.profile_completeness,
        )

    next_version = (db.scalar(select(func.max(CvVersion.version_number)).where(CvVersion.user_id == user.id)) or 0) + 1
    cv_version_id = uuid.uuid4()
    key = f"users/{user.id}/cv-versions/{cv_version_id}/original.{info.format}"
    try:
        put_bytes(data, key, info.content_type)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="CV storage is unavailable") from exc

    cv_version = CvVersion(
        id=cv_version_id,
        user_id=user.id,
        version_number=next_version,
        storage_key=key,
        filename=info.filename,
        content_type=info.content_type,
        byte_size=len(data),
        sha256=file_hash,
    )
    db.add(cv_version)
    profile.profile_completeness = compute_profile_completeness(profile)
    db.commit()
    from app.cv_tailoring.tasks import extract_cv_version

    extract_cv_version.delay(str(cv_version.id))
    return CvUploadOut(cv_version_id=cv_version.id, status=cv_version.status.value, profile_completeness=profile.profile_completeness)
