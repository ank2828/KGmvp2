"""
Gmail API routes with Graphiti integration
"""

import html
import logging
import re
import asyncio
import hashlib
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from graphiti_core.nodes import EpisodeType

from services.graphiti_service import GraphitiService
from services.pipedream import pipedream_service
from services.database import db_service
from models.email import EmailMessage, EmailProcessingResponse
from dependencies import get_graphiti_service
from config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def sanitize_user_id_for_graphiti(user_id: str) -> str:
    """
    Hash user_id to avoid FalkorDB special character issues.
    Returns consistent 16-char hash for same user_id.
    """
    return hashlib.sha256(user_id.encode()).hexdigest()[:16]


def group_emails_by_date(emails: list) -> dict:
    """
    Group emails by date for batch processing.

    CRITICAL: Sorts emails chronologically BEFORE grouping
    to maintain temporal accuracy for Graphiti.

    Args:
        emails: List of Gmail message dicts with 'internalDate' (ms since epoch)

    Returns:
        Dict mapping date → [emails], sorted oldest to newest
    """
    # STEP 1: Sort ALL emails chronologically (oldest first)
    sorted_emails = sorted(emails, key=lambda e: int(e.get('internalDate', 0)))

    # STEP 2: Group by date
    emails_by_date = defaultdict(list)
    for email in sorted_emails:
        timestamp_ms = int(email.get('internalDate', 0))
        date = datetime.fromtimestamp(timestamp_ms / 1000, tz=timezone.utc).date()
        emails_by_date[date].append(email)

    # STEP 3: Return with sorted keys
    return dict(sorted(emails_by_date.items()))


async def sync_gmail_30_days_batched(
    user_id: str,
    account_id: str,
    graphiti: GraphitiService,
    days: int = 30
) -> dict:
    """
    Fetch and process Gmail history using daily batching.

    Args:
        user_id: Supabase user ID
        account_id: Pipedream account ID
        graphiti: GraphitiService instance
        days: Number of days to sync (default 30)

    Cost: ~$1 per 1000 emails
    Time: ~10-15 minutes per 1000 emails
    """
    # Sanitize user_id for FalkorDB
    sanitized_user_id = sanitize_user_id_for_graphiti(user_id)

    # Calculate date range
    after_date = datetime.now(timezone.utc) - timedelta(days=days)
    after_timestamp = int(after_date.timestamp())

    # STEP 1: Fetch all message IDs with pagination
    all_message_ids = []
    page_token = None
    history_id = None

    logger.info(f"Starting {days}-day sync for user {user_id[:8]}...")

    while True:
        list_response = pipedream_service.fetch_gmail_messages_paginated(
            external_user_id=user_id,
            account_id=account_id,
            after_timestamp=after_timestamp,
            max_results=100,
            page_token=page_token
        )

        messages = list_response.get('messages', [])
        if not messages:
            break

        all_message_ids.extend([msg['id'] for msg in messages])
        history_id = list_response.get('historyId')
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

    logger.info(f"Found {len(all_message_ids)} emails")

    # STEP 2: Fetch full email details
    full_emails = []
    for msg_id in all_message_ids:
        try:
            full_message = pipedream_service.fetch_gmail_message_full(
                external_user_id=user_id,
                account_id=account_id,
                message_id=msg_id
            )
            full_emails.append(full_message)
        except Exception as e:
            logger.error(f"Error fetching message {msg_id}: {e}")
            continue

    # STEP 3: Group by date (chronologically sorted)
    emails_by_date = group_emails_by_date(full_emails)
    logger.info(f"Grouped into {len(emails_by_date)} days")

    # STEP 4: Process chronologically
    total_processed = 0
    MAX_EMAILS_PER_EPISODE = 50

    for date in sorted(emails_by_date.keys()):
        day_emails = emails_by_date[date]
        logger.info(f"Processing {len(day_emails)} emails from {date}")

        for batch_idx in range(0, len(day_emails), MAX_EMAILS_PER_EPISODE):
            batch = day_emails[batch_idx:batch_idx + MAX_EMAILS_PER_EPISODE]

            # Combine emails with per-field sanitization
            combined_parts = []
            for email_data in batch:
                # Extract headers using existing pattern
                headers_list = email_data.get('payload', {}).get('headers', [])
                subject = None
                sender = None
                date_str = None

                for header in headers_list:
                    name = header.get('name', '').lower()
                    value = header.get('value', '')

                    if name == 'subject':
                        subject = value
                    elif name == 'from':
                        sender = value
                    elif name == 'date':
                        date_str = value

                # Extract body using existing method
                body = pipedream_service._extract_plain_text_body(email_data)

                # Build email text with sanitization
                email_text = f"""From: {sanitize_for_falkordb(sender or 'Unknown')}
Subject: {sanitize_for_falkordb(subject or 'No Subject')}
Date: {date_str or 'Unknown'}

{sanitize_for_falkordb(body[:5000] if body else '')}"""

                combined_parts.append(email_text)

            combined_body = "\n\n---EMAIL SEPARATOR---\n\n".join(combined_parts)

            # Get reference time from oldest email
            oldest_email = batch[0]
            reference_time = datetime.fromtimestamp(
                int(oldest_email.get('internalDate', 0)) / 1000,
                tz=timezone.utc
            )

            # Create Graphiti episode with error handling
            try:
                await graphiti.graphiti.add_episode(
                    name=f"Gmail {date.isoformat()} (batch {batch_idx//MAX_EMAILS_PER_EPISODE + 1})",
                    episode_body=combined_body,
                    source_description=f"{len(batch)} emails from {date}",
                    reference_time=reference_time,
                    source=EpisodeType.text,
                    group_id=sanitized_user_id
                )

                total_processed += len(batch)
                logger.info(f"Processed: {total_processed}/{len(all_message_ids)} emails")

            except Exception as e:
                logger.error(f"Failed batch {date} idx {batch_idx}: {e}")
                continue

            # Rate limiting
            await asyncio.sleep(3)

    logger.info(f"Sync complete: {total_processed} emails")

    return {
        "status": "success",
        "total_processed": total_processed,
        "history_id": history_id
    }


