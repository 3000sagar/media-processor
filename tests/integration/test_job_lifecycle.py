import io
import os

os.environ.setdefault("VALID_API_KEYS", "testkey123:owner_1,testkey456:owner_2")
os.environ.setdefault("MODERATION_PROVIDER", "none")

import fakeredis
import pytest
import requests
from moto import mock_aws
from PIL import Image

from app.config import get_settings


@pytest.fixture
def shared_fake_redis():
    server = fakeredis.FakeServer()
    return lambda: fakeredis.FakeRedis(server=server, decode_responses=True)


@pytest.fixture
def client_and_settings(shared_fake_redis, monkeypatch):
    """Wires the FastAPI app + Celery tasks to a shared in-memory fake Redis and moto S3,
    with Celery running in eager (synchronous) mode so the test doesn't need a real broker.
    """
    get_settings.cache_clear()

    from app.celery_app import celery_app
    celery_app.conf.task_always_eager = True
    celery_app.conf.task_eager_propagates = True

    import app.api.v1.jobs as jobs_module
    import app.api.v1.health as health_module
    import app.tasks.image_tasks as image_tasks_module
    import app.tasks.video_tasks as video_tasks_module

    make_redis = shared_fake_redis
    original_get_redis_dependency = jobs_module._get_redis  # capture BEFORE any patching —
    # dependency_overrides must be keyed on the exact function object used in Depends(...)
    monkeypatch.setattr(health_module, "get_redis_client", lambda settings: make_redis())
    monkeypatch.setattr(image_tasks_module, "get_redis_client", lambda settings: make_redis())
    monkeypatch.setattr(video_tasks_module, "get_redis_client", lambda settings: make_redis())

    settings = get_settings()

    with mock_aws():
        import boto3

        s3 = boto3.client("s3", region_name=settings.aws_region)
        s3.create_bucket(Bucket=settings.s3_bucket_raw)
        s3.create_bucket(Bucket=settings.s3_bucket_processed)

        from fastapi.testclient import TestClient
        from app.main import create_app

        app = create_app()
        app.dependency_overrides[original_get_redis_dependency] = make_redis
        test_client = TestClient(app)

        yield test_client, settings


def _sample_jpeg_bytes() -> bytes:
    img = Image.new("RGB", (800, 600), color=(120, 50, 200))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def _sample_mp4_bytes() -> bytes:
    fixture_path = os.path.join(os.path.dirname(__file__), "..", "fixtures", "sample.mp4")
    with open(fixture_path, "rb") as f:
        return f.read()


