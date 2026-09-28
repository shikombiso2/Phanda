"""Re-fetch and re-parse stored vacancyupdate listings so existing rows get
the cleaned, structured description, not just future ingestions.

Why this re-fetches rather than rewriting the stored text in place: the
original page HTML is never persisted, only the parsed result. The old
parser had already flattened every section heading and <li> into one
unbroken run of text and mixed ad/widget script junk into it, so the
structure simply is not recoverable from what is stored -- the only source
of truth for "About X / Eligibility Criteria / Application Instructions" and
the bulleted criteria is the page itself.

Dry-run is the default, same convention as the other backfill/retag scripts.
"""
from __future__ import annotations

import argparse
import asyncio
from collections import Counter

import httpx
from sqlalchemy import select

from app.core.db import SessionLocal
from app.core.models import Listing
from app.listings.ingestion.vacancyupdate_adapter import (
    _PAUSE_BETWEEN_POSTS_SECONDS,
    _REQUEST_HEADERS,
    BASE_URL,
    parse_post,
)

_JUNK_MARKERS = ("adsbygoogle", "getElementById", "copyText", "URL Copied", "Copy URL")


async def _fetch(client: httpx.AsyncClient, url: str) -> str | None:
    try:
        response = await client.get(url, headers=_REQUEST_HEADERS)
    except httpx.HTTPError:
        return None
    if response.status_code != 200:
        return None
    return response.text


async def run(apply: bool, limit: int) -> None:
    summary = Counter()
    with SessionLocal() as db:
        listings = db.scalars(
            select(Listing).where(Listing.source == "vacancyupdate").order_by(Listing.source_listing_id).limit(limit)
        ).all()
        print(f"stored vacancyupdate listings: {len(listings)}")

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            for listing in listings:
                url = f"{BASE_URL}/{listing.source_listing_id}/"
                html = await _fetch(client, url)
                await asyncio.sleep(_PAUSE_BETWEEN_POSTS_SECONDS)
                if html is None:
                    summary["unreachable"] += 1
                    continue
                try:
                    parsed = parse_post(url, html)
                except ValueError:
                    # No apply target -- the same condition ingestion skips on.
                    summary["unparseable"] += 1
                    continue

                had_junk = any(marker in (listing.description or "") for marker in _JUNK_MARKERS)
                gained_structure = "## " in parsed.description and "## " not in (listing.description or "")
                if parsed.description == listing.description:
                    summary["already_clean"] += 1
                    continue

                summary["rewritten"] += 1
                summary["junk_removed"] += int(had_junk)
                summary["structure_added"] += int(gained_structure)
                if apply:
                    listing.description = parsed.description
                    listing.required_skills = parsed.required_skills

        if apply:
            db.commit()

    print(" ".join(f"{key}={summary[key]}" for key in sorted(summary)) or "nothing_to_do=0")
    if not apply:
        print("Dry run: no changes written. Re-run with --apply to persist.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Re-fetch and restructure stored vacancyupdate descriptions")
    parser.add_argument("--apply", action="store_true", help="Write the rebuilt descriptions; omitted means dry run")
    parser.add_argument("--limit", type=int, default=500)
    args = parser.parse_args()
    asyncio.run(run(apply=args.apply, limit=args.limit))


if __name__ == "__main__":
    main()
