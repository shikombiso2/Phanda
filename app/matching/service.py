from app.core.models import Listing, Profile


def normalize_skill(value: str) -> str:
    return value.strip().lower()


def score_listing(profile: Profile, listing: Listing) -> dict:
    required = sorted({normalize_skill(skill) for skill in (listing.required_skills or []) if skill.strip()})
    owned = {normalize_skill(skill) for skill in (profile.skills or []) if skill.strip()}
    if not required:
        return {"score": 0, "matched_skills": [], "missing_skills": []}

    matched = [skill for skill in required if skill in owned]
    missing = [skill for skill in required if skill not in owned]
    score = round(len(matched) / len(required) * 100)
    return {"score": score, "matched_skills": matched, "missing_skills": missing}