def test_full_job_lifecycle_image(client_and_settings):
    client, settings = client_and_settings
    headers = {"X-API-Key": "testkey123"}

    create_resp = client.post(
        "/api/v1/jobs",
        json={"media_type": "image", "declared_filename": "vacation.jpg", "operations": ["resize", "compress"]},
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    job_id = body["job_id"]
    assert body["status"] == "pending"

    # Simulate the client's direct-to-S3 upload using the presigned POST fields returned above.
    upload_post = body["upload_post"]
    files = {"file": ("vacation.jpg", _sample_jpeg_bytes(), "image/jpeg")}
    upload_resp = requests.post(upload_post["url"], data=upload_post["fields"], files=files)
    assert upload_resp.status_code in (200, 204), upload_resp.text

    confirm_resp = client.post(f"/api/v1/jobs/{job_id}/confirm-upload", headers=headers)
    assert confirm_resp.status_code == 200, confirm_resp.text
    # Eager Celery execution means processing already ran synchronously by this point.
    assert confirm_resp.json()["status"] == "completed", confirm_resp.json()

    status_resp = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    assert status_resp.status_code == 200
    final = status_resp.json()
    assert final["status"] == "completed"
    assert final["result_url"]
    assert final["moderation_status"] == "approved"


def test_missing_api_key_rejected(client_and_settings):
    client, _ = client_and_settings
    resp = client.post("/api/v1/jobs", json={"media_type": "image", "declared_filename": "a.jpg", "operations": ["resize"]})
    assert resp.status_code == 401
    body = resp.json()
    assert body["status"] == 401
    assert "title" in body  # RFC 7807 shape


def test_cross_owner_cannot_read_job(client_and_settings):
    client, _ = client_and_settings
    owner1_headers = {"X-API-Key": "testkey123"}
    owner2_headers = {"X-API-Key": "testkey456"}

    create_resp = client.post(
        "/api/v1/jobs",
        json={"media_type": "image", "declared_filename": "private.jpg", "operations": ["resize"]},
        headers=owner1_headers,
    )
    job_id = create_resp.json()["job_id"]

    forbidden_resp = client.get(f"/api/v1/jobs/{job_id}", headers=owner2_headers)
    assert forbidden_resp.status_code == 403


def test_cross_owner_cannot_confirm_job(client_and_settings):
    client, _ = client_and_settings
    owner1_headers = {"X-API-Key": "testkey123"}
    owner2_headers = {"X-API-Key": "testkey456"}

    create_resp = client.post(
        "/api/v1/jobs",
        json={"media_type": "image", "declared_filename": "private.jpg", "operations": ["resize"]},
        headers=owner1_headers,
    )
    job_id = create_resp.json()["job_id"]

    forbidden_resp = client.post(f"/api/v1/jobs/{job_id}/confirm-upload", headers=owner2_headers)
    assert forbidden_resp.status_code == 403


def test_invalid_operation_rejected(client_and_settings):
    client, _ = client_and_settings
    resp = client.post(
        "/api/v1/jobs",
        json={"media_type": "image", "declared_filename": "a.jpg", "operations": ["hack_the_mainframe"]},
        headers={"X-API-Key": "testkey123"},
    )
    assert resp.status_code == 422


def test_unknown_job_returns_404(client_and_settings):
    client, _ = client_and_settings
    resp = client.get("/api/v1/jobs/does-not-exist", headers={"X-API-Key": "testkey123"})
    assert resp.status_code == 404


def test_full_job_lifecycle_video(client_and_settings):
    """Same lifecycle as the image test, but exercises the real FFmpeg transcode + thumbnail
    path end to end through the actual Celery task, not just the ffmpeg_runner unit in isolation.
    """
    client, settings = client_and_settings
    headers = {"X-API-Key": "testkey123"}

    create_resp = client.post(
        "/api/v1/jobs",
        json={"media_type": "video", "declared_filename": "clip.mp4", "operations": ["transcode", "thumbnail"]},
        headers=headers,
    )
    assert create_resp.status_code == 201, create_resp.text
    body = create_resp.json()
    job_id = body["job_id"]

    upload_post = body["upload_post"]
    files = {"file": ("clip.mp4", _sample_mp4_bytes(), "video/mp4")}
    upload_resp = requests.post(upload_post["url"], data=upload_post["fields"], files=files)
    assert upload_resp.status_code in (200, 204), upload_resp.text

    confirm_resp = client.post(f"/api/v1/jobs/{job_id}/confirm-upload", headers=headers)
    assert confirm_resp.status_code == 200, confirm_resp.text
    assert confirm_resp.json()["status"] == "completed", confirm_resp.json()

    status_resp = client.get(f"/api/v1/jobs/{job_id}", headers=headers)
    final = status_resp.json()
    assert final["status"] == "completed"
    assert final["result_url"]
    assert final["moderation_status"] == "approved"


def test_video_job_with_disguised_non_video_file_fails_validation(client_and_settings):
    """Proves the magic-byte check actually runs inside the real task path, not just
    in isolation — an attacker declaring media_type=video but uploading a JPEG must fail.
    """
    client, settings = client_and_settings
    headers = {"X-API-Key": "testkey123"}

    create_resp = client.post(
        "/api/v1/jobs",
        json={"media_type": "video", "declared_filename": "clip.mp4", "operations": ["transcode"]},
        headers=headers,
    )
    job_id = create_resp.json()["job_id"]
    upload_post = create_resp.json()["upload_post"]

    # Upload a real JPEG but declare it as video — S3's own content-type policy condition
    # is what we're implicitly testing survives here too (moto enforces the "starts-with"
    # condition against the Content-Type field sent in the POST, not the byte content).
    files = {"file": ("clip.mp4", _sample_jpeg_bytes(), "video/mp4")}
    upload_resp = requests.post(upload_post["url"], data=upload_post["fields"], files=files)
    assert upload_resp.status_code in (200, 204)

    confirm_resp = client.post(f"/api/v1/jobs/{job_id}/confirm-upload", headers=headers)
    assert confirm_resp.json()["status"] == "failed"
    assert "file type mismatch" in confirm_resp.json()["error"]
