"""Centralized S3 operations for file upload, presigned URLs, and URL resolution."""

import os
from pathlib import Path

S3_BUCKET = os.environ.get("S3_BUCKET", "")
S3_PREFIX = os.environ.get("S3_PREFIX", "generated/")
S3_REGION = os.environ.get("S3_REGION", "us-west-2")

_s3_client = None


def _get_client():
    global _s3_client
    if _s3_client is None:
        import boto3
        _s3_client = boto3.client("s3", region_name=S3_REGION)
    return _s3_client


def upload_file(local_path: Path) -> str | None:
    """Upload file to S3. Returns the S3 key, or None if S3 is not configured."""
    if not S3_BUCKET:
        return None
    key = f"{S3_PREFIX}{local_path.name}"
    content_types = {
        ".mp4": "video/mp4",
        ".jpg": "image/jpeg",
        ".json": "application/json",
        ".xosc": "application/xml",
    }
    content_type = content_types.get(local_path.suffix, "application/octet-stream")
    try:
        _get_client().upload_file(
            str(local_path), S3_BUCKET, key,
            ExtraArgs={"ContentType": content_type},
        )
        return key
    except Exception as e:
        print(f"[S3] Upload failed for {local_path.name}: {e}")
        return None


def get_presigned_url(key: str, expires_in: int = 3600) -> str:
    """Generate a presigned URL for an S3 key. Default 1-hour expiry."""
    return _get_client().generate_presigned_url(
        "get_object",
        Params={"Bucket": S3_BUCKET, "Key": key},
        ExpiresIn=expires_in,
    )


def resolve_url(stored_value: str | None) -> str | None:
    """Resolve a stored URL/key to an accessible URL.

    - S3 key (no '/' prefix, no '://') → presigned URL
    - Full URL (http/https) → pass through
    - /api/file/... path → pass through
    - None → None
    """
    if not stored_value:
        return None
    if stored_value.startswith("http://") or stored_value.startswith("https://"):
        return stored_value
    if stored_value.startswith("/api/file/"):
        return stored_value
    # Treat as S3 key
    if S3_BUCKET:
        try:
            return get_presigned_url(stored_value)
        except Exception:
            return stored_value
    return stored_value


def file_url(filename: str, local_path: Path | None = None) -> str:
    """Upload file to S3 and return presigned URL, or fall back to local /api/file/ path."""
    if local_path is not None and S3_BUCKET:
        key = upload_file(local_path)
        if key:
            try:
                return get_presigned_url(key)
            except Exception:
                pass
    base = os.environ.get("API_BASE_URL", "").rstrip("/")
    return f"{base}/api/file/{filename}"