def clean_sender(sender: str) -> str:
    """Remove @ symbols that break FalkorDB search"""
    if '<' in sender:
        # Extract name: "John Doe <email>" → "John Doe"
        return sender.split('<')[0].strip()
    # Replace @: "noreply@company.com" → "noreply at company.com"
    return sender.replace('@', ' at ')


def sanitize_for_falkordb(text: str) -> str:
    """
    Clean text for FalkorDB entity search.

    Order matters:
    1. Decode HTML entities (&amp; → &)
    2. Strip HTML tags
    3. Remove URLs
    4. Sanitize special characters
    5. Clean whitespace
    """
    if not text:
        return text

    # Step 1: Decode HTML entities FIRST
    text = html.unescape(text)

    # Step 2: Strip HTML tags (<br/>, <img/>, etc.)
    text = re.sub(r'<[^>]+>', '', text)

    # Step 3: Remove URLs
    text = re.sub(r'https?://\S+', '[URL]', text)
    text = re.sub(r'www\.\S+', '[URL]', text)

    # Step 4: Sanitize special chars
    text = text.replace('@', ' at ')
    text = text.replace('*', '')
    # Note: & is safe after decoding, only &amp; entity was problematic

    # Step 5: Clean up whitespace from removed tags
    text = re.sub(r'\s+', ' ', text).strip()

    return text


