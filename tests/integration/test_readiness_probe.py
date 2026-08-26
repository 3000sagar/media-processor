import fakeredis
import pytest
from fastapi.testclient import TestClient
from moto import mock_aws

from app.config import get_settings


@pytest.fixture
def app_with_fake_redis(monkeypatch):
    get_settings.cache_clear()
    import app.api.v1.health as health_module

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(health_module, "get_redis_client", lambda settings: fake)

    from app.main import create_app

    return create_app()


def test_liveness_always_returns_ok_without_checking_dependencies(app_with_fake_redis):
    client = TestClient(app_with_fake_redis)
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_readiness_ok_when_redis_and_s3_available(app_with_fake_redis):
    settings = get_settings()
    with mock_aws():
        import boto3

        s3 = boto3.client("s3", region_name=settings.aws_region)
        s3.create_bucket(Bucket=settings.s3_bucket_raw)

        client = TestClient(app_with_fake_redis)
        resp = client.get("/api/v1/ready")
        assert resp.status_code == 200
        assert resp.json()["checks"]["redis"] == "ok"
        assert resp.json()["checks"]["s3"] == "ok"


def test_readiness_fails_when_bucket_missing(app_with_fake_redis):
    with mock_aws():
        # Deliberately do NOT create the bucket — S3 head_bucket should fail.
        client = TestClient(app_with_fake_redis)
        resp = client.get("/api/v1/ready")
        assert resp.status_code == 503
