from datetime import datetime, timezone
from unittest.mock import patch

import fakeredis

from app.config import get_settings
from app.schemas.job import JobRecord, JobStatus, MediaType, ModerationStatus
from app.services import moderation_service, redis_service
from app.tasks._common import run_moderation_gate


def _seed_job(redis_client) -> str:
    job = JobRecord(
        job_id="mod-job-1",
        owner_id="owner_1",
        media_type=MediaType.IMAGE,
        operations=["resize"],
        declared_filename="photo.jpg",
        raw_s3_key="raw-uploads/owner_1/mod-job-1.jpg",
        status=JobStatus.PROCESSING,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    redis_service.save_job(redis_client, job, ttl_seconds=60)
    return job.job_id


def test_approved_content_may_proceed_to_publish():
    get_settings.cache_clear()
    client = fakeredis.FakeRedis(decode_responses=True)
    job_id = _seed_job(client)
    settings = get_settings()

    with patch.object(moderation_service, "scan_file", return_value=moderation_service.ModerationResult.APPROVED):
        may_publish = run_moderation_gate(client, settings, job_id, "/tmp/fake_output.jpg")

    assert may_publish is True
    record = redis_service.get_job(client, job_id)
    assert record.moderation_status == ModerationStatus.APPROVED


def test_rejected_content_is_blocked_and_marked_failed():
    get_settings.cache_clear()
    client = fakeredis.FakeRedis(decode_responses=True)
    job_id = _seed_job(client)
    settings = get_settings()

    with patch.object(moderation_service, "scan_file", return_value=moderation_service.ModerationResult.REJECTED):
        may_publish = run_moderation_gate(client, settings, job_id, "/tmp/fake_output.jpg")

    assert may_publish is False  # this is what stops the calling task from uploading to the processed bucket
    record = redis_service.get_job(client, job_id)
    assert record.moderation_status == ModerationStatus.REJECTED
    assert record.status == JobStatus.FAILED
    assert record.result_url is None  # never populated — no CDN URL is ever issued for rejected content


def test_manual_review_content_is_held_not_published():
    get_settings.cache_clear()
    client = fakeredis.FakeRedis(decode_responses=True)
    job_id = _seed_job(client)
    settings = get_settings()

    with patch.object(moderation_service, "scan_file", return_value=moderation_service.ModerationResult.MANUAL_REVIEW):
        may_publish = run_moderation_gate(client, settings, job_id, "/tmp/fake_output.jpg")

    assert may_publish is False
    record = redis_service.get_job(client, job_id)
    assert record.moderation_status == ModerationStatus.MANUAL_REVIEW
    assert record.status == JobStatus.MODERATION_REVIEW
    assert record.result_url is None  # held content must not be CDN-servable until a human approves it
