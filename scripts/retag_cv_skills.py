"""Re-run skill extraction over already-ready CV versions.

Companion to retag_listing_skills.py, same problem: `CvVersion.extracted_skills`
was computed once at extraction time using whatever skills.py vocabulary
existed then, and nothing else ever recomputes it. This reads back each ready
version's already-extracted text (extracted_text_key) and re-runs
extract_required_skills over it -- it does not re-run OCR/parsing, since the
CV document itself hasn't changed, only the skill vocabulary has.

Dry-run is the default, same convention as the other backfill/retag scripts.
"""
from __future__ import annotations

import argparse
from collections import Counter

from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.models import CvVersion, CvVersionStatus
from app.core.storage import get_bytes
from app.listings.ingestion.skills import extract_required_skills


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-tag ready CV versions with the current skill vocabulary")
    parser.add_argument("--apply", action="store_true", help="Write the updated tags; omitted means dry run")
    parser.add_argument("--limit", type=int, default=5000)
    args = parser.parse_args()

    summary = Counter()
    with SessionLocal() as db:
        versions = db.scalars(
            select(CvVersion).where(CvVersion.status == CvVersionStatus.ready).limit(args.limit)
        ).all()
        for version in versions:
            if not version.extracted_text_key:
                summary["skipped_no_extracted_text"] += 1
                continue
            try:
                text = get_bytes(version.extracted_text_key).decode("utf-8")
            except FileNotFoundError:
                summary["skipped_missing_object"] += 1
                continue
            retagged = extract_required_skills(text)
            if retagged == (version.extracted_skills or []):
                summary["unchanged"] += 1
                continue
            summary["changed"] += 1
            if args.apply:
                version.extracted_skills = retagged
        if args.apply:
            db.commit()
    print(" ".join(f"{key}={summary[key]}" for key in sorted(summary)) or "no_ready_versions_found=0")
    if not args.apply:
        print("Dry run: no changes written. Re-run with --apply to persist.")


if __name__ == "__main__":
    main()
