"""
Celery configuration and task initialization.
Separate module to allow Celery workers and beat scheduler to import properly.
"""
import os
from celery import Celery

# Redis/Celery configuration
REDIS_URL = os.getenv("REDIS_URL", "")

# If REDIS_URL not set or is template, try service hostname first, then fallback
if not REDIS_URL or REDIS_URL.startswith("${"):
    REDIS_URL = "redis://redis:6379"  # Try Railway/Docker service name first

# Create Celery app
celery_app = Celery(
    "evaluation_pipeline",
    broker=REDIS_URL,
    backend=REDIS_URL
)

# Configure Celery
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=30 * 60,  # 30 minutes
    task_soft_time_limit=25 * 60,  # 25 minutes soft limit
    broker_connection_retry_on_startup=True,
)

# Register task routes
celery_app.conf.task_routes = {
    "evaluate_conversation": {"queue": "evaluation"},
    "analyze_and_suggest": {"queue": "analysis"},
}

# Configure periodic tasks (Celery Beat)
from celery.schedules import crontab

celery_app.conf.beat_schedule = {
    "analyze-evaluations-hourly": {
        "task": "analyze_and_suggest",
        "schedule": 3600.0,  # Run every hour (3600 seconds)
        "kwargs": {"window_hours": 1}
    },
    "analyze-evaluations-daily": {
        "task": "analyze_and_suggest",
        "schedule": 86400.0,  # Run daily (86400 seconds)
        "kwargs": {"window_hours": 24}
    },
}

# Use default scheduler (memory-based) instead of database
# This is more suitable for stateless cloud deployments
celery_app.conf.scheduler = "celery.beat:PersistentScheduler"
