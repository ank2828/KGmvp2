"""
Background Email Sync Tasks

Celery tasks for processing Gmail emails through Graphiti knowledge graph.
Handles large email syncs (up to 90 days / 2,847+ emails) in the background.

Production-ready implementation with:
- Proper async/sync handling
- Gmail API rate limit protection
- Celery state management
- Worker-level resource initialization
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from celery import Task
from celery.exceptions import Retry

from tasks.celery_config import app
from services.graphiti_service import GraphitiService
from services.pipedream import pipedream_service
from services.database import db_service
from services.entity_normalizer import EntityNormalizer
from services.entity_types import ENTITY_TYPES, EXCLUDED_ENTITY_TYPES
from routes.gmail import (
    sanitize_user_id_for_graphiti,
    group_emails_by_date,
    sanitize_for_falkordb,
)

logger = logging.getLogger(__name__)

# Worker-level service instances (initialized once per worker process)
_worker_graphiti = None


class GmailRateLimitError(Exception):
    """Raised when Gmail API rate limit is exceeded"""
    pass


class CallbackTask(Task):
    """
    Custom Celery task base class with lifecycle hooks.
    Tracks task state in Celery backend (not custom DB table).
    """

    def on_success(self, retval, task_id, args, kwargs):
        """Called when task executes successfully"""
        logger.info(f"Task {task_id} completed successfully: {retval.get('total_processed', 0)} emails")

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Called when task fails after all retries exhausted"""
        logger.error(f"Task {task_id} failed permanently: {exc}")

        # Update sync_jobs table with failure status
        try:
            job_id = kwargs.get('job_id')
            if job_id:
                db_service.client.table('sync_jobs').update({
                    'status': 'failed',
                    'error_message': str(exc)[:500],  # Truncate long errors
                    'completed_at': datetime.now(timezone.utc).isoformat()
                }).eq('id', job_id).execute()
        except Exception as e:
            logger.error(f"Failed to update sync_jobs on task failure: {e}")

    def on_retry(self, exc, task_id, args, kwargs, einfo):
        """Called when task is retried"""
        logger.warning(f"Task {task_id} retrying due to: {exc}")


@app.task(
    bind=True,
    base=CallbackTask,
    name="tasks.sync_tasks.sync_emails_background",
    max_retries=5,
    autoretry_for=(GmailRateLimitError, ConnectionError, TimeoutError),
    retry_backoff=True,  # Exponential backoff: 2^retry * base (60s)
    retry_backoff_max=600,  # Max 10 minutes between retries
    retry_jitter=True,  # Add randomness to prevent thundering herd
    acks_late=True,  # Override: acknowledge after completion
)
def sync_emails_background(
    self,
    user_id: str,
    account_id: str,
    days: int = 30,
    job_id: Optional[str] = None
):
    """
    Background task to sync Gmail emails to knowledge graph.

    Args:
        user_id: Supabase user ID
        account_id: Pipedream account ID
        days: Number of days to sync (default 30, max 90)
        job_id: Database record ID for tracking (from sync_jobs table)

    Returns:
        dict: {
            "status": "completed",
            "total_processed": 2847,
            "duration_seconds": 1234,
            "task_id": "abc-123"
        }

    Raises:
        Exception: On unrecoverable errors (will retry up to 5 times with backoff)

    Note:
        This task runs synchronously. Async operations (Graphiti) are handled
        via asyncio.run() in isolated event loops to avoid worker conflicts.
    """
    start_time = datetime.now(timezone.utc)
    task_id = self.request.id

    try:
        logger.info(f"🚀 [Task {task_id[:8]}] Starting {days}-day email sync for user {user_id[:8]}...")

        # Update Celery state (visible in Flower/monitoring)
        self.update_state(
            state='PROGRESS',
            meta={'phase': 'initializing', 'progress': 0}
        )

        # Update job status in database
        if job_id:
            db_service.client.table('sync_jobs').update({
                'status': 'processing',
                'started_at': start_time.isoformat(),
                'celery_task_id': task_id
            }).eq('id', job_id).execute()

        # Execute sync (handles its own async event loop)
        result = _sync_gmail_sync_wrapper(
            user_id=user_id,
            account_id=account_id,
            days=days,
            task=self,
            job_id=job_id
        )

        duration = (datetime.now(timezone.utc) - start_time).total_seconds()

        # Update job status to completed
        if job_id:
            db_service.client.table('sync_jobs').update({
                'status': 'completed',
                'completed_at': datetime.now(timezone.utc).isoformat(),
                'emails_processed': result.get('total_processed', 0),
                'duration_seconds': int(duration)
            }).eq('id', job_id).execute()

        logger.info(
            f"✅ [Task {task_id[:8]}] Sync completed: "
            f"{result.get('total_processed', 0)} emails in {duration:.1f}s"
        )

        return {
            "status": "completed",
            "total_processed": result.get('total_processed', 0),
            "duration_seconds": int(duration),
            "task_id": task_id
        }

    except Exception as exc:
        duration = (datetime.now(timezone.utc) - start_time).total_seconds()
        logger.error(f"❌ [Task {task_id[:8]}] Sync failed after {duration:.1f}s: {exc}")

        # Check if we should retry
        if self.request.retries < self.max_retries:
            retry_countdown = min(2 ** self.request.retries * 60, 600)  # Exponential backoff
            logger.info(
                f"🔄 Retrying in {retry_countdown}s... "
                f"(attempt {self.request.retries + 1}/{self.max_retries})"
            )
            raise self.retry(exc=exc, countdown=retry_countdown)

        # Final failure - update database
        if job_id:
            db_service.client.table('sync_jobs').update({
                'status': 'failed',
                'error_message': str(exc)[:500],
                'completed_at': datetime.now(timezone.utc).isoformat(),
                'duration_seconds': int(duration)
            }).eq('id', job_id).execute()

        raise


