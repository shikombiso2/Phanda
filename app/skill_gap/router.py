import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.errors import raise_access_blocked
from app.core.models import Listing, Profile, User
from app.core.security import get_current_user
from app.matching.service import score_listing
from app.monetization.gate import check_access
from app.skill_gap.resources import SKILL_RESOURCES
from app.skill_gap.schemas import RoadmapOut, SkillGapOut

router = APIRouter(prefix="/skill-gap", tags=["skill-gap"])


@router.get("", response_model=SkillGapOut)
def skill_gap(
    listing_id: uuid.UUID | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> SkillGapOut:
    profile = db.get(Profile, user.id)
    if not profile:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Profile not found")
    listings = [db.get(Listing, listing_id)] if listing_id else db.scalars(select(Listing).where(Listing.is_active.is_(True))).all()
    missing = sorted({skill for listing in listings if listing for skill in score_listing(profile, listing)["missing_skills"]})
    return SkillGapOut(missing_skills=missing)


@router.post("/roadmap/{skill}", response_model=RoadmapOut)
def skill_gap_roadmap(
    skill: str,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> RoadmapOut:
    access = check_access(db, user.id, "skill_gap_roadmap")
    if not access.allowed:
        raise_access_blocked(access)
    normalized = skill.strip().lower()
    return RoadmapOut(skill=normalized, resources=SKILL_RESOURCES.get(normalized, []), access_reason=access.reason)
