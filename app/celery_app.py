"""
Celery Application
==================
Real Celery worker configuration for the LLM Security Gateway.

Broker:  Redis DB 2  (rate limiter uses DB 0, behavioral uses DB 1)
Backend: Redis DB 3  (task result storage)

Usage:
    # Start a worker (from the implementation/ directory):
    celery -A app.celery_app worker --loglevel=info --concurrency=2

    # Monitor tasks:
    celery -A app.celery_app flower

    # Inspect active tasks:
    celery -A app.celery_app inspect active
"""

import os
from celery import Celery
from celery.schedules import crontab
from app.config import settings

BROKER_URL  = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/2"
BACKEND_URL = f"redis://{settings.REDIS_HOST}:{settings.REDIS_PORT}/3"

celery_app = Celery(
    "llm_security_gateway",
    broker=BROKER_URL,
    backend=BACKEND_URL,
    include=["app.feedback.tasks"],          # auto-discovers tasks on worker startup
)

celery_app.conf.update(
    # Serialization
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],

    # Reliability
    task_acks_late=True,                     # only ack after task succeeds
    task_reject_on_worker_lost=True,         # re-queue on worker crash
    worker_prefetch_multiplier=1,            # fair dispatch — one task at a time per worker

    # Timeouts
    task_soft_time_limit=300,                # 5 min soft limit → SoftTimeLimitExceeded
    task_time_limit=360,                     # 6 min hard kill

    # Result expiry
    result_expires=86400,                    # keep results 24h in Redis

    # Retry defaults
    task_max_retries=3,
    task_default_retry_delay=60,             # 60s between retries

    # Beat scheduler (periodic tasks)
    beat_schedule={
        # Re-evaluate threshold alerts every 15 minutes
        "threshold-monitor-every-15min": {
            "task": "app.feedback.tasks.monitor_threat_thresholds",
            "schedule": crontab(minute="*/15"),
            "args": (),
        },
        # Nightly model eval gate at 02:00
        "nightly-eval-gate": {
            "task": "app.feedback.tasks.run_nightly_eval_gate",
            "schedule": crontab(hour=2, minute=0),
            "args": (),
        },
    },

    timezone="UTC",
)
