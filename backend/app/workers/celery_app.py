"""App Celery: parsing asincrono dei report scanner in background."""
from __future__ import annotations

from celery import Celery

from ..config import settings

celery_app = Celery(
    "vcm",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.workers.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_acks_late=True,
    worker_prefetch_multiplier=1,   # un file gigante per worker alla volta
    task_soft_time_limit=3600,
    task_time_limit=7200,
    broker_connection_retry_on_startup=True,
)
