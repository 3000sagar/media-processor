import fakeredis

from app.services import idempotency


def test_second_lock_attempt_fails_while_first_holds():
    client = fakeredis.FakeRedis(decode_responses=True)
    lock_key = idempotency.job_processing_lock_key("job-1")

    first = idempotency.acquire_lock(client, lock_key, ttl_seconds=60)
    second = idempotency.acquire_lock(client, lock_key, ttl_seconds=60)  # simulates a second worker racing on the same job

    assert first is True
    assert second is False  # this is what stops duplicate processing


def test_lock_is_acquirable_again_after_release():
    client = fakeredis.FakeRedis(decode_responses=True)
    lock_key = idempotency.job_processing_lock_key("job-2")

    idempotency.acquire_lock(client, lock_key, ttl_seconds=60)
    idempotency.release_lock(client, lock_key)
    reacquired = idempotency.acquire_lock(client, lock_key, ttl_seconds=60)

    assert reacquired is True


def test_confirm_upload_idempotency_key_is_distinct_from_processing_lock():
    # These must be different Redis keys — the "don't double-enqueue" lock (§ confirm-upload)
    # and the "don't double-process" lock (§ worker task) are different concerns with
    # different TTLs, and collapsing them into one key would create a subtle bug where
    # a slow confirm-upload call could block the worker's own lock, or vice versa.
    job_id = "job-3"
    assert idempotency.job_processing_lock_key(job_id) != idempotency.confirm_idempotency_key(job_id)
