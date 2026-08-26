import os
import time
from typing import Any

from app.celery_app import celery_app
from app.config import get_settings
from app.schemas.job import JobStatus
from app.services import redis_service, s3_service
from app.services.redis_service import get_redis_client
from app.tasks._common import (
    TaskAborted,
    download_and_validate,
    job_lock,
    mark_completed,
    mark_failed,
    run_moderation_gate,
    scratch_dir,
)
from app.utils.ffmpeg_runner import FfmpegError, extract_thumbnail, transcode
from app.utils.metrics import task_processing_duration_seconds


@celery_app.task(  # type: ignore[misc]
    # [misc] suppressed: celery's @task decorator has no type stubs, so mypy correctly
    # but unhelpfully infers the wrapped function as untyped — nothing further to annotate.
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(ConnectionError, TimeoutError),
)
def process_video(self: Any, job_id: str) -> None:
    settings = get_settings()
    redis_client = get_redis_client(settings)

    record = redis_service.get_job(redis_client, job_id)
    if record is None:
        return

    try:
        with job_lock(redis_client, job_id, settings.job_lock_ttl_seconds):
            redis_service.update_job(redis_client, job_id, settings.job_status_ttl_seconds, status=JobStatus.PROCESSING)
            start = time.monotonic()

            with scratch_dir() as workdir:
                local_raw_path = download_and_validate(redis_client, settings, job_id, record, workdir)

                output_path = os.path.join(workdir, "output.mp4")
                thumb_path = os.path.join(workdir, "thumb.jpg")
                try:
                    transcode(
                        local_raw_path, output_path,
                        resolution=settings.video_output_resolution,
                        codec=settings.video_output_codec,
                        allowed_protocols=settings.ffmpeg_allowed_protocols,
                        timeout_seconds=settings.ffmpeg_timeout_seconds,
                    )
                except FfmpegError as exc:
                    mark_failed(redis_client, settings, job_id, f"ffmpeg_transcode_failed: {exc}")
                    return

                # Thumbnail is best-effort, not core deliverable: a short clip where the
                # requested seek point exceeds the video's duration should not fail the
                # whole job. Retry once at t=0 (guaranteed to exist for any valid video)
                # before giving up on the thumbnail specifically.
                thumbnail_available = True
                try:
                    extract_thumbnail(
                        local_raw_path, thumb_path,
                        allowed_protocols=settings.ffmpeg_allowed_protocols,
                        timeout_seconds=settings.ffmpeg_timeout_seconds,
                        at_seconds=2.0,
                    )
                except FfmpegError:
                    try:
                        extract_thumbnail(
                            local_raw_path, thumb_path,
                            allowed_protocols=settings.ffmpeg_allowed_protocols,
                            timeout_seconds=settings.ffmpeg_timeout_seconds,
                            at_seconds=0.0,
                        )
                    except FfmpegError:
                        thumbnail_available = False

                if not run_moderation_gate(redis_client, settings, job_id, output_path):
                    return

                processed_key = record.raw_s3_key.replace("raw-uploads/", "processed/", 1)
                thumb_key = processed_key.rsplit(".", 1)[0] + "_thumb.jpg"
                try:
                    s3_service.upload_processed_file(settings, output_path, settings.s3_bucket_processed, processed_key)
                    if thumbnail_available:
                        s3_service.upload_processed_file(settings, thumb_path, settings.s3_bucket_processed, thumb_key)
                except Exception as exc:
                    mark_failed(redis_client, settings, job_id, f"upload_failed: {exc}")
                    return

                result_url = (
                    f"https://{settings.cloudfront_domain}/{processed_key}"
                    if settings.cloudfront_domain else processed_key
                )
                mark_completed(redis_client, settings, job_id, result_url)

            task_processing_duration_seconds.labels(media_type="video").observe(time.monotonic() - start)

    except TaskAborted:
        return
