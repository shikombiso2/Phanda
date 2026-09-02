"""Private object storage helpers.

Callers persist opaque storage keys only. They never return S3 URIs or
credentials to clients; routers authorize before asking for a signed URL.
"""

from __future__ import annotations

from pathlib import Path, PurePosixPath

import boto3
from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings


def put_bytes(data: bytes, key: str, content_type: str = "application/octet-stream") -> str:
    """Store bytes privately and return the opaque, validated key."""
    normalized = _validate_key(key)
    settings = get_settings()
    if settings.s3_bucket:
        _client().put_object(Bucket=settings.s3_bucket, Key=normalized, Body=data, ContentType=content_type)
    else:
        path = _local_path(normalized)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    return normalized


def get_bytes(key: str) -> bytes:
    normalized = _validate_key(key)
    settings = get_settings()
    if settings.s3_bucket:
        return _client().get_object(Bucket=settings.s3_bucket, Key=normalized)["Body"].read()
    path = _local_path(normalized)
    if not path.is_file():
        raise FileNotFoundError(normalized)
    return path.read_bytes()


def delete_key(key: str) -> None:
    normalized = _validate_key(key)
    settings = get_settings()
    if settings.s3_bucket:
        _client().delete_object(Bucket=settings.s3_bucket, Key=normalized)
        return
    _local_path(normalized).unlink(missing_ok=True)


def create_download_url(key: str, filename: str, expires_in: int = 300) -> str | None:
    """Return a short-lived HTTPS URL for S3, or None for local development storage."""
    normalized = _validate_key(key)
    settings = get_settings()
    if not settings.s3_bucket:
        return None
    return _client().generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": normalized,
            "ResponseContentDisposition": f'attachment; filename="{_safe_filename(filename)}"',
        },
        ExpiresIn=expires_in,
    )


async def read_upload(file: UploadFile, max_bytes: int) -> bytes:
    data = await file.read(max_bytes + 1)
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    if len(data) > max_bytes:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="CV exceeds the 5 MB limit")
    return data


def _client():
    settings = get_settings()
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )


def _validate_key(key: str) -> str:
    path = PurePosixPath(key)
    if not key or path.is_absolute() or ".." in path.parts:
        raise ValueError("Invalid storage key")
    return path.as_posix()


def _local_path(key: str) -> Path:
    root = Path(get_settings().local_storage_path).resolve()
    path = (root / key).resolve()
    if root != path and root not in path.parents:
        raise ValueError("Invalid storage key")
    return path


def _safe_filename(value: str) -> str:
    return "".join(character if character.isalnum() or character in {".", "-", "_", " "} else "_" for character in value)
