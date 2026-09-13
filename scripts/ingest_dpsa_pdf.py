"""Manual, one-off ingestion of DPSA Public Service Vacancy Circular PDFs.

Deliberately NOT automated -- there is no scraper and no scheduled task for
this source (unlike Adzuna/Himalayas/Vacancy Update). The user downloads
each circular PDF from dpsa.gov.za themselves and runs this script against
it directly.

Accepts one or more PDF paths in a single run, for batch ingestion of
several circulars at once. Dry-run is the default, same convention as
retag_listing_skills.py and backfill_legacy_cv_versions.py -- --apply
writes. Safe to re-run: upsert_listings() is keyed on (source,
source_listing_id), and a DPSA post number ("33/01") is globally unique
forever since circular numbers never repeat.

Usage:
    python -m scripts.ingest_dpsa_pdf "PSV CIRCULAR 33 of 2026.pdf" [more.pdf ...] [--apply]
"""
from __future__ import annotations

import argparse
from collections import Counter

from app.core.db import SessionLocal
from app.listings.ingestion.dpsa_adapter import DpsaParsingError, parse_circular
from app.listings.ingestion.repository import upsert_listings


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest one or more DPSA circular PDFs")
    parser.add_argument("pdf_paths", nargs="+", help="Path(s) to circular PDF file(s)")
    parser.add_argument("--apply", action="store_true", help="Write the parsed listings; omitted means dry run")
    args = parser.parse_args()

    per_circular: Counter[str] = Counter()
    all_rows = []
    for pdf_path in args.pdf_paths:
        try:
            rows = parse_circular(pdf_path)
        except DpsaParsingError as exc:
            print(f"SKIPPED {pdf_path}: {exc}")
            continue
        per_circular[pdf_path] = len(rows)
        all_rows.extend(rows)
        print(f"Parsed {len(rows)} posts from {pdf_path}")

    print(f"\nTotal posts parsed across {len(per_circular)} circular(s): {len(all_rows)}")

    if not args.apply:
        print("Dry run -- no rows written. Re-run with --apply to upsert into the listings table.")
        return

    with SessionLocal() as db:
        upserted = upsert_listings(db, all_rows)
    print(f"Upserted {upserted} listings.")


if __name__ == "__main__":
    main()
