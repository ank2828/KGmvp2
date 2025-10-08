"""
Process emails endpoint - accepts emails from frontend and processes through Graphiti
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
from datetime import datetime, timezone

from services.graphiti_service import GraphitiService
from services.entity_normalizer import EntityNormalizer
from services.entity_types import ENTITY_TYPES, EXCLUDED_ENTITY_TYPES
from graphiti_core.nodes import EpisodeType
from routes.gmail import sanitize_for_falkordb, sanitize_user_id_for_graphiti

router = APIRouter()


class Email(BaseModel):
    """Single email data"""
    id: Optional[str] = None
    subject: str
    from_: str  # Use from_ to avoid Python keyword
    to: str
    date: str
    body: str


class EmailBatch(BaseModel):
    """Batch of emails to process"""
    user_id: str
    emails: List[Email]


@router.post("/process-emails")
async def process_emails(batch: EmailBatch):
    """
    Accept emails from frontend, process through Graphiti, normalize to FalkorDB

    Args:
        batch: EmailBatch with user_id and list of emails

    Returns:
        Processing statistics including emails processed and entities created
    """

    print(f"📧 Processing {len(batch.emails)} emails for user {batch.user_id[:8]}...")

    # Sanitize user_id for Graphiti (avoid RediSearch special characters)
    sanitized_user_id = sanitize_user_id_for_graphiti(batch.user_id)

    # Initialize Graphiti
    graphiti = GraphitiService()
    await graphiti.initialize()

    try:
        # Process each email through Graphiti
        for idx, email in enumerate(batch.emails, 1):
            print(f"  [{idx}/{len(batch.emails)}] Processing: {email.subject[:50]}")

            # Create episode text with sanitization
            episode_text = f"""
Subject: {sanitize_for_falkordb(email.subject)}
From: {sanitize_for_falkordb(email.from_)}
To: {sanitize_for_falkordb(email.to)}
Date: {email.date}

{sanitize_for_falkordb(email.body[:2000])}
            """.strip()

            # Add to Graphiti (extracts entities)
            result = await graphiti.graphiti.add_episode(
                name=sanitize_for_falkordb(f"email_{email.id or idx}"),
                episode_body=episode_text,
                source_description=sanitize_for_falkordb(f"Gmail email from {email.from_}"),
                reference_time=datetime.now(timezone.utc),
                group_id=sanitized_user_id,
                source=EpisodeType.text,
                entity_types=ENTITY_TYPES,
                excluded_entity_types=EXCLUDED_ENTITY_TYPES
            )

            print(f"    ✓ Extracted entities with Graphiti")

            # Normalize entities immediately after each email
            normalizer = EntityNormalizer(driver=graphiti.driver, source='gmail')
            normalized_counts = await normalizer.normalize_and_persist(
                graphiti_result=result,
                group_id=sanitized_user_id
            )

            print(f"    ✓ Normalized: {normalized_counts}")

        print(f"\n✅ Successfully processed {len(batch.emails)} emails")

        return {
            'status': 'success',
            'emails_processed': len(batch.emails),
            'message': f'Processed {len(batch.emails)} emails through Graphiti'
        }

    except Exception as e:
        print(f"❌ Error processing emails: {e}")
        raise HTTPException(status_code=500, detail=str(e))

    finally:
        # Always cleanup
        await graphiti.close()
