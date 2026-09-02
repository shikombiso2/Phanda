"""Re-run skill extraction over already-ingested listings.

Every listing tagged before app/listings/ingestion/skills.py grew its word-
boundary + alias vocabulary was tagged with the old, smaller, substring-
matched skill list -- and would stay that way forever without this, since
ingestion only re-tags a listing the next time it's seen in a source pull.
This applies the current vocabulary to existing rows in place.

Dry-run is the default, same convention as backfill_legacy_cv_versions.py.
"""
from __future__ import annotations

import argparse
from collections import Counter

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.models import Listing
from app.listings.ingestion.skills import extract_required_skills


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-tag existing listings with the current skill vocabulary")
    parser.add_argument("--apply", action="store_true", help="Write the updated tags; omitted means dry run")
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()

    summary = Counter()
    with SessionLocal() as db:
        listings = db.scalars(select(Listing).limit(args.limit)).all()
        for listing in listings:
            retagged = extract_required_skills(f"{listing.title} {listing.description}")
            if retagged == (listing.required_skills or []):
                summary["unchanged"] += 1
                continue
            summary["changed"] += 1
            if args.apply:
                listing.required_skills = retagged
        if args.apply:
            db.commit()
    print(" ".join(f"{key}={summary[key]}" for key in sorted(summary)) or "no_listings_found=0")
    if not args.apply:
        print("Dry run: no changes written. Re-run with --apply to persist.")


if __name__ == "__main__":
    main()
