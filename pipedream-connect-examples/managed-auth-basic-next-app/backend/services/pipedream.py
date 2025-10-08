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

    def _fetch_message_details(self, external_user_id: str, message_id: str):
        """
        Fetch full details for a single Gmail message using Pipedream Actions API

        Args:
            external_user_id: The external user ID from your system
            message_id: Gmail message ID

        Returns:
            dict: Parsed email with subject, from, date
        """
        try:
            # Use Actions API to fetch message
            # NOTE: Only pass external_user_id, NOT account_id (causes "account and user mismatch")
            result = self.client.actions.run(
                id='gmail-get-message',
                external_user_id=external_user_id,
                configured_props={
                    'id': message_id
                }
            )

            # Extract actual response from Pipedream wrapper
            if isinstance(result, dict):
                message_data = result.get('ret') or result.get('data') or result
            else:
                message_data = result

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
        Fetch full Gmail message body using Pipedream Proxy API (direct Gmail access).

        Returns plain text body or None if unavailable.
        """
        try:
            # Use Proxy API for direct Gmail access
            # Correct signature: url first, then external_user_id, then account_id
            result = self.client.proxy.get(
                f'https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}',
                external_user_id=external_user_id,
                account_id=account_id,
                params={'format': 'full'}
            )

            # Unwrap Pydantic response if needed
            if hasattr(result, 'model_dump'):
                message_data = result.model_dump()
            elif isinstance(result, dict):
                message_data = result
            else:
                message_data = result

            return self._extract_plain_text_body(message_data)
        except Exception as e:
            print(f"Failed to fetch body for message {message_id}: {e}")
            return None

    def fetch_gmail_messages(self, external_user_id: str, account_id: str, max_results: int = 10):
        """
        Fetch Gmail messages with full details using Pipedream Proxy API (direct Gmail API access)

        Args:
            external_user_id: The external user ID from your system
            account_id: Pipedream account ID (e.g., apn_xxx)
            max_results: Maximum number of messages to fetch

        Returns:
            list: Array of email objects with subject, from, date
        """
        try:
            # Step 1: Get list of message IDs using Proxy API (direct Gmail API)
            print(f"Fetching message list from Gmail API via Proxy...")

            # Correct signature: url first, then external_user_id, then account_id
            result = self.client.proxy.get(
                'https://gmail.googleapis.com/gmail/v1/users/me/messages',
                external_user_id=external_user_id,
                account_id=account_id,
                params={
                    'maxResults': max_results,
                    'q': 'in:inbox'  # Simple query for inbox
                }
            )

            # Proxy API returns direct Gmail API response
            # Unwrap Pydantic response if needed
            if hasattr(result, 'model_dump'):
                result = result.model_dump()

            messages = result.get('messages', [])
            print(f"Found {len(messages)} messages, fetching details for first {max_results}...")

            # Step 2: Fetch full details for each message
            detailed_emails = []
            for message in messages[:max_results]:
                message_id = message['id']

                # Fetch full message details via Proxy API
                # Correct signature: url first, then external_user_id, then account_id
                msg_result = self.client.proxy.get(
                    f'https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}',
                    external_user_id=external_user_id,
                    account_id=account_id,
                    params={'format': 'full'}
                )

                # Unwrap Pydantic response
                if hasattr(msg_result, 'model_dump'):
                    msg_result = msg_result.model_dump()

                # Parse headers to extract subject, from, date
                headers_list = msg_result.get('payload', {}).get('headers', [])
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

                detailed_emails.append(email_details)
                print(f"  - Fetched: {email_details.get('subject', '(No subject)')}")

            print(f"Successfully fetched {len(detailed_emails)} emails with full details")
            return detailed_emails

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
        Fetch Gmail messages list with pagination using Pipedream Actions API.

        Args:
            external_user_id: User's Supabase ID
            account_id: Pipedream account ID (e.g., apn_xxx)
            after_timestamp: Unix timestamp - fetch emails after this time
            max_results: Messages per page (max 100)
            page_token: Pagination token from previous response

        Returns:
            dict: {"messages": [...], "nextPageToken": "...", "historyId": "..."}
        """
        try:
            logger.info(f"🔍 Calling Pipedream Proxy API with external_user_id={external_user_id}, account_id={account_id}")

            # Build query - fetch emails from inbox and sent
            query = f"(in:inbox OR in:sent) after:{after_timestamp}"

            # Build Gmail API params
            params = {
                'q': query,
                'maxResults': max_results
            }

            # Add page token if provided
            if page_token:
                params['pageToken'] = page_token

            # Use Proxy API - it's designed for Connect's managed auth
            # Correct signature: url first, then external_user_id, then account_id
            result = self.client.proxy.get(
                'https://gmail.googleapis.com/gmail/v1/users/me/messages',
                external_user_id=external_user_id,
                account_id=account_id,
                params=params
            )

            logger.info(f"✅ Pipedream actions API call successful")
            logger.info(f"Raw response type: {type(result)}")

            # Extract actual Gmail API response from Pipedream wrapper
            # The Actions API returns a RunActionResponse Pydantic object
            # Try different attributes to find the Gmail data
            if hasattr(result, 'exports') and result.exports:
                logger.info(f"Found 'exports' attribute, type: {type(result.exports)}, value: {result.exports}")
                actual_result = result.exports
            elif hasattr(result, 'ret') and result.ret is not None:
                logger.info(f"Found 'ret' attribute, type: {type(result.ret)}")
                actual_result = result.ret
            elif hasattr(result, 'data') and result.data is not None:
                logger.info(f"Found 'data' attribute, type: {type(result.data)}")
                actual_result = result.data
            elif isinstance(result, dict):
                logger.info("Result is dict, unwrapping...")
                actual_result = result.get('ret') or result.get('data') or result
            else:
                logger.info("Converting Pydantic model to dict...")
                # If it's a Pydantic model, convert to dict
                actual_result = result.model_dump() if hasattr(result, 'model_dump') else result

            logger.info(f"Unwrapped response type: {type(actual_result)}")
            logger.info(f"Unwrapped response value: {str(actual_result)[:200] if actual_result else 'None'}")
            return actual_result
        except Exception as e:
            logger.error(f"❌ Pipedream actions API call failed: {e}")
            print(f"Error fetching paginated Gmail messages: {e}")
            raise

    def fetch_gmail_message_full(
        self,
        external_user_id: str,
        account_id: str,
        message_id: str
    ) -> dict:
        """
        Fetch specific Gmail message with full content using Pipedream Actions API.

        Args:
            external_user_id: User's Supabase ID
            account_id: Pipedream account ID
            message_id: Gmail message ID

        Returns:
            dict: Full Gmail message object with payload, headers, body
        """
        try:
            # Use Proxy API to fetch message directly from Gmail
            # Correct signature: url first, then external_user_id, then account_id
            result = self.client.proxy.get(
                f'https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}',
                external_user_id=external_user_id,
                account_id=account_id,
                params={'format': 'full'}
            )

            logger.debug(f"Raw response type: {type(result)}")

            # Extract actual Gmail API response from Pipedream wrapper
            # The Actions API returns a RunActionResponse Pydantic object
            if hasattr(result, 'ret'):
                actual_result = result.ret
            elif hasattr(result, 'data'):
                actual_result = result.data
            elif isinstance(result, dict):
                actual_result = result.get('ret') or result.get('data') or result
            else:
                # If it's a Pydantic model, convert to dict
                actual_result = result.model_dump() if hasattr(result, 'model_dump') else result

            return actual_result
        except Exception as e:
            print(f"Error fetching full message {message_id}: {e}")
            raise


# Singleton instance
pipedream_service = PipedreamService()
