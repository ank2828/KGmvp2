"""
Webhook endpoints for real-time Gmail event processing
"""

from fastapi import APIRouter, Request, HTTPException
import logging
import hmac
import hashlib

from services.database import db_service
from config import settings

router = APIRouter()
logger = logging.getLogger(__name__)


def verify_webhook_signature(request: Request, payload: bytes) -> bool:
    """
    Verify that webhook request is actually from Pipedream.

    NOTE: Pipedream signature verification method TBD -
    need to check Pipedream docs for their signature header name and algorithm.
    For now, this is a placeholder that logs a warning.

    TODO: Implement actual Pipedream signature verification once we have:
    - The header name Pipedream uses (e.g., X-Pipedream-Signature)
    - The signing algorithm (HMAC-SHA256, etc.)
    - Example signature from Pipedream webhook

    Args:
        request: FastAPI Request object with headers
        payload: Raw request body bytes

    Returns:
        True if signature is valid (currently always True as placeholder)
    """
    if not settings.pipedream_webhook_secret:
        logger.warning("PIPEDREAM_WEBHOOK_SECRET not set - webhook signature verification disabled")
        return True

    # TODO: Implement actual verification
    # signature = request.headers.get("X-Pipedream-Signature")
    # if not signature:
    #     logger.error("Missing webhook signature header")
    #     return False
    #
    # expected = hmac.new(
    #     settings.pipedream_webhook_secret.encode(),
    #     payload,
    #     hashlib.sha256
    # ).hexdigest()
    #
    # return hmac.compare_digest(signature, expected)

    logger.warning("Webhook signature verification not yet implemented")
    return True


async def is_already_processed(message_id: str, user_id: str) -> bool:
    """
    Check if we've already processed this email to prevent duplicates.

    Args:
        message_id: Gmail message ID
        user_id: User ID (external_user_id from Pipedream)

    Returns:
        True if this message has been processed before
    """
    try:
        result = db_service.client.table('processed_webhooks').select('id').eq(
            'message_id', message_id
        ).eq(
            'user_id', user_id
        ).execute()

        return len(result.data) > 0
    except Exception as e:
        logger.error(f"Error checking if webhook processed: {e}")
        # Fail open - allow processing to avoid blocking on database errors
        return False


async def mark_as_processed(message_id: str, user_id: str) -> bool:
    """
    Mark this email as processed.

    Args:
        message_id: Gmail message ID
        user_id: User ID (external_user_id from Pipedream)

    Returns:
        True if successfully marked, False if duplicate key error
    """
    try:
        db_service.client.table('processed_webhooks').insert({
            'message_id': message_id,
            'user_id': user_id
        }).execute()
        return True
    except Exception as e:
        # If duplicate key error, email was already processed by another request
        if "duplicate key" in str(e).lower() or "unique constraint" in str(e).lower():
            logger.info(f"Email {message_id} already marked as processed (race condition)")
            return False
        # Other errors should be logged but not block processing
        logger.error(f"Error marking webhook as processed: {e}")
        return True  # Allow processing to continue


@router.post("/webhooks/gmail")
async def handle_gmail_webhook(request: Request):
    """
    Receives new email events from Pipedream in real-time.

    Pipedream sends webhook when gmail-new-email-received trigger fires:
    {
        "external_user_id": "user-uuid",
        "event": {
            "id": "message-id",
            "threadId": "thread-id",
            "labelIds": [...],
            "snippet": "email preview...",
            "payload": {
                "headers": [...],
                "body": {...}
            },
            "internalDate": "1234567890000"
        }
    }

    Security:
    - Verifies webhook signature (TODO: implement)
    - Checks idempotency to prevent duplicate processing

    Returns:
        {"status": "queued", "message_id": "...", "user_id": "..."}
        {"status": "duplicate", "message_id": "..."}
    """
    # Get raw body for signature verification
    body = await request.body()

    # Verify webhook is from Pipedream
    if not verify_webhook_signature(request, body):
        logger.error("Invalid webhook signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    try:
        payload = await request.json()

        logger.info(f"Received Gmail webhook: {list(payload.keys())}")

        external_user_id = payload.get('external_user_id')
        email_event = payload.get('event', {})
        message_id = email_event.get('id')

        if not external_user_id or not email_event or not message_id:
            logger.error(f"Missing required fields in webhook payload: {payload}")
            raise HTTPException(status_code=400, detail="Invalid payload: missing required fields")

        # Idempotency check - have we seen this email before?
        if await is_already_processed(message_id, external_user_id):
            logger.info(f"Email {message_id} already processed, skipping")
            return {
                "status": "duplicate",
                "message_id": message_id
            }

        # Mark as processed immediately to prevent race conditions
        # If this fails due to duplicate, another request is already processing
        if not await mark_as_processed(message_id, external_user_id):
            logger.info(f"Email {message_id} being processed by another request")
            return {
                "status": "duplicate",
                "message_id": message_id
            }

        # TODO: Queue email processing (next step - async processing)
        # For now, just acknowledge receipt
        logger.info(f"Queued email {message_id} for processing for user {external_user_id}")

        return {
            "status": "queued",
            "message_id": message_id,
            "user_id": external_user_id
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Gmail webhook: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
