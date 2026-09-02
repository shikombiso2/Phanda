from pydantic import BaseModel

from app.listings.schemas import ListingOut


class CompatibilityFactor(BaseModel):
    key: str
    label: str
    probability: float
    weight: float
    detail: str | None = None


class MatchExplanation(BaseModel):
    score: int
    matched_skills: list[str]
    missing_skills: list[str]
    factors: list[CompatibilityFactor]
    summary: str


class MatchedListingOut(ListingOut):
    match: MatchExplanation
