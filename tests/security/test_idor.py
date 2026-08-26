from datetime import datetime, timezone

import fakeredis
import pytest

from app.schemas.job import JobRecord, JobStatus, MediaType
from app.services import redis_service


@pytest.fixture
def redis_client():
    return fakeredis.FakeRedis(decode_responses=True)


def _make_job(owner_id: str) -> JobRecord:
    return JobRecord(
        job_id="job-xyz",
        owner_id=owner_id,
        media_type=MediaType.IMAGE,
        operations=["resize"],
        declared_filename="photo.jpg",
        raw_s3_key="raw-uploads/owner_1/job-xyz.jpg",
        status=JobStatus.PENDING,
        created_at=datetime.now(timezone.utc).isoformat(),
    )


def test_job_record_roundtrip_preserves_owner(redis_client):
    job = _make_job("owner_1")
    redis_service.save_job(redis_client, job, ttl_seconds=60)
    fetched = redis_service.get_job(redis_client, job.job_id)
    assert fetched.owner_id == "owner_1"


def test_ownership_mismatch_is_detectable(redis_client):
    job = _make_job("owner_1")
    redis_service.save_job(redis_client, job, ttl_seconds=60)
    fetched = redis_service.get_job(redis_client, job.job_id)
    requesting_owner = "owner_2"
    assert fetched.owner_id != requesting_owner  # this is the condition app/api/v1/jobs.py
    # checks before raising forbidden() — verified at the API layer in test_jobs_api.py