def _sync_gmail_sync_wrapper(
    user_id: str,
    account_id: str,
    days: int,
    task: Task,
    job_id: Optional[str] = None
) -> dict:
    """
    Synchronous wrapper that runs async Gmail sync in isolated event loop.

    This prevents conflicts with Celery worker's event loop by using asyncio.run()
    which creates and cleans up its own event loop.
    """
    import asyncio

    # Create fresh event loop for this task (prevents worker conflicts)
    try:
        result = asyncio.run(
            _sync_gmail_async(
                user_id=user_id,
                account_id=account_id,
                days=days,
                task=task,
                job_id=job_id
            )
        )
        return result
    except Exception as e:
        logger.error(f"Error in async sync wrapper: {e}")
        raise


async def _sync_gmail_async(
    user_id: str,
    account_id: str,
    days: int,
    task: Task,
    job_id: Optional[str] = None
) -> dict:
    """
    Async implementation of Gmail sync.

    Uses fresh GraphitiService instance per task to avoid connection issues.
    Updates Celery state via task.update_state() for monitoring.
    """
    sanitized_user_id = sanitize_user_id_for_graphiti(user_id)
    after_date = datetime.now(timezone.utc) - timedelta(days=days)
    after_timestamp = int(after_date.timestamp())

    # Initialize Graphiti for this task
    graphiti = GraphitiService()

    try:
        await graphiti.initialize()

        # STEP 1: Fetch all message IDs with pagination
        task.update_state(state='PROGRESS', meta={'phase': 'fetching_ids', 'progress': 0})

        all_message_ids = []
        page_token = None
        page_count = 0

        logger.info(f"📥 Fetching message IDs (after {after_date.date()}) using Pipedream Actions API...")

        while True:
            try:
                list_response = pipedream_service.fetch_gmail_messages_paginated(
                    external_user_id=user_id,
                    account_id=account_id,
                    after_timestamp=after_timestamp,
                    max_results=100,
                    page_token=page_token
                )
            except Exception as e:
                # Check for rate limit errors
                if 'quota' in str(e).lower() or 'rate limit' in str(e).lower():
                    logger.warning(f"Gmail API rate limit hit: {e}")
                    raise GmailRateLimitError(f"Gmail API rate limit: {e}")
                raise

            messages = list_response.get('messages', [])
            if not messages:
                break

            all_message_ids.extend([msg['id'] for msg in messages])
            page_count += 1

            # Update state every page (reduces overhead)
            task.update_state(
                state='PROGRESS',
                meta={
                    'phase': 'fetching_ids',
                    'message_ids_found': len(all_message_ids),
                    'pages_fetched': page_count
                }
            )

            page_token = list_response.get('nextPageToken')
            if not page_token:
                break

        if not all_message_ids:
            logger.info(f"No emails found in last {days} days")
            return {
                "status": "success",
                "total_processed": 0,
                "message": f"No emails found in last {days} days"
            }

        logger.info(f"📧 Found {len(all_message_ids)} emails")

        # STEP 2: Fetch full email details
        task.update_state(
            state='PROGRESS',
            meta={'phase': 'fetching_details', 'total_emails': len(all_message_ids)}
        )

        full_emails = []
        for idx, msg_id in enumerate(all_message_ids):
            try:
                full_message = pipedream_service.fetch_gmail_message_full(
                    external_user_id=user_id,
                    account_id=account_id,
                    message_id=msg_id
                )
                full_emails.append(full_message)

                # Update state every 50 emails (reduces overhead)
                if (idx + 1) % 50 == 0:
                    task.update_state(
                        state='PROGRESS',
                        meta={
                            'phase': 'fetching_details',
                            'emails_fetched': len(full_emails),
                            'total_emails': len(all_message_ids),
                            'progress': int((len(full_emails) / len(all_message_ids)) * 100)
                        }
                    )

            except Exception as e:
                if 'quota' in str(e).lower() or 'rate limit' in str(e).lower():
                    raise GmailRateLimitError(f"Gmail API rate limit: {e}")
                logger.error(f"Error fetching message {msg_id}: {e}")
                continue

        # STEP 3: Group by date
        emails_by_date = group_emails_by_date(full_emails)
        logger.info(f"📅 Grouped into {len(emails_by_date)} days")

        # STEP 4: Process chronologically
        task.update_state(
            state='PROGRESS',
            meta={'phase': 'processing', 'total_emails': len(full_emails)}
        )

        total_processed = 0
        MAX_EMAILS_PER_EPISODE = 50

        for date_idx, date in enumerate(sorted(emails_by_date.keys())):
            day_emails = emails_by_date[date]
            logger.info(f"Processing {len(day_emails)} emails from {date}")

            for batch_idx in range(0, len(day_emails), MAX_EMAILS_PER_EPISODE):
                batch = day_emails[batch_idx:batch_idx + MAX_EMAILS_PER_EPISODE]

                # PHASE 1: Store individual emails in Supabase FIRST
                from services.document_store import document_store

                document_ids_map = {}
                emails_for_storage = []

                for email_data in batch:
                    headers_list = email_data.get('payload', {}).get('headers', [])
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

                    body = gmail._extract_plain_text_body(email_data)

                    # Prepare for Supabase storage
                    emails_for_storage.append({
                        'id': email_data['id'],
                        'subject': subject or 'No Subject',
                        'body': body or '',
                        'from': sender or 'Unknown',
                        'to': '',
                        'date': date_str,
                        'thread_id': email_data.get('threadId', '')
                    })

                # Store emails in batch (with embeddings)
                try:
                    stored_doc_ids = await document_store.store_emails_batch(
                        user_id=sanitized_user_id,
                        emails=emails_for_storage
                    )

                    for email, doc_id in zip(emails_for_storage, stored_doc_ids):
                        document_ids_map[email['id']] = doc_id

                    logger.info(f"  Stored {len(stored_doc_ids)} emails in Supabase")
                except Exception as e:
                    logger.error(f"Failed to store emails in Supabase: {e}")

                # PHASE 2: Combine emails for Graphiti episode
                combined_parts = []
                for email_data in batch:
                    headers_list = email_data.get('payload', {}).get('headers', [])
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

                    body = gmail._extract_plain_text_body(email_data)

                    email_text = f"""From: {sanitize_for_falkordb(sender or 'Unknown')}
Subject: {sanitize_for_falkordb(subject or 'No Subject')}
Date: {date_str or 'Unknown'}

{sanitize_for_falkordb(body[:1000] if body else '')}"""

                    combined_parts.append(email_text)

                combined_body = "\n\n---EMAIL SEPARATOR---\n\n".join(combined_parts)

                # Get reference time
                oldest_email = batch[0]
                reference_time = datetime.fromtimestamp(
                    int(oldest_email.get('internalDate', 0)) / 1000,
                    tz=timezone.utc
                )

                # PHASE 3: Add to Graphiti
                try:
                    from graphiti_core.nodes import EpisodeType

                    result = await graphiti.graphiti.add_episode(
                        name=f"Gmail {date.isoformat()} (batch {batch_idx//MAX_EMAILS_PER_EPISODE + 1})",
                        episode_body=combined_body,
                        source_description=f"{len(batch)} emails from {date}",
                        reference_time=reference_time,
                        group_id=sanitized_user_id,
                        source=EpisodeType.text,
                        entity_types=ENTITY_TYPES,
                        excluded_entity_types=EXCLUDED_ENTITY_TYPES
                    )

                    # Normalize entities immediately after extraction
                    normalizer = EntityNormalizer(driver=graphiti.driver, source='gmail')
                    normalized_counts = await normalizer.normalize_and_persist(
                        graphiti_result=result,
                        group_id=sanitized_user_id
                    )
                    logger.info(f"  Normalized: {normalized_counts}")

                    # PHASE 4: Link documents to extracted entities
                    for entity_node in result.nodes:
                        entity_uuid = entity_node.uuid
                        entity_type = entity_node.labels[0] if entity_node.labels else 'Entity'
                        entity_name = entity_node.name

                        for email_id, doc_id in document_ids_map.items():
                            try:
                                await document_store.link_document_to_entity(
                                    document_id=doc_id,
                                    entity_uuid=entity_uuid,
                                    entity_type=entity_type,
                                    entity_name=entity_name,
                                    mention_count=1,
                                    relevance_score=0.8
                                )
                            except Exception as link_error:
                                logger.debug(f"Failed to link document to entity: {link_error}")

                    logger.info(f"  Linked {len(document_ids_map)} documents to {len(result.nodes)} entities")

                    total_processed += len(batch)
                    logger.info(f"✓ Batch {batch_idx//MAX_EMAILS_PER_EPISODE + 1}: {len(batch)} emails")

                    # Update state after each batch
                    task.update_state(
                        state='PROGRESS',
                        meta={
                            'phase': 'processing',
                            'emails_processed': total_processed,
                            'total_emails': len(full_emails),
                            'progress': int((total_processed / len(full_emails)) * 100),
                            'current_date': date.isoformat()
                        }
                    )

                except Exception as e:
                    logger.error(f"Error adding episode for {date}: {e}")
                    continue

        return {
            "status": "success",
            "total_processed": total_processed
        }

    finally:
        # Always cleanup
        await graphiti.close()
