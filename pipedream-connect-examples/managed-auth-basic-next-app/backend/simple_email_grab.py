"""
Simple script to grab emails and load them into FalkorDB
No syncing, no background tasks, just a one-time data load
"""

import asyncio
from pipedream import Pipedream
from services.graphiti_service import GraphitiService
from services.entity_normalizer import EntityNormalizer
from services.entity_types import ENTITY_TYPES, EXCLUDED_ENTITY_TYPES
from services.database import db_service
from config import settings
import base64
from datetime import datetime, timezone
import sys

# Your user ID - we'll get account from database
USER_ID = "8d6126ed-dfb5-4fff-9d72-b84fb0cb889a"

async def grab_emails(pd, external_user_id: str, account_id: str, num_emails: int = 10):
    """Grab N most recent emails"""

    # Step 1: Get message IDs
    print(f"📧 Fetching {num_emails} most recent emails...")
    url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages"

    response = pd.proxy.get(
        url=url,
        external_user_id=external_user_id,
        account_id=account_id,
        params={'maxResults': num_emails}
    )

    message_ids = response.get('messages', [])
    print(f"✅ Found {len(message_ids)} messages")

    # Step 2: Get full content for each
    emails = []
    for msg in message_ids:
        msg_id = msg['id']

        detail_url = f"https://gmail.googleapis.com/gmail/v1/users/me/messages/{msg_id}"
        full_msg = pd.proxy.get(
            url=detail_url,
            external_user_id=external_user_id,
            account_id=account_id,
            params={'format': 'full'}
        )

        # Extract headers
        headers = {
            h['name']: h['value']
            for h in full_msg.get('payload', {}).get('headers', [])
        }

        # Extract body
        body = extract_body(full_msg)

        emails.append({
            'id': msg_id,
            'subject': headers.get('Subject', 'No Subject'),
            'from': headers.get('From', ''),
            'to': headers.get('To', ''),
            'date': headers.get('Date', ''),
            'body': body
        })

        print(f"  ✓ {headers.get('Subject', 'No Subject')[:50]}")

    return emails

def extract_body(message):
    """Extract plain text from Gmail message"""
    payload = message.get('payload', {})

    # Try direct body
    if 'body' in payload and payload['body'].get('data'):
        try:
            return base64.urlsafe_b64decode(payload['body']['data'] + '===').decode('utf-8', errors='ignore')
        except:
            pass

    # Try parts
    for part in payload.get('parts', []):
        if part.get('mimeType') == 'text/plain' and part.get('body', {}).get('data'):
            try:
                return base64.urlsafe_b64decode(part['body']['data'] + '===').decode('utf-8', errors='ignore')
            except:
                continue

    return ""

async def load_to_falkordb(emails, user_id: str):
    """Process emails through Graphiti and normalize to FalkorDB"""

    print(f"\n🧠 Initializing Graphiti...")
    graphiti = GraphitiService()
    await graphiti.initialize()

    print(f"📝 Processing {len(emails)} emails...\n")

    for idx, email in enumerate(emails, 1):
        print(f"[{idx}/{len(emails)}] Processing: {email['subject'][:50]}")

        # Create episode text
        episode_text = f"""
Subject: {email['subject']}
From: {email['from']}
To: {email['to']}
Date: {email['date']}

{email['body'][:2000]}
        """.strip()

        # Add to Graphiti (extracts entities)
        from graphiti_core.nodes import EpisodeType

        result = await graphiti.graphiti.add_episode(
            name=f"email_{email['id']}",
            episode_body=episode_text,
            source_description=f"Gmail email from {email['from']}",
            reference_time=datetime.now(timezone.utc),
            group_id=user_id,
            source=EpisodeType.text,
            entity_types=ENTITY_TYPES,
            excluded_entity_types=EXCLUDED_ENTITY_TYPES
        )

        print(f"  ✓ Extracted entities with Graphiti")

        # Normalize entities immediately
        normalizer = EntityNormalizer(driver=graphiti.driver, source='gmail')
        normalized_counts = await normalizer.normalize_and_persist(
            graphiti_result=result,
            group_id=user_id
        )
        print(f"  ✓ Normalized: {normalized_counts}")

    await graphiti.close()

    print(f"\n✅ COMPLETE!")

async def main():
    """Main execution"""

    print("=" * 60)
    print("SIMPLE EMAIL GRAB → FalkorDB")
    print("=" * 60)

    # Get account from database
    print(f"🔍 Looking up Gmail account for user {USER_ID[:8]}...")
    account = db_service.get_user_account(USER_ID, app="gmail")

    if not account:
        print(f"❌ No Gmail account found for user {USER_ID}")
        print(f"   Please connect Gmail through the UI first.")
        sys.exit(1)

    external_user_id = account['external_user_id']
    account_id = account['account_id']

    print(f"✅ Found account: {account_id}")
    print(f"   External user ID: {external_user_id[:8]}...")

    print(f"\n🔌 Connecting to Pipedream...")
    pd = Pipedream(
        client_id=settings.pipedream_client_id,
        client_secret=settings.pipedream_client_secret,
        project_id=settings.pipedream_project_id,
        project_environment=settings.pipedream_project_environment
    )

    # Step 1: Grab emails
    emails = await grab_emails(pd, external_user_id, account_id, num_emails=10)  # Change this number as needed

    # Step 2: Load to FalkorDB
    await load_to_falkordb(emails, USER_ID)

    print("\n" + "=" * 60)
    print("🎉 Done! Check FalkorDB for your entities.")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())
