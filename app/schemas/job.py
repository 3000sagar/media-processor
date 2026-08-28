from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class MediaType(StrEnum):
    IMAGE = "image"
    VIDEO = "video"


ALLOWED_OPERATIONS = {"resize", "compress", "watermark", "transcode", "thumbnail"}


class JobStatus(StrEnum):
    PENDING = "pending"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    MODERATION_REVIEW = "moderation_review"
    COMPLETED = "completed"
    FAILED = "failed"


class ModerationStatus(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MANUAL_REVIEW = "manual_review"


class JobCreateRequest(BaseModel):
    media_type: MediaType
    declared_filename: str = Field(..., min_length=1, max_length=255)
    operations: list[str] = Field(..., min_length=1, max_length=10)

    @field_validator("operations")
    @classmethod
    def validate_operations(cls, ops: list[str]) -> list[str]:
        invalid = set(ops) - ALLOWED_OPERATIONS
        if invalid:
            raise ValueError(f"Unsupported operations: {sorted(invalid)}")
        return ops

    @field_validator("declared_filename")
    @classmethod
    def strip_path_components(cls, name: str) -> str:
        # Defense in depth: even though this value is NEVER used to build a storage path
        # (see s3_service.derive_object_key), we still normalize it so it can't masquerade
        # as a path in logs/metadata either.
        return name.replace("/", "_").replace("\\", "_").replace("..", "_")


class UploadPostFields(BaseModel):
    url: str
    fields: dict[str, str]


class JobCreateResponse(BaseModel):
    job_id: str
    owner_id: str
    upload_post: UploadPostFields
    status: JobStatus
    expires_at: str


class JobStatusResponse(BaseModel):
    job_id: str
    status: JobStatus
    media_type: MediaType
    result_url: str | None = None
    moderation_status: ModerationStatus | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    processing_duration_seconds: float | None = None
    error: str | None = None


class JobRecord(BaseModel):
    """Internal representation stored in Redis. Not exposed directly via API."""

    job_id: str
    owner_id: str
    media_type: MediaType
    operations: list[str]
    declared_filename: str
    raw_s3_key: str
    status: JobStatus = JobStatus.PENDING
    moderation_status: ModerationStatus = ModerationStatus.PENDING
    result_url: str | None = None
    error: str | None = None
    created_at: str
    started_at: str | None = None
    completed_at: str | None = None
    processing_duration_seconds: float | None = None

    def to_status_response(self) -> JobStatusResponse:
        return JobStatusResponse(
            job_id=self.job_id,
            status=self.status,
            media_type=self.media_type,
            result_url=self.result_url,
            moderation_status=self.moderation_status,
            created_at=self.created_at,
            started_at=self.started_at,
            completed_at=self.completed_at,
            processing_duration_seconds=self.processing_duration_seconds,
            error=self.error,
        )

    def to_redis_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
