"""Safely prepare CV versions from legacy ``profiles.cv_file_url`` values.

Dry-run is the default. ``--apply`` creates only UPLOADED versions and queues
extraction; it never changes ``active_cv_version_id``. The extraction worker is
the sole component that activates a version after successful parsing.
"""
from __future__ import annotations

import argparse
import hashlib
import uuid
from collections import Counter
from pathlib import PurePosixPath
from urllib.parse import urlparse

from sqlalchemy import func, select

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.core.models import CvVersion, Profile
from app.core.storage import get_bytes
from app.cv_tailoring.extraction import CvExtractionError, validate_upload


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill verified legacy CV objects into immutable CV versions")
    parser.add_argument("--apply", action="store_true", help="Create versions and enqueue extraction; omitted means dry run")
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    summary = Counter()
    queued: list[str] = []
    with SessionLocal() as db:
        profiles = db.scalars(
            select(Profile).where(Profile.cv_file_url.is_not(None), Profile.active_cv_version_id.is_(None)).limit(args.limit)
        ).all()
        for profile in profiles:
            outcome, version_id = _process_profile(db, profile, apply=args.apply)
            summary[outcome] += 1
            if version_id:
                queued.append(str(version_id))
        if args.apply:
            db.commit()
    if args.apply:
        from app.cv_tailoring.tasks import extract_cv_version
        for version_id in queued:
            extract_cv_version.delay(version_id)
    print(" ".join(f"{key}={summary[key]}" for key in sorted(summary)) or "no_eligible_profiles=0")


def _process_profile(db, profile: Profile, *, apply: bool) -> tuple[str, uuid.UUID | None]:
    legacy_url = profile.cv_file_url or ""
    key = _verified_s3_key(legacy_url)
    if not key:
        return ("skipped_unusable_legacy_reference", None)
    try:
        data = get_bytes(key)
        info = validate_upload(PurePosixPath(key).name, None, data)
    except (CvExtractionError, FileNotFoundError, ValueError):
        return ("skipped_unavailable_or_invalid_object", None)
    digest = hashlib.sha256(data).hexdigest()
    existing = db.scalar(select(CvVersion).where(CvVersion.user_id == profile.user_id, CvVersion.sha256 == digest))
    if existing:
        return ("skipped_existing_version", None)
    if not apply:
        return ("would_queue_extraction", None)
    version_number = (db.scalar(select(func.max(CvVersion.version_number)).where(CvVersion.user_id == profile.user_id)) or 0) + 1
    version = CvVersion(
        id=uuid.uuid4(), user_id=profile.user_id, version_number=version_number,
        storage_key=key, filename=info.filename, content_type=info.content_type,
        byte_size=len(data), sha256=digest,
    )
    db.add(version)
    db.flush()
    return ("queued_extraction", version.id)


def _verified_s3_key(value: str) -> str | None:
    """Accept only a current-bucket S3 URI; placeholders and public URLs are skipped."""
    if value.startswith("local://") or value.startswith(("http://", "https://")):
        return None
    parsed = urlparse(value)
    settings = get_settings()
    if parsed.scheme != "s3" or not settings.s3_bucket or parsed.netloc != settings.s3_bucket:
        return None
    key = parsed.path.lstrip("/")
    if not key or ".." in PurePosixPath(key).parts:
        return None
    return key


if __name__ == "__main__":
    main()
