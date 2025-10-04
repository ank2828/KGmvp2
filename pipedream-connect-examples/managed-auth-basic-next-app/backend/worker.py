"""
Celery Worker Entry Point

Starts the Celery worker process to handle background tasks.

Usage:
    Local dev:
        celery -A worker worker --loglevel=info

    Production (with specific queues):
        celery -A worker worker --loglevel=info --queues=email_sync,webhooks

    Monitoring with Flower:
        celery -A worker flower
"""

from tasks.celery_config import app

# Import tasks to register them with Celery
from tasks import sync_tasks, webhook_tasks

if __name__ == '__main__':
    app.start()