@router.get("/gmail/fetch")
async def fetch_gmail(
    user_id: str = Query(...),
    max_results: int = Query(10, le=50),
    process_graph: bool = Query(True),
    graphiti: GraphitiService = Depends(get_graphiti_service),
):
    """Fetch Gmail and process through Graphiti"""
    try:
        # Get stored account connection from database
        account = db_service.get_user_account(user_id, "gmail")

        if not account:
            raise HTTPException(
                status_code=401,
                detail="Gmail not connected. Please connect your account first."
            )

        external_user_id = account["external_user_id"]
        account_id = account["account_id"]

        # Sanitize user_id for Graphiti processing (remove hyphens to avoid RediSearch syntax errors)
        sanitized_user_id = external_user_id.replace('-', '')

        # Fetch from Pipedream (returns list directly)
        raw_emails = pipedream_service.fetch_gmail_messages(
            external_user_id=external_user_id,
            account_id=account_id,
            max_results=max_results
        )

        if not raw_emails:
            return {"success": True, "count": 0, "emails": []}

        # Convert to EmailMessage models and fetch bodies
        emails = []
        for i, data in enumerate(raw_emails, 1):
            try:
                message_id = data.get('id', '')

                # Fetch full body for this message
                logger.info(f"Fetching body for message {i}/{len(raw_emails)}: {message_id}")
                body = pipedream_service.fetch_gmail_message_body(
                    message_id=message_id,
                    external_user_id=external_user_id,
                    account_id=account_id
                )

                # Truncate body to max length
                if body and len(body) > settings.max_email_body_length:
                    original_length = len(body)
                    body = body[:settings.max_email_body_length]
                    logger.info(f"Truncated body from {original_length} to {settings.max_email_body_length} chars")

                # Sanitize body for FalkorDB (URLs and @ symbols)
                if body:
                    body = sanitize_for_falkordb(body)

                # Sanitize subject for FalkorDB
                subject = sanitize_for_falkordb(data.get('subject', 'No Subject'))

                emails.append(EmailMessage(
                    subject=subject,
                    sender=clean_sender(data.get('from', 'Unknown')),
                    date=data.get('date', ''),
                    message_id=message_id,
                    body=body
                ))
            except Exception as e:
                logger.warning(f"Parse error: {e}")

        # Process through Graphiti
        results = []
        for i, email in enumerate(emails, 1):
            try:
                if process_graph and settings.graphiti_enabled:
                    graph_result = await graphiti.process_email(email, sanitized_user_id)
                    results.append(EmailProcessingResponse(email=email, graph_processing=graph_result))
                else:
                    results.append(EmailProcessingResponse(email=email, skipped=True))
            except Exception as e:
                logger.error(f"Graphiti error on email {i}: {e}")
                results.append(EmailProcessingResponse(email=email, error=str(e)))

        return {"success": True, "count": len(results), "emails_processed": results}

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/graph/search")
async def search_graph(
    query: str = Query(..., min_length=3),
    user_id: str = Query(...),
    limit: int = Query(10, le=50),
    graphiti: GraphitiService = Depends(get_graphiti_service),
):
    """Search knowledge graph"""
    try:
        # Sanitize user_id to avoid RediSearch syntax errors with hyphens
        sanitized_user_id = user_id.replace('-', '')
        results = await graphiti.search(query, limit, sanitized_user_id)
        return {"query": query, "user_id": user_id, "count": len(results), "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/dev/clear-database")
async def clear_database(
    confirm: bool = Query(False, description="Must be true to confirm deletion"),
    graphiti: GraphitiService = Depends(get_graphiti_service),
):
    """
    DEV/TEST ONLY: Clear all data from FalkorDB Cloud.

    WARNING: This permanently deletes all nodes, edges, and episodes.

    Parameters:
    - confirm: Must be set to true to execute (safety check)

    Returns:
    - success: Boolean
    - nodes_deleted: Count of nodes removed
    - message: Confirmation message
    """
    # Safety check: require explicit confirmation
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail="Must set confirm=true to clear database. This operation is irreversible."
        )

    # Additional safety: only allow in dev mode
    if not settings.graphiti_enabled:
        raise HTTPException(
            status_code=403,
            detail="Graphiti not enabled. Cannot clear database."
        )

    try:
        logger.warning("⚠️  Database clear requested via API")
        result = await graphiti.clear_database()
        logger.info(f"✅ Database cleared: {result['nodes_deleted']} nodes deleted")
        return result

    except Exception as e:
        logger.error(f"❌ Database clear failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to clear database: {str(e)}"
        )


