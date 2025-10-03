"""
Authentication routes for managing Pipedream Connect accounts
"""

import logging
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from services.database import db_service

logger = logging.getLogger(__name__)
router = APIRouter()


class ConnectionRequest(BaseModel):
    """Request body for saving account connection"""
    user_id: str
    external_user_id: str
    account_id: str
    app: str = "gmail"


@router.get("/auth/check-connection")
async def check_connection(
    user_id: str = Query(...),
    app: str = Query("gmail")
):
    """
    Check if user has connected account.

    Args:
        user_id: User identifier
        app: Application name (default: gmail)

    Returns:
        Connection status and details if connected
    """
    account = db_service.get_user_account(user_id, app)

    if account:
        return {
            "connected": True,
            "account_id": account["account_id"],
            "external_user_id": account["external_user_id"],
            "connected_at": account["connected_at"],
            "app": app
        }

    return {"connected": False, "app": app}


@router.post("/auth/save-connection")
async def save_connection(request: ConnectionRequest):
    """
    Save account connection after user authenticates.

    Args:
        request: Connection details

    Returns:
        Success status
    """
    success = db_service.save_user_account(
        user_id=request.user_id,
        external_user_id=request.external_user_id,
        account_id=request.account_id,
        app=request.app
    )

    if not success:
        raise HTTPException(status_code=500, detail="Failed to save connection")

    return {"success": True, "message": "Connection saved"}


@router.post("/auth/disconnect")
async def disconnect_account(
    user_id: str = Query(...),
    app: str = Query("gmail")
):
    """
    Disconnect account.

    Args:
        user_id: User identifier
        app: Application name (default: gmail)

    Returns:
        Success status
    """
    success = db_service.disconnect_account(user_id, app)

    if not success:
        raise HTTPException(status_code=500, detail="Failed to disconnect")

    return {"success": True, "message": "Account disconnected"}
