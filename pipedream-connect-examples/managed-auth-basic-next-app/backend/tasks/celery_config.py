"""
Celery Application Configuration

Configures Celery for background job processing with Redis broker.
Supports both local development (localhost Redis) and production (Google Cloud
Memorystore).

Redis Database Strategy:
- db=0: Celery broker (task queue)
- db=1: Result backend (task results)
This separation allows independent FLUSHDB operations and easier monitoring.
"""

import logging
from celery import Celery
from config import settings

logger = logging.getLogger(__name__)

# REDIS_URL format:
# Local dev: redis://localhost:6379/0
# Production (Memorystore with AUTH): redis://:password@<internal-ip>:6379/0
# Production (Memorystore no AUTH): redis://<internal-ip>:6379/0
REDIS_BROKER_URL = settings.redis_broker_url or "redis://localhost:6379/0"
REDIS_RESULT_BACKEND = settings.redis_result_backend or "redis://localhost:6379/1"

# Create Celery app
app = Celery(
    "gmail_knowledge_graph",
    broker=REDIS_BROKER_URL,
    backend=REDIS_RESULT_BACKEND,
)

# Celery configuration
app.conf.update(
    # Task serialization
    task_serializer="json",
    accept_content=["json"],  # Security: reject pickle to prevent code execution
    result_serializer="json",

    # Timezone
    timezone="UTC",
    enable_utc=True,

    # Task execution - Conservative defaults
    task_track_started=True,
    task_time_limit=600,  # 10 min default
    task_soft_time_limit=540,  # 9 min warning

    # Result backend
    result_expires=86400,  # 24 hours
    result_extended=True,  # Store args/kwargs for debugging

    # Redis connection settings (applies to BOTH broker and backend)
    # These are Celery-level settings that configure the Redis client
    redis_socket_keepalive=True,  # TCP keepalive for NAT/firewall traversal
    redis_socket_timeout=10.0,  # Read timeout (seconds)
    redis_socket_connect_timeout=5.0,  # Connection timeout (seconds)
    redis_retry_on_timeout=True,  # Retry on network timeouts
    redis_backend_health_check_interval=30,  # Check connection health every 30s
    redis_max_connections=50,  # Connection pool limit per worker
    # NOTE: With N workers, total connections = N × 50
    # Monitor with: redis-cli INFO clients

    # Broker connection settings
    broker_connection_retry_on_startup=True,  # Retry if Redis unavailable at startup
    broker_connection_retry=True,  # Retry on connection loss
    broker_connection_max_retries=10,  # Don't retry forever
    broker_connection_timeout=5.0,  # Connection timeout

    # Retry configuration
    task_acks_late=True,  # Acknowledge after execution (not before)
    task_reject_on_worker_lost=True,  # Requeue if worker dies

    # Worker configuration
    worker_prefetch_multiplier=1,  # Don't prefetch tasks (ideal for long-running jobs)
    worker_max_tasks_per_child=100,  # Recycle worker after 100 tasks (prevent memory leaks)

    # Monitoring
    worker_send_task_events=True,  # Enable for Flower/monitoring
    task_send_sent_event=True,  # Track task lifecycle

    # Logging
    worker_hijack_root_logger=False,  # Don't override root logger
    worker_log_format="[%(asctime)s: %(levelname)s/%(processName)s] %(message)s",
    worker_task_log_format=(
        "[%(asctime)s: %(levelname)s/%(processName)s]"
        "[%(task_name)s(%(task_id)s)] %(message)s"
    ),

    # Task discovery
    imports=(
        "tasks.sync_tasks",
        "tasks.webhook_tasks",
    ),
)

# Task routes - direct tasks to specific queues
app.conf.task_routes = {
    "tasks.sync_tasks.sync_emails_background": {"queue": "email_sync"},
    "tasks.webhook_tasks.process_webhook_email": {"queue": "webhooks"},
}

# Per-task configuration overrides
app.conf.task_annotations = {
    "tasks.sync_tasks.sync_emails_background": {
        "time_limit": 900,  # 15 min for large email syncs
        "soft_time_limit": 840,  # 14 min warning
        "rate_limit": "10/m",  # Respect Gmail API quotas
    },
    "tasks.webhook_tasks.process_webhook_email": {
        "time_limit": 60,  # 1 min for webhooks (should be fast)
        "soft_time_limit": 50,  # 50 sec warning
        "rate_limit": "100/m",  # Higher rate for webhooks
    },
}

logger.info(
    f"Celery configured - Broker: {REDIS_BROKER_URL} (db=0), "
    f"Backend: {REDIS_RESULT_BACKEND} (db=1)"
)
