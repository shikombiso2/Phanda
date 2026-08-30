import json

from anthropic import Anthropic

from app.core.config import get_settings
from app.core.models import Listing, Profile
from app.core.storage import upload_bytes


def generate_tailored_documents(profile: Profile, listing: Listing) -> tuple[str, str]:
    settings = get_settings()
    if not settings.anthropic_api_key:
        cv = _fallback_cv(profile, listing)
        cover = _fallback_cover_letter(profile, listing)
    else:
        cv, cover = _call_anthropic(profile, listing)

    cv_url = upload_bytes(cv.encode("utf-8"), f"users/{profile.user_id}/generated/cv", "text/markdown")
    cover_url = upload_bytes(cover.encode("utf-8"), f"users/{profile.user_id}/generated/cover-letter", "text/markdown")
    return cv_url, cover_url


def _call_anthropic(profile: Profile, listing: Listing) -> tuple[str, str]:
    settings = get_settings()
    client = Anthropic(api_key=settings.anthropic_api_key)
    prompt = {
        "profile": {
            "location": profile.location,
            "skills": profile.skills,
            "industries": profile.industries,
            "education_level": profile.education_level,
            "experience_level": profile.experience_level.value,
            "cv_file_url": profile.cv_file_url,
        },
        "listing": {
            "title": listing.title,
            "company": listing.company,
            "location": listing.location,
            "description": listing.description,
            "required_skills": listing.required_skills,
        },
    }
    message = client.messages.create(
        model=settings.anthropic_model,
        max_tokens=3000,
        messages=[
            {
                "role": "user",
                "content": (
                    "Create a tailored CV and cover letter for a South African youth employment applicant. "
                    "Return valid JSON with keys tailored_cv_markdown and cover_letter_markdown.\n\n"
                    + json.dumps(prompt)
                ),
            }
        ],
    )
    text = "".join(block.text for block in message.content if getattr(block, "type", None) == "text")
    data = json.loads(text)
    return data["tailored_cv_markdown"], data["cover_letter_markdown"]


def _fallback_cv(profile: Profile, listing: Listing) -> str:
    skills = ", ".join(profile.skills or []) or "Entry-level skills"
    return f"# Tailored CV\n\nTarget role: {listing.title}\n\nLocation: {profile.location or 'South Africa'}\n\nSkills: {skills}\n"


def _fallback_cover_letter(profile: Profile, listing: Listing) -> str:
    company = listing.company or "your team"
    skills = ", ".join(profile.skills or []) or "a strong willingness to learn"
    return (
        "# Cover Letter\n\n"
        f"Dear {company},\n\n"
        f"I am applying for the {listing.title} opportunity. My background includes {skills}, "
        "and I am excited to contribute while continuing to grow professionally.\n"
    )

