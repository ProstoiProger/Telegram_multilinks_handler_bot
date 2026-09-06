from celery import Celery

from link_checker.config import get_settings

settings = get_settings()

celery_app = Celery(
    "link_checker",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["link_checker.tasks"],
)
celery_app.conf.update(
    accept_content=["json"],
    task_serializer="json",
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    worker_cancel_long_running_tasks_on_connection_loss=True,
    task_track_started=True,
    task_soft_time_limit=600,
    task_time_limit=630,
    result_expires=settings.job_ttl_seconds,
    broker_connection_retry_on_startup=True,
    broker_transport_options={
        "visibility_timeout": settings.monitor_lock_timeout_seconds + 60
    },
    beat_schedule={
        "dispatch-due-link-monitors": {
            "task": "link_checker.dispatch_due_jobs",
            "schedule": float(settings.monitor_dispatch_interval_seconds),
        }
    },
)
