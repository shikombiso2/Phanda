from fastapi import APIRouter, Depends, File, UploadFile
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.models import Profile, User
from app.core.security import get_current_user
from app.core.storage import upload_file
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
    profile.cv_file_url = await upload_file(file, f"users/{user.id}/uploaded-cv")
    profile.profile_completeness = compute_profile_completeness(profile)
    db.commit()
    return CvUploadOut(cv_file_url=profile.cv_file_url, profile_completeness=profile.profile_completeness)

