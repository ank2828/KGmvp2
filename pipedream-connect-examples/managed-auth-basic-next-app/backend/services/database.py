"""
Supabase Database Service
Manages user account connections for Pipedream OAuth
"""

import logging
from typing import Optional, Dict
from datetime import datetime
from supabase import create_client, Client

from config import settings

logger = logging.getLogger(__name__)


class DatabaseService:
    """Manages user account storage in Supabase"""

    def __init__(self):
        self.client: Client = create_client(
            settings.supabase_url,
            settings.supabase_service_key
        )

    def get_user_account(self, user_id: str, app: str = "gmail") -> Optional[Dict]:
        """
        Get stored account for user.

        Args:
            user_id: User identifier
            app: Application name (default: gmail)

        Returns:
            Account dict or None if not found
        """
        try:
            response = self.client.table("user_accounts").select("*").eq(
                "user_id", user_id
            ).eq("app", app).eq("status", "active").execute()

            if response.data and len(response.data) > 0:
                return response.data[0]
            return None
        except Exception as e:
            logger.error(f"Error fetching user account: {e}")
            return None

    def save_user_account(
        self,
        user_id: str,
        external_user_id: str,
        account_id: str,
        app: str = "gmail"
    ) -> bool:
        """
        Save new account connection (upsert).

        Args:
            user_id: User identifier
            external_user_id: Pipedream external user ID
            account_id: Pipedream account ID (apn_xxx)
            app: Application name (default: gmail)

        Returns:
            True if successful, False otherwise
        """
        try:
            # Upsert - update if exists, insert if new
            # Uses UNIQUE constraint on (user_id, app)
            self.client.table("user_accounts").upsert({
                "user_id": user_id,
                "external_user_id": external_user_id,
                "account_id": account_id,
                "app": app,
                "status": "active",
                "connected_at": datetime.utcnow().isoformat()
            }, on_conflict="user_id,app").execute()

            logger.info(f"Saved account connection for user {user_id}, app {app}")
            return True
        except Exception as e:
            logger.error(f"Error saving user account: {e}")
            return False

    def disconnect_account(self, user_id: str, app: str = "gmail") -> bool:
        """
        Mark account as disconnected.

        Args:
            user_id: User identifier
            app: Application name (default: gmail)

        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.table("user_accounts").update({
                "status": "disconnected"
            }).eq("user_id", user_id).eq("app", app).execute()

            logger.info(f"Disconnected {app} for user {user_id}")
            return True
        except Exception as e:
            logger.error(f"Error disconnecting account: {e}")
            return False


# Singleton instance
db_service = DatabaseService()
