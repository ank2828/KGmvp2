"""
Pipedream SDK wrapper service
Handles all Pipedream API interactions
"""

import os
import base64
import logging
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv
from pipedream import Pipedream

# Load .env from project root
env_path = Path(__file__).parent.parent / '.env'
load_dotenv(env_path)

logger = logging.getLogger(__name__)

class PipedreamService:
    """Wrapper for Pipedream Connect SDK operations"""

    def __init__(self):
        self.project_id = os.getenv("PIPEDREAM_PROJECT_ID")
        self.project_environment = os.getenv("PIPEDREAM_PROJECT_ENVIRONMENT", "development")
        self.client_id = os.getenv("PIPEDREAM_CLIENT_ID")
        self.client_secret = os.getenv("PIPEDREAM_CLIENT_SECRET")

        # Initialize Pipedream Connect SDK - handles auth automatically
        self.client = Pipedream(
            client_id=self.client_id,
            client_secret=self.client_secret,
            project_id=self.project_id,
            project_environment=self.project_environment
        )

    def _fetch_message_details(self, external_user_id: str, account_id: str, message_id: str):
        """
        Fetch full details for a single Gmail message

        Args:
            external_user_id: The external user ID from your system
            account_id: The Pipedream account/provision ID (e.g., apn_xxx)
            message_id: Gmail message ID

        Returns:
            dict: Parsed email with subject, from, date
        """
        try:
            # Target Gmail API URL - SDK handles encoding and auth automatically
            target_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}"

            # Use SDK's proxy - handles auth and encoding automatically
            # SDK returns dict directly, not Response object
            message_data = self.client.proxy.get(
                target_url,
                external_user_id=external_user_id,
                account_id=account_id
            )

            # Parse headers to extract subject, from, date
            headers_list = message_data.get('payload', {}).get('headers', [])

            email_details = {
                "id": message_id,
                "subject": None,
                "from": None,
                "date": None
            }

            for header in headers_list:
                name = header.get('name', '').lower()
                value = header.get('value', '')

                if name == 'subject':
                    email_details['subject'] = value
                elif name == 'from':
                    email_details['from'] = value
                elif name == 'date':
                    email_details['date'] = value

            return email_details

        except Exception as e:
            print(f"Error fetching message {message_id}: {str(e)}")
            return {
                "id": message_id,
                "subject": "(Error loading)",
                "from": "(Error loading)",
                "date": None
            }

    def _decode_gmail_body(self, data: str) -> str:
        """Decode URL-safe base64 Gmail body data"""
        # Add padding if needed (Gmail sometimes omits it)
        return base64.urlsafe_b64decode(data + '===').decode('utf-8', errors='ignore')

    def _extract_plain_text_body(self, message: dict) -> Optional[str]:
        """Extract plain text from Gmail message payload"""
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

    def fetch_gmail_message_body(
        self,
        message_id: str,
        external_user_id: str,
        account_id: str
    ) -> Optional[str]:
        """
        Fetch full Gmail message body via Pipedream Connect API proxy.

        Returns plain text body or None if unavailable.
        """
        # Use format=full to get complete message with body
        target_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}?format=full"

        try:
            # SDK returns dict directly, not Response object
            message_data = self.client.proxy.get(
                target_url,
                external_user_id=external_user_id,
                account_id=account_id
            )
            return self._extract_plain_text_body(message_data)
        except Exception as e:
            print(f"Failed to fetch body for message {message_id}: {e}")
            return None

    def fetch_gmail_messages(self, external_user_id: str, account_id: str, max_results: int = 10):
        """
        Fetch Gmail messages with full details using Pipedream Connect Proxy

        Args:
            external_user_id: The external user ID from your system
            account_id: The Pipedream account/provision ID (e.g., apn_xxx)
            max_results: Maximum number of messages to fetch

        Returns:
            list: Array of email objects with subject, from, date
        """
        try:
            # Step 1: Get list of message IDs
            target_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults={max_results}"

            print(f"Fetching message list from Gmail API...")
            # SDK returns dict directly, not Response object
            result = self.client.proxy.get(
                target_url,
                external_user_id=external_user_id,
                account_id=account_id
            )
            messages = result.get('messages', [])

            print(f"Found {len(messages)} messages, fetching details for first {max_results}...")

            # Step 2: Fetch full details for each message (limit to max_results)
            detailed_emails = []
            for message in messages[:max_results]:
                message_id = message['id']
                email_details = self._fetch_message_details(external_user_id, account_id, message_id)
                detailed_emails.append(email_details)
                print(f"  - Fetched: {email_details.get('subject', '(No subject)')}")

            print(f"Successfully fetched {len(detailed_emails)} emails with full details")
            return detailed_emails

        except requests.exceptions.HTTPError as e:
            print(f"HTTP Error fetching Gmail messages: {e}")
            print(f"Response: {e.response.text if e.response else 'No response'}")
            raise
        except Exception as e:
            print(f"Error fetching Gmail messages: {str(e)}")
            raise

    def fetch_gmail_messages_paginated(
        self,
        external_user_id: str,
        account_id: str,
        after_timestamp: int,
        max_results: int = 100,
        page_token: Optional[str] = None
    ) -> dict:
        """
        Fetch Gmail messages list with pagination.

        Args:
            external_user_id: User's Supabase ID
            account_id: Pipedream account ID (e.g., apn_xxx)
            after_timestamp: Unix timestamp - fetch emails after this time
            max_results: Messages per page (max 100)
            page_token: Pagination token from previous response

        Returns:
            dict: {"messages": [...], "nextPageToken": "...", "historyId": "..."}
        """
        # Build Gmail API URL with query
        target_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages?maxResults={max_results}&q=after:{after_timestamp}"
        if page_token:
            target_url += f"&pageToken={page_token}"

        try:
            logger.info(f"🔍 Calling Pipedream proxy with external_user_id={external_user_id}, account_id={account_id}")
            # SDK returns dict directly, not Response object
            result = self.client.proxy.get(
                target_url,
                external_user_id=external_user_id,
                account_id=account_id
            )
            logger.info(f"✅ Pipedream proxy call successful")
            return result
        except Exception as e:
            logger.error(f"❌ Pipedream proxy call failed: {e}")
            print(f"Error fetching paginated Gmail messages: {e}")
            raise

    def fetch_gmail_message_full(
        self,
        external_user_id: str,
        account_id: str,
        message_id: str
    ) -> dict:
        """
        Fetch specific Gmail message with full content.

        Args:
            external_user_id: User's Supabase ID
            account_id: Pipedream account ID
            message_id: Gmail message ID

        Returns:
            dict: Full Gmail message object with payload, headers, body
        """
        # Use format=full to get complete message
        target_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}?format=full"

        try:
            # SDK returns dict directly, not Response object
            return self.client.proxy.get(
                target_url,
                external_user_id=external_user_id,
                account_id=account_id
            )
        except Exception as e:
            print(f"Error fetching full message {message_id}: {e}")
            raise


# Singleton instance
pipedream_service = PipedreamService()
