from __future__ import annotations

import redis


def acquire_lock(client: redis.Redis[str], lock_key: str, ttl_seconds: int) -> bool:
    """Atomic SETNX-with-expiry. Returns True if the lock was acquired, False if it's
    already held. This is what prevents two workers processing the same job, and what
    makes double-clicked / retried confirm-upload calls safe.
    """
    return bool(client.set(lock_key, "1", nx=True, ex=ttl_seconds))


def release_lock(client: redis.Redis[str], lock_key: str) -> None:
    client.delete(lock_key)


def job_processing_lock_key(job_id: str) -> str:
    return f"lock:job:{job_id}"


def confirm_idempotency_key(job_id: str) -> str:
    return f"confirm:{job_id}"
