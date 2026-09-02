"""Seed a local dev account and two sample listings.

Requires the schema to already exist — run ``alembic upgrade head`` first.
This script used to call ``Base.metadata.create_all()`` itself, which meant
the ORM models (not a tracked migration) were the real source of truth for
the schema on anyone's first run. That is exactly the gap that made
``alembic upgrade head`` fail on a fresh database, so it is deliberately not
done here any more.
"""

from sqlalchemy import inspect

from app.core.db import SessionLocal, engine
from app.core.models import ApplyMethod, JobType, Listing, ListingType, Profile, User, utcnow
from app.core.security import hash_password
from app.profiles.service import compute_profile_completeness

DEV_EMAIL = "dev@phanda.local"
DEV_PASSWORD = "PhandaDev123!"


def main() -> None:
    if not inspect(engine).has_table("users"):
        raise SystemExit(
            "The 'users' table does not exist yet. Run `alembic upgrade head` before seeding — "
            "this script no longer creates the schema itself."
        )

    with SessionLocal() as db:
        user = db.query(User).filter(User.email == DEV_EMAIL).one_or_none()
        if not user:
            user = User(email=DEV_EMAIL, password_hash=hash_password(DEV_PASSWORD), email_verified_at=utcnow())
            db.add(user)
            db.flush()

        profile = db.get(Profile, user.id)
        if not profile:
            profile = Profile(user_id=user.id)
            db.add(profile)
        profile.job_type = JobType.any
        profile.location = "Johannesburg"
        profile.open_to_remote = True
        profile.skills = ["excel", "communication", "customer service"]
        profile.industries = ["retail", "admin"]
        profile.education_level = "matric"
        profile.profile_completeness = compute_profile_completeness(profile)

        _upsert_listing(
            db,
            source_listing_id="dev-ats-1",
            title="Junior Admin Assistant",
            company="Ubuntu Careers",
            location="Johannesburg",
            description="Entry-level admin role requiring Excel, communication and data entry.",
            required_skills=["admin", "excel", "communication", "data entry"],
            apply_method=ApplyMethod.ats_link,
            apply_target="https://example.com/apply/admin-assistant",
        )
        _upsert_listing(
            db,
            source_listing_id="dev-email-1",
            title="Customer Service Learnership",
            company="Mzansi Retail Group",
            location="Cape Town",
            description="Learnership for candidates with customer service, communication and retail interest.",
            required_skills=["customer service", "communication", "retail"],
            apply_method=ApplyMethod.email,
            apply_target="applications@example.co.za",
            listing_type=ListingType.learnership,
        )

        db.commit()
        print(f"Seeded dev user {user.id}")
        print(f"  email:    {DEV_EMAIL}")
        print(f"  password: {DEV_PASSWORD}")


def _upsert_listing(
    db,
    *,
    source_listing_id: str,
    title: str,
    company: str,
    location: str,
    description: str,
    required_skills: list[str],
    apply_method: ApplyMethod,
    apply_target: str,
    listing_type: ListingType = ListingType.job,
) -> None:
    listing = db.query(Listing).filter(Listing.source == "dev", Listing.source_listing_id == source_listing_id).one_or_none()
    if not listing:
        listing = Listing(source="dev", source_listing_id=source_listing_id)
        db.add(listing)
    listing.title = title
    listing.company = company
    listing.location = location
    listing.listing_type = listing_type
    listing.description = description
    listing.required_skills = required_skills
    listing.apply_method = apply_method
    listing.apply_target = apply_target
    listing.is_active = True


if __name__ == "__main__":
    main()
