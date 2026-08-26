import os

os.environ.setdefault("VALID_API_KEYS", "testkey123:owner_1,testkey456:owner_2")
os.environ.setdefault("MODERATION_PROVIDER", "none")
os.environ.setdefault("S3_ENDPOINT_URL", "")

import boto3
import fakeredis
import pytest
from moto import mock_aws

from app.config import get_settings


@pytest.fixture
def settings():
    get_settings.cache_clear()
    return get_settings()


@pytest.fixture
def s3_bucket_names(settings):
    return settings.s3_bucket_raw, settings.s3_bucket_processed


@pytest.fixture
def moto_s3(settings, s3_bucket_names):
    with mock_aws():
        client = boto3.client("s3", region_name=settings.aws_region)
        raw_bucket, processed_bucket = s3_bucket_names
        client.create_bucket(Bucket=raw_bucket)
        client.create_bucket(Bucket=processed_bucket)
        yield client


@pytest.fixture
def fake_redis():
    return fakeredis.FakeRedis(decode_responses=True)