@router.post("/gmail/sync-30-days-direct")
async def start_30_day_sync_direct(
    user_id: str = Query(...),
    account_id: str = Query(...),
    days: int = Query(30, ge=1, le=90, description="Number of days to sync (1-90)"),
    graphiti: GraphitiService = Depends(get_graphiti_service),
):
    """
    [LEGACY] Direct synchronous Gmail sync with Supabase state tracking.

    DEPRECATED: Use /gmail/sync-30-days instead (background processing).
    This endpoint blocks until sync completes - kept for backward compatibility.

    Args:
        user_id: Supabase user ID
        account_id: Pipedream account ID
        days: Number of days to sync (default 30, max 90)

    Prevents duplicate syncs, tracks progress, handles errors.
    """
    # Check if sync already in progress
    try:
        response = db_service.client.table('sync_state')\
            .select('*')\
            .eq('user_id', user_id)\
            .eq('app', 'gmail')\
            .maybe_single()\
            .execute()

        if response.data and response.data.get('sync_in_progress'):
            raise HTTPException(
                status_code=409,
                detail="Sync already in progress for this user"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking sync state: {e}")

    # Mark sync as in progress
    try:
        db_service.client.table('sync_state').upsert({
            'user_id': user_id,
            'app': 'gmail',
            'sync_in_progress': True,
            'last_sync_status': 'in_progress',
            'oldest_synced_date': (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).execute()
    except Exception as e:
        logger.error(f"Error updating sync state: {e}")
        raise HTTPException(status_code=500, detail="Failed to start sync")

    # Run the sync
    try:
        result = await sync_gmail_30_days_batched(
            user_id=user_id,
            account_id=account_id,
            graphiti=graphiti,
            days=days
        )

        # Update sync state on success
        db_service.client.table('sync_state').update({
            'sync_in_progress': False,
            'last_sync_status': 'success',
            'last_synced_at': datetime.now(timezone.utc).isoformat(),
            'total_emails_synced': result['total_processed'],
            'last_history_id': result.get('history_id'),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).eq('user_id', user_id).execute()

        return result

    except Exception as e:
        logger.error(f"Sync failed: {e}")

        # Update sync state on failure
        db_service.client.table('sync_state').update({
            'sync_in_progress': False,
            'last_sync_status': 'failed',
            'last_error': str(e),
            'updated_at': datetime.now(timezone.utc).isoformat()
        }).eq('user_id', user_id).execute()

        raise HTTPException(status_code=500, detail=f"Sync failed: {str(e)}")


@router.post("/gmail/sync-30-days")
async def start_30_day_sync(
    user_id: str = Query(...),
    account_id: str = Query(...),
    days: int = Query(30, ge=1, le=90, description="Number of days to sync (1-90)"),
):
    """
    Queue Gmail sync as background Celery task.

    Args:
        user_id: Supabase user ID
        account_id: Pipedream account ID
        days: Number of days to sync (default 30, max 90)

    Returns immediately with job_id for progress tracking.
    User can close browser - sync continues in background.
    """
    # Check if sync already in progress for this user
    try:
        active_jobs = db_service.client.table('sync_jobs')\
            .select('id')\
            .eq('user_id', user_id)\
            .in_('status', ['queued', 'processing'])\
            .execute()

        if active_jobs.data:
            raise HTTPException(
                status_code=409,
                detail=f"Sync already in progress (job_id: {active_jobs.data[0]['id']})"
            )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error checking active syncs: {e}")

    # Create job record
    try:
        job_result = db_service.client.table('sync_jobs').insert({
            'user_id': user_id,
            'account_id': account_id,
            'status': 'queued',
            'days': days
        }).execute()

        job_id = job_result.data[0]['id']
        logger.info(f"Created sync job {job_id} for user {user_id[:8]}")

    except Exception as e:
        logger.error(f"Error creating sync job: {e}")
        raise HTTPException(status_code=500, detail="Failed to create sync job")

    # Queue Celery task
    try:
        from tasks.sync_tasks import sync_emails_background

        task = sync_emails_background.delay(
            user_id=user_id,
            account_id=account_id,
            days=days,
            job_id=job_id
        )

        # Update job with task_id
        db_service.client.table('sync_jobs').update({
            'task_id': task.id
        }).eq('id', job_id).execute()

        logger.info(f"Queued Celery task {task.id} for job {job_id}")

        return {
            "status": "queued",
            "job_id": job_id,
            "task_id": task.id,
            "message": f"Sync queued for {days} days. Check /api/sync/status/{job_id} for progress."
        }

    except Exception as e:
        logger.error(f"Error queuing Celery task: {e}")

        # Mark job as failed
        db_service.client.table('sync_jobs').update({
            'status': 'failed',
            'error_message': f"Failed to queue task: {str(e)}"
        }).eq('id', job_id).execute()

        raise HTTPException(status_code=500, detail=f"Failed to queue sync: {str(e)}")


@router.get("/gmail/sync-status")
async def get_sync_status(user_id: str = Query(...)):
    """
    Get current sync status for a user.
    """
    try:
        response = db_service.client.table('sync_state')\
            .select('*')\
            .eq('user_id', user_id)\
            .eq('app', 'gmail')\
            .maybe_single()\
            .execute()

        # Check if response and data exist
        if not response or not hasattr(response, 'data') or not response.data:
            return {"status": "never_synced"}

        return response.data

    except Exception as e:
        logger.error(f"Error fetching sync status: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch sync status")
