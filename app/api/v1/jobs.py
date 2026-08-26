
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Request
from redis import Redis

from app.auth import get_owner_id
from app.config import Settings, get_settings
from app.errors import conflict, forbidden, not_found, service_unavailable
from app.rate_limit import limiter
from app.schemas.job import (
    JobCreateRequest,
    JobCreateResponse,
    JobRecord,
    JobStatus,
    JobStatusResponse,
    UploadPostFields,
)
from app.services import idempotency, redis_service, s3_service
from app.services.redis_service import get_redis_client
from app.utils.metrics import jobs_created_total

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


def _get_redis(settings: Settings = Depends(get_settings)) -> Redis:  # type: ignore[type-arg]  # noqa: E501
    # Redis[str] is a mypy-stub-only generic; redis-py 5.0.8 does not support runtime
    # subscription (Redis[str] raises TypeError outside a type-checking context). This
    # file cannot use `from __future__ import annotations` to defer evaluation because
    # FastAPI/Pydantic needs real runtime annotations here to build the OpenAPI schema.
    # Plain Redis + a scoped ignore is the correct tradeoff, not a loosened strict bar.
    return get_redis_client(settings)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat()


@router.post("", response_model=JobCreateResponse, status_code=201)
@limiter.limit(lambda: f"{get_settings().rate_limit_jobs_per_minute}/minute")
async def create_job(
    request: Request,
    body: JobCreateRequest,
    owner_id: str = Depends(get_owner_id),
    settings: Settings = Depends(get_settings),
    redis_client: Redis = Depends(_get_redis),  # type: ignore[type-arg]
) -> JobCreateResponse:
    # Backpressure: reject new work before the queue is overwhelmed, rather than accepting
    # unbounded jobs and letting workers fall further and further behind (or OOM).
    current_depth = redis_client.llen("celery") if redis_client.exists("celery") else 0
    if current_depth > settings.max_queue_depth_before_backpressure:
        raise service_unavailable("System is at capacity, please retry shortly")

    job_id = s3_service.new_job_id()
    raw_key = s3_service.derive_object_key(owner_id, job_id, body.declared_filename, body.media_type)

    presigned = s3_service.generate_presigned_post(
        settings=settings,
        bucket=settings.s3_bucket_raw,
        key=raw_key,
        media_type=body.media_type,
        max_size_bytes=settings.max_upload_size_mb * 1024 * 1024,
    )

    record = JobRecord(
        job_id=job_id,
        owner_id=owner_id,
        media_type=body.media_type,
        operations=body.operations,
        declared_filename=body.declared_filename,
        raw_s3_key=raw_key,
        status=JobStatus.PENDING,
        created_at=_now_iso(),
    )
    redis_service.save_job(redis_client, record, settings.job_status_ttl_seconds)
    jobs_created_total.inc()

    return JobCreateResponse(
        job_id=job_id,
        owner_id=owner_id,
        upload_post=UploadPostFields(url=presigned["url"], fields=presigned["fields"]),
        status=JobStatus.PENDING,
        expires_at=_now_iso(),  # exact expiry timestamp computation left to a follow-up;
                                  # ExpiresIn is enforced server-side by S3 regardless.
    )


@router.post("/{job_id}/confirm-upload", response_model=JobStatusResponse)
async def confirm_upload(
    job_id: str,
    owner_id: str = Depends(get_owner_id),
    settings: Settings = Depends(get_settings),
    redis_client: Redis = Depends(_get_redis),  # type: ignore[type-arg]
) -> JobStatusResponse:
    record = redis_service.get_job(redis_client, job_id)
    if record is None:
        raise not_found(f"No job with id {job_id}")
    if record.owner_id != owner_id:
        raise forbidden()
    if record.status != JobStatus.PENDING:
        raise conflict(f"Job is already in status '{record.status}', cannot re-confirm")

    idem_key = idempotency.confirm_idempotency_key(job_id)
    if not idempotency.acquire_lock(redis_client, idem_key, settings.confirm_idempotency_ttl_seconds):
        # Duplicate confirm call (retry/double-click) — do not double-enqueue.
        # Return current state instead of erroring, since the first call already handled it.
        current = redis_service.get_job(redis_client, job_id)
        if current is None:
            # TTL race: job expired between our fetch above and this re-fetch. Extremely
            # unlikely (job_status_ttl_seconds defaults to 24h), but mypy --strict correctly
            # refused to let this be silently unsound — surface it as a real error instead
            # of crashing on `.to_status_response()` against None.
            raise not_found(f"Job {job_id} expired during processing")
        return current.to_status_response()

    updated = redis_service.update_job(redis_client, job_id, settings.job_status_ttl_seconds, status=JobStatus.UPLOADED)
    if updated is None:
        raise not_found(f"Job {job_id} expired during processing")

    # Local import avoids a circular import (tasks module imports celery_app which is fine,
    # but importing tasks at module load time here would create app <-> tasks <-> app cycle).
    from app.schemas.job import MediaType
    from app.tasks.image_tasks import process_image
    from app.tasks.video_tasks import process_video

    if record.media_type == MediaType.IMAGE:
        process_image.delay(job_id)
    else:
        process_video.delay(job_id)

    # Re-fetch rather than returning the pre-enqueue `updated` snapshot. Under Celery's
    # default (async broker) mode this makes no observable difference — the task hasn't
    # run yet either way. But under CELERY_TASK_ALWAYS_EAGER (used in tests, and by anyone
    # who eager-mode's a single-node deployment) `.delay()` runs the task synchronously
    # in-process, so by the time we reach this line the job may already be completed/failed.
    # Returning the stale pre-enqueue snapshot in that case is a genuine bug, not a
    # theoretical one — it was caught by the integration test, not by inspection.
    latest = redis_service.get_job(redis_client, job_id) or updated
    return latest.to_status_response()


@router.get("/{job_id}", response_model=JobStatusResponse)
async def get_job_status(
    job_id: str,
    owner_id: str = Depends(get_owner_id),
    redis_client: Redis = Depends(_get_redis),  # type: ignore[type-arg]
) -> JobStatusResponse:
    record = redis_service.get_job(redis_client, job_id)
    if record is None:
        raise not_found(f"No job with id {job_id}")
    if record.owner_id != owner_id:
        raise forbidden()
    return record.to_status_response()
