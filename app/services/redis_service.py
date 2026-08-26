from __future__ import annotations

import json
from typing import Any

import redis

from app.config import Settings
from app.schemas.job import JobRecord


def get_redis_client(settings: Settings) -> redis.Redis[str]:
    return redis.Redis.from_url(settings.redis_url, decode_responses=True)


def save_job(client: redis.Redis[str], job: JobRecord, ttl_seconds: int) -> None:
    client.set(f"job:{job.job_id}", json.dumps(job.to_redis_dict()), ex=ttl_seconds)


def get_job(client: redis.Redis[str], job_id: str) -> JobRecord | None:
    raw = client.get(f"job:{job_id}")
    if raw is None:
        return None
    return JobRecord.model_validate_json(raw)


def update_job(client: redis.Redis[str], job_id: str, ttl_seconds: int, **fields: Any) -> JobRecord | None:
    job = get_job(client, job_id)
    if job is None:
        return None
    updated = job.model_copy(update=fields)
    save_job(client, updated, ttl_seconds)
    return updated
