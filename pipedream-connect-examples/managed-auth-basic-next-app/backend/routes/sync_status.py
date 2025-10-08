"""
Sync Status API

Endpoints for checking background sync job status and history.
"""

import logging
from fastapi import APIRouter, HTTPException, Query
from celery.result import AsyncResult

from tasks.celery_config import app as celery_app
from services.database import db_service

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/sync/status/{job_id}")
async def get_sync_status(job_id: str):
    """
    Get status of a background sync job.

    Args:
        job_id: UUID from sync_jobs table

    Returns:
        {
            "job_id": "...",
            "task_id": "...",
            "status": "processing",
            "progress": { "phase": "fetching_details", "progress": 45 },
            "emails_processed": 123,
            "started_at": "2025-01-15T10:30:00Z",
            "error_message": null
        }
    """
    try:
        # Get job from database
        result = db_service.client.table('sync_jobs').select('*').eq('id', job_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        job = result.data[0]

        # If we have a Celery celery_task_id, get real-time status
        celery_state = None
        celery_meta = None
        if job.get('celery_task_id'):
            try:
                task = AsyncResult(job['celery_task_id'], app=celery_app)
                celery_state = task.state
                celery_meta = task.info if isinstance(task.info, dict) else {}
            except Exception as e:
                logger.warning(f"Could not get Celery status for task {job['celery_task_id']}: {e}")

        return {
            "job_id": job['id'],
            "celery_task_id": job.get('celery_task_id'),
            "status": job['status'],
            "celery_state": celery_state,  # PENDING, PROGRESS, SUCCESS, FAILURE
            "progress": job.get('progress') or celery_meta,
            "emails_processed": job.get('emails_processed', 0),
            "started_at": job.get('started_at'),
            "completed_at": job.get('completed_at'),
            "duration_seconds": job.get('duration_seconds'),
            "error_message": job.get('error_message'),
            "days": job.get('days')
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting sync status: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/sync/history")
async def get_sync_history(
    user_id: str = Query(...),
    limit: int = Query(10, ge=1, le=100)
):
    """
    Get user's sync job history.

    Args:
        user_id: User ID to get history for
        limit: Number of jobs to return (default 10, max 100)

    Returns:
        [
            {
                "job_id": "...",
                "status": "completed",
                "emails_processed": 2847,
                "started_at": "2025-01-15T10:30:00Z",
                "completed_at": "2025-01-15T10:45:00Z",
                "duration_seconds": 900
            },
            ...
        ]
    """
    try:
        result = db_service.client.table('sync_jobs').select(
            'id', 'status', 'days', 'emails_processed',
            'started_at', 'completed_at', 'duration_seconds', 'error_message'
        ).eq(
            'user_id', user_id
        ).order(
            'created_at', desc=True
        ).limit(limit).execute()

        return {
            "user_id": user_id,
            "total": len(result.data),
            "jobs": [
                {
                    "job_id": job['id'],
                    "status": job['status'],
                    "days": job['days'],
                    "emails_processed": job.get('emails_processed', 0),
                    "started_at": job.get('started_at'),
                    "completed_at": job.get('completed_at'),
                    "duration_seconds": job.get('duration_seconds'),
                    "error_message": job.get('error_message')
                }
                for job in result.data
            ]
        }

    except Exception as e:
        logger.error(f"Error getting sync history: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/sync/{job_id}/cancel")
async def cancel_sync_job(job_id: str):
    """
    Cancel a running sync job.

    Args:
        job_id: UUID from sync_jobs table

    Returns:
        {"status": "cancelled", "job_id": "..."}
    """
    try:
        # Get job from database
        result = db_service.client.table('sync_jobs').select('*').eq('id', job_id).execute()

        if not result.data:
            raise HTTPException(status_code=404, detail=f"Job {job_id} not found")

        job = result.data[0]

        # Can only cancel queued or processing jobs
        if job['status'] not in ['queued', 'processing']:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot cancel job with status '{job['status']}'"
            )

        # Revoke Celery task if it exists
        if job.get('celery_task_id'):
            try:
                celery_app.control.revoke(job['celery_task_id'], terminate=True)
                logger.info(f"Revoked Celery task {job['celery_task_id']}")
            except Exception as e:
                logger.warning(f"Could not revoke Celery task: {e}")

        # Update database
        db_service.client.table('sync_jobs').update({
            'status': 'failed',
            'error_message': 'Cancelled by user',
            'completed_at': 'now()'
        }).eq('id', job_id).execute()

        return {
            "status": "cancelled",
            "job_id": job_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error cancelling sync job: {e}")
        raise HTTPException(status_code=500, detail=str(e))
