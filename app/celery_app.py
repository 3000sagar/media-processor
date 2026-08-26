from celery import Celery

from app.config import get_settings

settings = get_settings()

celery_app = Celery(
    "media_processor",
    broker=settings.rabbitmq_url,
    backend=settings.celery_result_backend,
    include=["app.tasks.image_tasks", "app.tasks.video_tasks"],
)

celery_app.conf.update(
    task_acks_late=True,  # don't ack until the task actually finishes — a killed worker
                            # requeues the task instead of silently losing it
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,  # avoid one worker hoarding many long video jobs
    task_time_limit=settings.ffmpeg_timeout_seconds + 60,  # hard kill beyond ffmpeg's own timeout
    broker_connection_retry_on_startup=True,
)
