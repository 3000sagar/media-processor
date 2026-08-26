import os
import time
from typing import Any

from PIL import Image, UnidentifiedImageError

from app.celery_app import celery_app
from app.config import Settings, get_settings
from app.schemas.job import JobStatus
from app.services import redis_service, s3_service
from app.services.file_validation import apply_pillow_safety_limit
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
from app.utils.metrics import task_processing_duration_seconds


@celery_app.task(  # type: ignore[misc]
    # [misc] suppressed: celery's @task decorator has no type stubs, so mypy correctly
    # but unhelpfully infers the wrapped function as untyped — nothing further to annotate.
    bind=True,
    max_retries=3,
    default_retry_delay=30,
    autoretry_for=(ConnectionError, TimeoutError),
)
def process_image(self: Any, job_id: str) -> None:
    settings = get_settings()
    redis_client = get_redis_client(settings)
    apply_pillow_safety_limit(settings.pillow_max_image_pixels)

    record = redis_service.get_job(redis_client, job_id)
    if record is None:
        return  # job expired/vanished — nothing to do, not an error worth retrying

    try:
        with job_lock(redis_client, job_id, settings.job_lock_ttl_seconds):
            redis_service.update_job(redis_client, job_id, settings.job_status_ttl_seconds, status=JobStatus.PROCESSING)
            start = time.monotonic()

            with scratch_dir() as workdir:
                local_raw_path = download_and_validate(redis_client, settings, job_id, record, workdir)

                try:
                    output_path = _process_image_file(local_raw_path, workdir, settings)
                except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
                    mark_failed(redis_client, settings, job_id, f"image_processing_failed: {exc}")
                    return

                if not run_moderation_gate(redis_client, settings, job_id, output_path):
                    return  # status already set by run_moderation_gate (rejected or manual_review)

                processed_key = record.raw_s3_key.replace("raw-uploads/", "processed/", 1)
                try:
                    s3_service.upload_processed_file(settings, output_path, settings.s3_bucket_processed, processed_key)
                except Exception as exc:
                    mark_failed(redis_client, settings, job_id, f"upload_failed: {exc}")
                    return

                result_url = (
                    f"https://{settings.cloudfront_domain}/{processed_key}"
                    if settings.cloudfront_domain else processed_key
                )
                mark_completed(redis_client, settings, job_id, result_url)

            task_processing_duration_seconds.labels(media_type="image").observe(time.monotonic() - start)

    except TaskAborted:
        return


def _process_image_file(input_path: str, workdir: str, settings: "Settings") -> str:
    opened = Image.open(input_path)
    image: Image.Image = opened.convert("RGB") if opened.mode in ("RGBA", "P") else opened

    if image.width > settings.image_max_width:
        ratio = settings.image_max_width / image.width
        new_size = (settings.image_max_width, int(image.height * ratio))
        image = image.resize(new_size, Image.Resampling.LANCZOS)

    output_path = os.path.join(workdir, "output.jpg")
    image.save(output_path, "JPEG", quality=settings.image_compression_quality, optimize=True)
    return output_path
