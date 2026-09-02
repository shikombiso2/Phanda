from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.models import Listing, utcnow
from app.listings.ingestion.normalize import NormalizedListing


def upsert_listings(db: Session, normalized: list[NormalizedListing]) -> int:
    seen = 0
    for row in normalized:
        listing = db.scalar(
            select(Listing).where(Listing.source == row.source, Listing.source_listing_id == row.source_listing_id)
        )
        if not listing:
            listing = Listing(source=row.source, source_listing_id=row.source_listing_id)
            db.add(listing)
        listing.title = row.title
        listing.company = row.company
        listing.location = row.location
        listing.listing_type = row.listing_type
        listing.category = row.category
        listing.salary_min = row.salary_min
        listing.salary_max = row.salary_max
        listing.description = row.description
        listing.required_skills = row.required_skills
        listing.apply_method = row.apply_method
        listing.apply_target = row.apply_target
        listing.posted_at = row.posted_at
        listing.ingested_at = utcnow()
        listing.is_active = True
        seen += 1
    db.commit()
    return seen

