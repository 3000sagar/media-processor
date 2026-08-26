from __future__ import annotations

import os
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from redis import Redis

from app.config import Settings
from app.logging_config import get_logger
from app.schemas.job import JobRecord, JobStatus, ModerationStatus
from app.services import idempotency, moderation_service, redis_service, s3_service
from app.services.file_validation import verify_file_type
from app.utils.metrics import (
    jobs_completed_total,
    jobs_failed_total,
    moderation_manual_review_total,
    redis_lock_contention_total,
)

logger = get_logger(__name__)


class TaskAborted(Exception):
    """Raised to stop processing early (lock contention, validation failure, moderation reject)
    without treating it as a Celery retry-worthy error.
    """


@contextmanager
def job_lock(redis_client: Redis[str], job_id: str, ttl_seconds: int) -> Iterator[None]:
    acquired = idempotency.acquire_lock(redis_client, idempotency.job_processing_lock_key(job_id), ttl_seconds)
    if not acquired:
        redis_lock_contention_total.inc()
        logger.info("job_lock_contention_skipping", job_id=job_id)
        raise TaskAborted("lock already held")
    try:
        yield
    finally:
        idempotency.release_lock(redis_client, idempotency.job_processing_lock_key(job_id))


def mark_failed(redis_client: Redis[str], settings: Settings, job_id: str, reason: str) -> None:
    redis_service.update_job(
        redis_client, job_id, settings.job_status_ttl_seconds,
        status=JobStatus.FAILED, error=reason, completed_at=datetime.now(UTC).isoformat(),
    )
    jobs_failed_total.labels(reason=reason[:64]).inc()
    logger.warning("job_failed", job_id=job_id, reason=reason)


def download_and_validate(
    redis_client: Redis[str], settings: Settings, job_id: str, record: JobRecord, workdir: str
) -> str:
    """Downloads the raw file and verifies its real content matches the declared media_type.
    Returns the local path on success; raises TaskAborted (with status already updated) on failure.
    """
    local_raw_path = os.path.join(workdir, f"raw_{job_id}")
    try:
        s3_service.download_file(settings, settings.s3_bucket_raw, record.raw_s3_key, local_raw_path)
    except Exception as exc:
        mark_failed(redis_client, settings, job_id, f"download_failed: {exc}")
        raise TaskAborted("download failed") from exc

    valid, detected_mime = verify_file_type(local_raw_path, record.media_type)
    if not valid:
        reason = f"file type mismatch: declared={record.media_type}, detected={detected_mime}"
        mark_failed(redis_client, settings, job_id, reason)
        raise TaskAborted("file type mismatch")

    return local_raw_path


def run_moderation_gate(redis_client: Redis[str], settings: Settings, job_id: str, processed_path: str) -> bool:
    """Returns True if the file may proceed to publish. Updates job state for reject/review cases."""
    result = moderation_service.scan_file(settings, processed_path)

    if result == moderation_service.ModerationResult.APPROVED:
        redis_service.update_job(
            redis_client, job_id, settings.job_status_ttl_seconds,
            moderation_status=ModerationStatus.APPROVED,
        )
        return True

    if result == moderation_service.ModerationResult.MANUAL_REVIEW:
        redis_service.update_job(
            redis_client, job_id, settings.job_status_ttl_seconds,
            status=JobStatus.MODERATION_REVIEW, moderation_status=ModerationStatus.MANUAL_REVIEW,
        )
        moderation_manual_review_total.inc()
        return False

    # REJECTED
    mark_failed(redis_client, settings, job_id, "rejected by content moderation")
    redis_service.update_job(
        redis_client, job_id, settings.job_status_ttl_seconds,
        moderation_status=ModerationStatus.REJECTED,
    )
    return False


def mark_completed(redis_client: Redis[str], settings: Settings, job_id: str, result_url: str) -> None:
    redis_service.update_job(
        redis_client, job_id, settings.job_status_ttl_seconds,
        status=JobStatus.COMPLETED, result_url=result_url,
        completed_at=datetime.now(UTC).isoformat(),
    )
    jobs_completed_total.inc()
    logger.info("job_completed", job_id=job_id, result_url=result_url)


@contextmanager
def scratch_dir() -> Iterator[str]:
    with tempfile.TemporaryDirectory(prefix="media-proc-") as d:
        yield d
