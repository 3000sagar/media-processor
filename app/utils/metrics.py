from prometheus_client import Counter, Gauge, Histogram

jobs_created_total = Counter("jobs_created_total", "Total jobs created")
jobs_completed_total = Counter("jobs_completed_total", "Total jobs completed successfully")
jobs_failed_total = Counter("jobs_failed_total", "Total jobs that failed", ["reason"])
moderation_manual_review_total = Counter(
    "moderation_manual_review_total", "Total jobs flagged for manual moderation review"
)
redis_lock_contention_total = Counter(
    "redis_lock_contention_total", "Total times a job lock was already held (contention/retry)"
)
s3_upload_errors_total = Counter("s3_upload_errors_total", "Total S3 upload failures")

queue_depth = Gauge("queue_depth", "Approximate pending task count")
worker_active_count = Gauge("worker_active_count", "Number of active Celery workers")

task_processing_duration_seconds = Histogram(
    "task_processing_duration_seconds",
    "Time spent processing a media task",
    ["media_type"],
    buckets=(1, 5, 15, 30, 60, 120, 300, 600),
)
