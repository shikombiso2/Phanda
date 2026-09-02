from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.models import Listing, utcnow
from app.core.observability import emit_event
from app.listings.ingestion.normalize import NormalizedListing


def upsert_listings(db: Session, normalized: list[NormalizedListing]) -> int:
    seen = 0
    now = utcnow()
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
        listing.ingested_at = now
        listing.last_seen_at = now
        listing.is_active = True
        seen += 1
    db.commit()
    return seen


def deactivate_stale_listings(db: Session, source: str | None = None) -> int:
    """Mark inactive any listing not seen in the most recent ingestion pulls
    for its source in over ``listing_stale_after_days``. Scoped to a single
    source when given, since different sources refresh on different
    schedules and one source's outage should not silently deactivate every
    other source's listings."""
    cutoff = utcnow() - timedelta(days=get_settings().listing_stale_after_days)
    query = update(Listing).where(Listing.is_active.is_(True), Listing.last_seen_at < cutoff)
    if source:
        query = query.where(Listing.source == source)
    result = db.execute(query.values(is_active=False))
    db.commit()
    deactivated = result.rowcount or 0
    if deactivated:
        emit_event("listings_deactivated", count=deactivated, source=source or "all")
    return deactivated
