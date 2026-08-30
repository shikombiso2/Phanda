import uuid

import boto3
from fastapi import HTTPException, UploadFile, status

from app.core.config import get_settings


def upload_bytes(data: bytes, key_prefix: str, content_type: str = "application/octet-stream") -> str:
    settings = get_settings()
    if not settings.s3_bucket:
        return f"local://{key_prefix}/{uuid.uuid4()}"

    client = boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key_id,
        aws_secret_access_key=settings.s3_secret_access_key,
        region_name=settings.s3_region,
    )
    key = f"{key_prefix.rstrip('/')}/{uuid.uuid4()}"
    client.put_object(Bucket=settings.s3_bucket, Key=key, Body=data, ContentType=content_type)
    return f"s3://{settings.s3_bucket}/{key}"


async def upload_file(file: UploadFile, key_prefix: str) -> str:
    data = await file.read()
    if not data:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty file")
    return upload_bytes(data, key_prefix, file.content_type or "application/octet-stream")

