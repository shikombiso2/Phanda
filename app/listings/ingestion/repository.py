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
        listing.salary_period = row.salary_period
        listing.salary_currency = row.salary_currency
        listing.description = row.description
        listing.required_skills = row.required_skills
        listing.apply_method = row.apply_method
        listing.apply_target = row.apply_target
        listing.posted_at = row.posted_at
        listing.expires_at = row.expires_at
        listing.ingested_at = now
        listing.last_seen_at = now
        # A listing that arrives already past its source-stated expiry is
        # never activated in the first place, rather than going live until
        # the next expiry sweep runs.
        listing.is_active = row.expires_at is None or row.expires_at > now
        seen += 1
    db.commit()
    return seen


def deactivate_expired_listings(db: Session) -> int:
    """Deactivate listings past the expiry their source stated.

    Layered on top of deactivate_stale_listings, not a replacement for it:
    staleness catches listings that quietly stop appearing in pulls (the only
    signal Adzuna gives), while this catches the ones whose source published
    an end date up front, and catches them on the date itself instead of
    listing_stale_after_days later. Listings with no expires_at are untouched
    here and continue to rely on staleness alone.
    """
    result = db.execute(
        update(Listing)
        .where(Listing.is_active.is_(True), Listing.expires_at.is_not(None), Listing.expires_at <= utcnow())
        .values(is_active=False)
    )
    db.commit()
    deactivated = result.rowcount or 0
    if deactivated:
        emit_event("listings_expired", count=deactivated)
    return deactivated


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
