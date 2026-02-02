"""
Celery Application Configuration

Configures Celery with Redis as the broker for background task processing.
Run with: celery -A app.workers.celery_app worker --loglevel=info
"""

import os
from celery import Celery

# Redis configuration
# Default to localhost Redis; can be overridden via environment variable
REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")

# Create Celery application
celery_app = Celery(
    "aml_pipeline",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=["app.workers.tasks"],
)

# Celery configuration
celery_app.conf.update(
    # Task settings
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task execution settings
    task_track_started=True,
    task_time_limit=3600,  # 1 hour hard limit
    task_soft_time_limit=3300,  # 55 min soft limit

    # Result backend settings
    result_expires=86400,  # Results expire after 24 hours

    # Worker settings
    worker_prefetch_multiplier=1,  # Disable prefetching for long tasks
    worker_concurrency=2,  # Max concurrent tasks per worker

    # Task routing (disabled for single-worker setup; enable for scaling)
    # task_routes={
    #     "app.workers.tasks.run_pipeline_task": {"queue": "pipeline"},
    # },

    # Task retry settings
    task_acks_late=True,
    task_reject_on_worker_lost=True,
)

# Optional: Configure task priorities
celery_app.conf.task_default_priority = 5
celery_app.conf.task_queue_max_priority = 10


if __name__ == "__main__":
    celery_app.start()
