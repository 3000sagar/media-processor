from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # --- AWS / storage ---
    aws_region: str = "us-east-1"
    s3_bucket_raw: str = "media-raw-uploads"
    s3_bucket_processed: str = "media-processed"
    cloudfront_domain: str = ""
    s3_endpoint_url: str | None = None  # set for local/moto testing only
    s3_public_endpoint_url: str | None = None  # browser/client endpoint for local S3

    # --- Broker / cache ---
    rabbitmq_url: str = "amqp://guest:guest@localhost:5672//"
    redis_url: str = "redis://localhost:6379/0"
    celery_result_backend: str = "redis://localhost:6379/1"

    # --- Auth ---
    api_key_header_name: str = "X-API-Key"
    valid_api_keys: str = ""  # comma-separated "key:owner_id" pairs, e.g. "abc123:owner_1,def456:owner_2"

    # --- Limits ---
    max_upload_size_mb: int = 500
    presigned_url_expiry_seconds: int = 900
    rate_limit_jobs_per_minute: int = 10
    job_status_ttl_seconds: int = 86400
    max_queue_depth_before_backpressure: int = 500

    # --- Media safety ---
    pillow_max_image_pixels: int = 178_956_970
    ffmpeg_allowed_protocols: str = "file"
    ffmpeg_timeout_seconds: int = 300
    image_max_width: int = 1920
    image_compression_quality: int = 85
    video_output_codec: str = "libx264"
    video_output_resolution: str = "1280x720"

    # --- Moderation ---
    moderation_provider: str = "none"  # "none" | "aws_rekognition" | "hive" — HUMAN DECISION REQUIRED before prod
    moderation_confidence_threshold: float = 0.8

    # --- Locking ---
    job_lock_ttl_seconds: int = 600
    confirm_idempotency_ttl_seconds: int = 60


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
