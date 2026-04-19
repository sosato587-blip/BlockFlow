from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.config import Config as BotoConfig
from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse

from backend import config

logger = logging.getLogger(__name__)

router = APIRouter()


def _get_s3_client():
    """Create a boto3 S3 client configured for Cloudflare R2."""
    return boto3.client(
        "s3",
        endpoint_url=config.R2_ENDPOINT,
        aws_access_key_id=config.R2_ACCESS_KEY,
        aws_secret_access_key=config.R2_SECRET_KEY,
        region_name=config.R2_REGION,
        config=BotoConfig(signature_version="s3v4"),
    )


@router.get("/api/r2/list")
def api_r2_list(
    prefix: str = Query(""),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
) -> JSONResponse:
    """List images from R2 bucket with pre-signed URLs."""
    try:
        s3 = _get_s3_client()

        # Build the full prefix
        full_prefix = config.R2_PREFIX
        if prefix:
            full_prefix = full_prefix.rstrip("/") + "/" + prefix.lstrip("/")

        # List all objects under the prefix
        paginator = s3.get_paginator("list_objects_v2")
        all_objects: list[dict[str, Any]] = []

        for page in paginator.paginate(Bucket=config.R2_BUCKET, Prefix=full_prefix):
            for obj in page.get("Contents", []):
                key = obj["Key"]
                # Only include image files
                lower_key = key.lower()
                if not any(lower_key.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp", ".gif", ".mp4", ".webm")):
                    continue
                all_objects.append(obj)

        # Sort by last modified descending (newest first)
        all_objects.sort(key=lambda o: o["LastModified"], reverse=True)

        total = len(all_objects)
        # Apply offset and limit
        page_objects = all_objects[offset : offset + limit]

        # Generate pre-signed URLs (7 day expiry)
        items: list[dict[str, Any]] = []
        for obj in page_objects:
            key = obj["Key"]
            filename = key.rsplit("/", 1)[-1] if "/" in key else key
            url = s3.generate_presigned_url(
                "get_object",
                Params={"Bucket": config.R2_BUCKET, "Key": key},
                ExpiresIn=7 * 24 * 3600,  # 7 days
            )
            items.append(
                {
                    "key": key,
                    "filename": filename,
                    "size": obj["Size"],
                    "last_modified": obj["LastModified"].isoformat(),
                    "url": url,
                }
            )

        return JSONResponse(
            {
                "ok": True,
                "items": items,
                "total": total,
                "limit": limit,
                "offset": offset,
            }
        )

    except Exception as e:
        logger.exception("Failed to list R2 objects")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)


@router.get("/api/r2/image/{key:path}")
def api_r2_image(key: str) -> JSONResponse:
    """Get a pre-signed URL for a specific image."""
    try:
        s3 = _get_s3_client()
        url = s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": config.R2_BUCKET, "Key": key},
            ExpiresIn=7 * 24 * 3600,
        )
        return JSONResponse({"ok": True, "url": url, "key": key})
    except Exception as e:
        logger.exception("Failed to generate presigned URL")
        return JSONResponse({"ok": False, "error": str(e)}, status_code=500)
