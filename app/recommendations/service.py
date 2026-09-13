"""Orchestrates scoring: builds the explained match for one listing, and
ranks every active listing for a profile.

Kept out of app/listings/router.py deliberately -- recommendation logic is
its own concern with its own tests, not something to bury inside a listings
CRUD router.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import Application, CvVersion, CvVersionStatus, Listing, Profile, SavedOpportunity, TailoredDocument
from app.recommendations import features
from app.recommendations.schemas import CompatibilityFactor, MatchExplanation
from app.recommendations.scoring import FACTOR_WEIGHTS, combine, score_from_probability


def build_match_explanation(profile: Profile, listing: Listing, engaged_skills: set[str], cv_skills: list[str]) -> MatchExplanation:
    factors: list[CompatibilityFactor] = []

    skill_probability, matched, missing = features.skill_compatibility(
        profile.skills or [], cv_skills, listing.required_skills or []
    )
    factors.append(_factor("skills", "Skill match", skill_probability, detail=_skill_detail(matched, missing)))

    experience_probability, listing_seniority = features.experience_compatibility(
        profile.experience_level, listing.title, listing.description
    )
    factors.append(_factor("experience", "Experience level", experience_probability, detail=_seniority_detail(listing_seniority)))

    factors.append(_factor("job_type", "Role type", features.job_type_compatibility(profile.job_type, listing.listing_type)))

    factors.append(
        _factor(
            "location",
            "Location",
            features.location_compatibility(profile.location, profile.open_to_remote, listing.location),
        )
    )

    factors.append(_factor("industry", "Industry", features.industry_compatibility(profile.industries or [], listing.category)))

    factors.append(
        _factor(
            "salary",
            "Salary",
            features.salary_compatibility(profile.desired_salary_min, profile.desired_salary_max, listing.salary_min, listing.salary_max),
        )
    )

    engagement_probability, applicable = features.engagement_compatibility(listing.required_skills or [], engaged_skills)
    if applicable:
        factors.append(_factor("engagement", "Similar to jobs you've engaged with", engagement_probability))

    probability = combine(factors)
    return MatchExplanation(
        score=score_from_probability(probability),
        matched_skills=matched,
        missing_skills=missing,
        factors=factors,
        summary=_summarize(factors, matched, missing),
    )


def score_listings_for_profile(db: Session, profile: Profile, listings: list[Listing]) -> list[tuple[Listing, MatchExplanation]]:
    engaged_skills = _engaged_skills(db, profile.user_id)
    cv_skills = active_cv_skills(db, profile)
    scored = [(listing, build_match_explanation(profile, listing, engaged_skills, cv_skills)) for listing in listings]
    return sorted(scored, key=lambda row: row[1].score, reverse=True)


def active_cv_skills(db: Session, profile: Profile) -> list[str]:
    """The active CV's extracted_skills, computed once at CV-ready time (see
    app/cv_tailoring/tasks.py) and just read back here -- never recomputed
    inside this request path. Empty for a profile with no CV, or whose CV
    hasn't finished processing yet -- both are ordinary states, not errors."""
    if not profile.active_cv_version_id:
        return []
    cv_version = db.get(CvVersion, profile.active_cv_version_id)
    if not cv_version or cv_version.status != CvVersionStatus.ready:
        return []
    return cv_version.extracted_skills or []


def _engaged_skills(db: Session, user_id) -> set[str]:
    """Skills drawn from listings the user has saved, applied to, or
    requested a tailored CV for -- a light, fully-explainable use of
    interaction history. Not collaborative filtering (nothing here compares
    across users): just "this listing looks like things you've already
    shown interest in", which is honest to compute with the sparse,
    single-user interaction volume a new product actually has at launch.
    """
    saved_listing_ids = db.scalars(select(SavedOpportunity.listing_id).where(SavedOpportunity.user_id == user_id))
    applied_listing_ids = db.scalars(select(Application.listing_id).where(Application.user_id == user_id))
    tailored_listing_ids = db.scalars(select(TailoredDocument.listing_id).where(TailoredDocument.user_id == user_id))
    listing_ids = set(saved_listing_ids) | set(applied_listing_ids) | set(tailored_listing_ids)
    if not listing_ids:
        return set()
    skill_lists = db.scalars(select(Listing.required_skills).where(Listing.id.in_(listing_ids)))
    return {features.normalize_skill(skill) for skills in skill_lists for skill in (skills or [])}


def _factor(key: str, label: str, probability: float, *, detail: str | None = None) -> CompatibilityFactor:
    return CompatibilityFactor(key=key, label=label, probability=round(probability, 3), weight=FACTOR_WEIGHTS[key], detail=detail)


def _skill_detail(matched: list[str], missing: list[str]) -> str | None:
    total = len(matched) + len(missing)
    if total == 0:
        return None
    return f"{len(matched)} of {total} required skills"


def _seniority_detail(listing_seniority: int | None) -> str | None:
    return {0: "Entry-level role", 2: "Senior-level role"}.get(listing_seniority)


def _summarize(factors: list[CompatibilityFactor], matched: list[str], missing: list[str]) -> str:
    strong = sorted((f for f in factors if f.probability >= 0.75), key=lambda f: f.probability, reverse=True)
    weak = sorted((f for f in factors if f.probability <= 0.3), key=lambda f: f.probability)

    if not strong:
        if missing:
            return f"Missing: {', '.join(missing[:3])}."
        if weak:
            return f"Weaker {weak[0].label.lower()}."
        return "Not enough profile information yet to judge fit confidently."

    strong_labels = " and ".join(f.label.lower() for f in strong[:2])
    if weak:
        return f"Strong {strong_labels}, but a weaker {weak[0].label.lower()}."
    return f"Strong {strong_labels}."
