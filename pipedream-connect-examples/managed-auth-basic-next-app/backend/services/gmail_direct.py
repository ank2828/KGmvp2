"""
Gmail Direct API Service

Bypasses Pipedream proxy by calling Gmail API directly using OAuth tokens.
Tokens are obtained via Pipedream Connect (OAuth UI) but API calls go direct to Gmail.

This solves the "account and user mismatch" error from Pipedream proxy.
"""

import logging
import base64
import requests
from typing import Optional, Dict
from services.database import db_service

logger = logging.getLogger(__name__)


class GmailDirectService:
    """Direct Gmail API client using stored OAuth access tokens"""

    GMAIL_API_BASE = "https://www.googleapis.com/gmail/v1"

    def __init__(self, access_token: str):
        """
        Args:
            access_token: OAuth access token from Pipedream connected account
        """
        self.access_token = access_token
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json"
        }

    @classmethod
    def from_account(cls, user_id: str, account_id: str) -> "GmailDirectService":
        """
        Create GmailDirectService instance by reading credentials from Supabase.

        Args:
            user_id: Supabase user ID (external_user_id)
            account_id: Pipedream account ID (apn_xxx)

        Returns:
            GmailDirectService instance

        Raises:
            Exception: If account not found or credentials invalid
        """
        try:
            # Fetch credentials from Supabase (stored during OAuth)
            result = db_service.client.table('user_accounts').select('credentials').eq(
                'user_id', user_id
            ).eq('account_id', account_id).eq('status', 'active').execute()

            if not result.data or len(result.data) == 0:
                raise Exception(f"No active account found for user {user_id[:8]}... / account {account_id}")

            account = result.data[0]
            credentials = account.get('credentials')

            if not credentials:
                raise Exception(f"Account {account_id} has no credentials stored")

            # Extract OAuth access token from stored credentials
            if 'oauth' not in credentials or 'access_token' not in credentials['oauth']:
                raise Exception(f"Account {account_id} has invalid credential format")

            access_token = credentials['oauth']['access_token']
            logger.info(f"✅ Loaded access token from Supabase for user {user_id[:8]}... / account {account_id}")

            return cls(access_token=access_token)

        except Exception as e:
            logger.error(f"❌ Failed to load credentials from Supabase: {e}")
            raise

    def fetch_gmail_messages_paginated(
        self,
        after_timestamp: int,
        max_results: int = 100,
        page_token: Optional[str] = None
    ) -> Dict:
        """
        Fetch Gmail messages list with pagination (DIRECT API - no Pipedream proxy).

        Args:
            after_timestamp: Unix timestamp - fetch emails after this time
            max_results: Messages per page (max 100)
            page_token: Pagination token from previous response

        Returns:
            dict: {"messages": [...], "nextPageToken": "...", "resultSizeEstimate": ...}

        Raises:
            Exception: On API errors
        """
        try:
            # Build query - fetch emails from inbox and sent
            query = f"(in:inbox OR in:sent) after:{after_timestamp}"

            # Build request params
            params = {
                'q': query,
                'maxResults': max_results
            }
            if page_token:
                params['pageToken'] = page_token

            # Call Gmail API directly
            logger.debug(f"🔍 Calling Gmail API directly: {self.GMAIL_API_BASE}/users/me/messages")
            response = requests.get(
                f"{self.GMAIL_API_BASE}/users/me/messages",
                headers=self.headers,
                params=params,
                timeout=30
            )

            # Check for errors
            if response.status_code != 200:
                logger.error(f"❌ Gmail API error: {response.status_code} - {response.text}")
                raise Exception(f"Gmail API error: {response.status_code} - {response.text}")

            result = response.json()
            logger.info(f"✅ Direct Gmail API call successful: {result.get('resultSizeEstimate', 0)} messages")
            return result

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Gmail API request failed: {e}")
            raise Exception(f"Gmail API request error: {e}")
        except Exception as e:
            logger.error(f"❌ Gmail API call failed: {e}")
            raise

    def fetch_gmail_message_full(self, message_id: str) -> Dict:
        """
        Fetch specific Gmail message with full content (DIRECT API - no Pipedream proxy).

        Args:
            message_id: Gmail message ID

        Returns:
            dict: Full Gmail message object with payload, headers, body

        Raises:
            Exception: On API errors
        """
        try:
            # Fetch full message with format=full
            response = requests.get(
                f"{self.GMAIL_API_BASE}/users/me/messages/{message_id}",
                headers=self.headers,
                params={'format': 'full'},
                timeout=30
            )

            # Check for errors
            if response.status_code != 200:
                logger.error(f"❌ Gmail API error fetching message {message_id}: {response.status_code}")
                raise Exception(f"Gmail API error: {response.status_code}")

            return response.json()

        except requests.exceptions.RequestException as e:
            logger.error(f"❌ Failed to fetch message {message_id}: {e}")
            raise Exception(f"Gmail API request error: {e}")
        except Exception as e:
            logger.error(f"❌ Failed to fetch message {message_id}: {e}")
            raise

    def _decode_gmail_body(self, data: str) -> str:
        """Decode URL-safe base64 Gmail body data"""
        # Add padding if needed (Gmail sometimes omits it)
        return base64.urlsafe_b64decode(data + '===').decode('utf-8', errors='ignore')

    def _extract_plain_text_body(self, message: dict) -> Optional[str]:
        """
        Extract plain text from Gmail message payload.

        Reuses existing logic from pipedream_service.
        """
        payload = message.get('payload', {})

        # Simple message - body directly in payload
        if 'data' in payload.get('body', {}):
            return self._decode_gmail_body(payload['body']['data'])

        # Multipart message - search parts for text/plain
        for part in payload.get('parts', []):
            if part.get('mimeType') == 'text/plain':
                body_data = part.get('body', {}).get('data')
                if body_data:
                    return self._decode_gmail_body(body_data)

        # No plain text found
        return None
