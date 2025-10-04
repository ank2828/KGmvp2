"""
Webhook Processing Tasks

Celery tasks for processing incoming Gmail webhook events in the background.
Processes individual emails received via Pipedream webhooks.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

from tasks.celery_config import app
from services.graphiti_service import GraphitiService
from services.pipedream import pipedream_service
from routes.gmail import sanitize_user_id_for_graphiti, sanitize_for_falkordb

logger = logging.getLogger(__name__)


@app.task(
    bind=True,
    name="tasks.webhook_tasks.process_webhook_email",
    max_retries=3,
    default_retry_delay=30,  # 30 seconds
    acks_late=True,
)
def process_webhook_email(
    self,
    user_id: str,
    account_id: str,
    message_id: str,
    event_data: dict
):
    """
    Process a single email received via webhook.

    Args:
        user_id: Supabase user ID (external_user_id from Pipedream)
        account_id: Pipedream account ID
        message_id: Gmail message ID
        event_data: Full email event data from Pipedream webhook

    Returns:
        dict: {
            "status": "processed",
            "message_id": "...",
            "user_id": "..."
        }

    Raises:
        Exception: On unrecoverable errors (will retry up to 3 times)
    """
    task_id = self.request.id
    start_time = datetime.now(timezone.utc)

    try:
        logger.info(f"📨 [Task {task_id[:8]}] Processing webhook email {message_id} for user {user_id[:8]}...")

        # Execute async processing
        import asyncio
        result = asyncio.run(
            _process_webhook_email_async(
                user_id=user_id,
                account_id=account_id,
                message_id=message_id,
                event_data=event_data
            )
        )

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.info(f"✅ [Task {task_id[:8]}] Webhook processed in {duration:.2f}s")

        return {
            "status": "processed",
            "message_id": message_id,
            "user_id": user_id,
            "duration_seconds": duration
        }

    except Exception as exc:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.error(f"❌ [Task {task_id[:8]}] Webhook processing failed after {duration:.2f}s: {exc}")

        # Retry logic
        if self.request.retries < self.max_retries:
            logger.info(f"🔄 Retrying... (attempt {self.request.retries + 1}/{self.max_retries})")
            raise self.retry(exc=exc)

        raise


async def _process_webhook_email_async(
    user_id: str,
    account_id: str,
    message_id: str,
    event_data: dict
) -> dict:
    """
    Async implementation of webhook email processing.

    Extracts email content and adds to Graphiti knowledge graph.
    """
    sanitized_user_id = sanitize_user_id_for_graphiti(user_id)

    # Initialize Graphiti
    graphiti = GraphitiService()

    try:
        await graphiti.initialize()

        # Extract email headers
        payload = event_data.get('payload', {})
        headers_list = payload.get('headers', [])

        subject = sender = date_str = None
        for header in headers_list:
            name = header.get('name', '').lower()
            value = header.get('value', '')
            if name == 'subject':
                subject = value
            elif name == 'from':
                sender = value
            elif name == 'date':
                date_str = value

        # Extract body
        body = pipedream_service._extract_plain_text_body(event_data)

        # Build email text
        email_text = f"""From: {sanitize_for_falkordb(sender or 'Unknown')}
Subject: {sanitize_for_falkordb(subject or 'No Subject')}
Date: {date_str or 'Unknown'}

{sanitize_for_falkordb(body[:5000] if body else '')}"""

        # Get timestamp
        internal_date = event_data.get('internalDate', int(datetime.now(timezone.utc).timestamp() * 1000))
        reference_time = datetime.fromtimestamp(int(internal_date) / 1000, tz=timezone.utc)

        # Add to Graphiti
        from graphiti_core.nodes import EpisodeType

        await graphiti.graphiti.add_episode(
            name=f"Gmail Webhook {reference_time.date()} - {subject or 'No Subject'}",
            episode_body=email_text,
            source_description=f"Real-time email from {sender}",
            reference_time=reference_time,
            group_id=sanitized_user_id,
            source=EpisodeType.text
        )

        logger.info(f"✓ Added webhook email to knowledge graph: {subject}")

        return {
            "status": "success",
            "message_id": message_id
        }

    finally:
        await graphiti.close()
