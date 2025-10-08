#!/usr/bin/env python3
"""
Standalone email sync script - bypasses Celery/database

Usage:
    python run_sync.py --days 14
"""
import argparse
import asyncio
from datetime import datetime, timedelta, timezone
from services.pipedream import pipedream_service
from services.graphiti_service import GraphitiService
from graphiti_core.nodes import EpisodeType
from routes.gmail import (
    sanitize_user_id_for_graphiti,
    group_emails_by_date,
    sanitize_for_falkordb,
)

async def main():
    parser = argparse.ArgumentParser(description='Sync Gmail emails to Graphiti')
    parser.add_argument('--days', type=int, default=14, help='Number of days to sync')
    args = parser.parse_args()

    # Hardcoded working credentials
    USER_ID = '7ab7b70c-889a-46b4-b6af-25ab1dfe4608'
    ACCOUNT_ID = 'apn_QPh347g'

    print(f"🚀 Starting {args.days}-day Gmail sync...")
    print(f"Account: {ACCOUNT_ID}")
    print(f"User: {USER_ID}")
    print("")

    # Initialize Graphiti
    print("Initializing Graphiti...")
    graphiti = GraphitiService()
    await graphiti.initialize()
    print("✅ Graphiti ready")
    print("")

    # Calculate timestamp
    after_date = datetime.now(timezone.utc) - timedelta(days=args.days)
    after_timestamp = int(after_date.timestamp())

    # Fetch emails
    print(f"📥 Fetching messages after {after_date.strftime('%Y-%m-%d')}...")
    all_messages = []
    page_token = None
    page_num = 1

    while True:
        result = pipedream_service.fetch_gmail_messages_paginated(
            external_user_id=USER_ID,
            account_id=ACCOUNT_ID,
            after_timestamp=after_timestamp,
            max_results=100,
            page_token=page_token
        )

        messages = result.get('messages', [])
        all_messages.extend(messages)
        print(f"  Page {page_num}: {len(messages)} messages")

        page_token = result.get('nextPageToken')
        if not page_token:
            break
        page_num += 1

    print(f"✅ Found {len(all_messages)} total messages")
    print("")

    # Process each message
    print("📧 Processing emails...")
    for idx, msg in enumerate(all_messages, 1):
        message_id = msg['id']
        print(f"  [{idx}/{len(all_messages)}] Fetching message {message_id[:12]}...")

        try:
            full_msg = pipedream_service.fetch_gmail_message_full(
                external_user_id=USER_ID,
                account_id=ACCOUNT_ID,
                message_id=message_id
            )

            # Extract headers
            headers = full_msg.get('payload', {}).get('headers', [])
            email_meta = {}
            for h in headers:
                name = h.get('name', '').lower()
                if name in ['from', 'to', 'subject', 'date']:
                    email_meta[name] = h.get('value', '')

            # Extract body
            body = pipedream_service._extract_plain_text_body(full_msg) or "(no body)"

            # Build episode content
            content = f"""
From: {email_meta.get('from', 'Unknown')}
To: {email_meta.get('to', 'Unknown')}
Subject: {email_meta.get('subject', 'No Subject')}
Date: {email_meta.get('date', 'Unknown')}

{body[:500]}{'...' if len(body) > 500 else ''}
""".strip()

            content = sanitize_for_falkordb(content)

            # Add to Graphiti
            sanitized_user_id = sanitize_user_id_for_graphiti(USER_ID)
            await graphiti.graphiti.add_episode(
                name=f"Email: {email_meta.get('subject', 'No Subject')[:50]}",
                episode_body=content,
                source=EpisodeType.text,
                source_description=f"Gmail message {message_id}",
                reference_time=datetime.now(timezone.utc),
                group_id=sanitized_user_id
            )

            print(f"    ✅ Added: {email_meta.get('subject', 'No Subject')[:60]}")

        except Exception as e:
            print(f"    ❌ Error: {str(e)[:100]}")

    await graphiti.close()
    print("")
    print("=" * 60)
    print(f"✅ SYNC COMPLETE: Processed {len(all_messages)} emails")
    print("=" * 60)

if __name__ == '__main__':
    asyncio.run(main())
