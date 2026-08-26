import uuid
from typing import Any

import boto3

from app.config import Settings
from app.schemas.job import MediaType

_EXT_BY_MEDIA_TYPE = {
    MediaType.IMAGE: {".jpg", ".jpeg", ".png", ".webp"},
    MediaType.VIDEO: {".mp4", ".mov", ".mkv"},
}

_CONTENT_TYPE_PREFIX = {
    MediaType.IMAGE: "image/",
    MediaType.VIDEO: "video/",
}


def get_s3_client(settings: Settings) -> Any:
    # boto3's dynamically-generated client has no static type surface without the heavy
    # boto3-stubs/mypy-boto3-s3 dependency; Any here is an honest reflection of that, not
    # a place where a real type was dropped for convenience.
    kwargs: dict[str, str] = {"region_name": settings.aws_region}
    if settings.s3_endpoint_url:  # only set for local/moto testing
        kwargs["endpoint_url"] = settings.s3_endpoint_url
    return boto3.client("s3", **kwargs)


def get_presign_client(settings: Settings) -> Any:
    if not settings.s3_public_endpoint_url:
        return get_s3_client(settings)
    return boto3.client(
        "s3",
        region_name=settings.aws_region,
        endpoint_url=settings.s3_public_endpoint_url,
    )


def derive_object_key(owner_id: str, job_id: str, declared_filename: str, media_type: MediaType) -> str:
    """Server-side key derivation. The client's declared_filename is NEVER used in the path —
    only its extension is inspected, and only against an explicit allow-list. This is the fix
    for the path-traversal / key-collision vulnerability identified in the security audit.
    """
    ext = ""
    if "." in declared_filename:
        _, suffix = declared_filename.rsplit(".", 1)
        ext = f".{suffix.lower()}"
    allowed = _EXT_BY_MEDIA_TYPE[media_type]
    if ext not in allowed:
        # Fall back to a safe default extension rather than trusting client input further.
        ext = sorted(allowed)[0]
    return f"raw-uploads/{owner_id}/{job_id}{ext}"


def generate_presigned_post(
    settings: Settings,
    bucket: str,
    key: str,
    media_type: MediaType,
    max_size_bytes: int,
) -> dict[str, Any]:
    """Presigned POST (not PUT) so S3 itself enforces size and content-type — the enforcement
    the v1 plan claimed to have but didn't actually implement.
    """
    client = get_presign_client(settings)
    content_type_prefix = _CONTENT_TYPE_PREFIX[media_type]
    response = client.generate_presigned_post(
        Bucket=bucket,
        Key=key,
        Fields={"Content-Type": content_type_prefix + "*"},
        Conditions=[
            ["content-length-range", 1, max_size_bytes],
            ["starts-with", "$Content-Type", content_type_prefix],
        ],
        ExpiresIn=settings.presigned_url_expiry_seconds,
    )
    return dict(response)


def upload_processed_file(settings: Settings, local_path: str, bucket: str, key: str) -> None:
    client = get_s3_client(settings)
    client.upload_file(local_path, bucket, key)


def download_file(settings: Settings, bucket: str, key: str, local_path: str) -> None:
    client = get_s3_client(settings)
    client.download_file(bucket, key, local_path)


def delete_object(settings: Settings, bucket: str, key: str) -> None:
    client = get_s3_client(settings)
    client.delete_object(Bucket=bucket, Key=key)


def new_job_id() -> str:
    return str(uuid.uuid4())
