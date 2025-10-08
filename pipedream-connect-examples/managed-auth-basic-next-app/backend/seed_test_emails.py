#!/usr/bin/env python3
"""
Seed Test Emails for Phase 1 Testing

Creates realistic test emails in Supabase to verify:
1. Document storage with embeddings
2. Entity linking
3. Hybrid AI agent with citations
"""

import asyncio
from datetime import datetime, timedelta, timezone

from services.document_store import document_store
from services.database import db_service


async def seed_test_emails():
    print("=" * 80)
    print("SEEDING TEST EMAILS FOR PHASE 1")
    print("=" * 80)

    user_id = "8d6126ed-dfb5-4fff-9d72-b84fb0cb889a"  # Your actual user ID

    # Test emails with realistic CRM data
    test_emails = [
        {
            'id': 'test_acme_001',
            'subject': 'RE: Q4 Enterprise License - Pricing Discussion',
            'body': '''Hi team,

I had a great call with Sarah Johnson from Acme Corp yesterday. They're very interested in our enterprise license for Q4 2025.

Key points from the discussion:
- Budget approved: $150K for annual license
- Need multi-tenant support for 500 users
- Want to start pilot in November 2025
- Decision maker: John Smith (VP Engineering)
- Competitive eval against DataBricks and Snowflake

Sarah mentioned they're also evaluating our competitors but we're the frontrunner due to our superior API documentation.

Next steps:
1. Send proposal by Friday
2. Schedule demo with their engineering team
3. Prepare custom pricing for 500-seat license

Let me know if you need anything else.

Best,
Alex''',
            'from': 'sarah.johnson@acme-corp.com',
            'to': 'sales@company.com',
            'date': (datetime.now(timezone.utc) - timedelta(days=2)).strftime('%a, %d %b %Y %H:%M:%S %z'),
            'thread_id': 'thread_acme_001'
        },
        {
            'id': 'test_techflow_001',
            'subject': 'TechFlow Partnership - Follow-up',
            'body': '''Hi Alex,

Following up on our conversation from last week. Mike Chen at TechFlow Solutions confirmed they want to proceed with the integration partnership.

Details:
- Company: TechFlow Solutions
- Contact: Mike Chen (CTO)
- Deal size: $75K integration fee + $25K/year maintenance
- Timeline: Kick off in December 2025
- Integration scope: REST API + Webhook events
- Their tech stack: Python, PostgreSQL, React

Mike mentioned they're also talking to Segment and Zapier, but they prefer our real-time event architecture.

I'm scheduling a technical deep-dive for next Tuesday. Can you join?

Thanks,
Emily''',
            'from': 'mike.chen@techflow.io',
            'to': 'partnerships@company.com',
            'date': (datetime.now(timezone.utc) - timedelta(days=5)).strftime('%a, %d %b %Y %H:%M:%S %z'),
            'thread_id': 'thread_techflow_001'
        },
        {
            'id': 'test_globex_001',
            'subject': 'Globex Corp - Customer Success Check-in',
            'body': '''Hi Sarah,

Quick check-in on Globex Corp (our largest customer). I spoke with Lisa Rodriguez, their Head of Data, this morning.

Current status:
- Company: Globex Corp
- Contact: Lisa Rodriguez (Head of Data)
- ARR: $500K (renewed last month)
- Health score: 9/10 (excellent)
- Usage: 450 active users out of 500 license limit
- Recent activity: Deployed to 3 new departments

Lisa mentioned they'll need to expand to a 1000-user license by Q1 2026 as they're rolling out to their European offices.

Action items:
- Upsell conversation scheduled for Jan 15, 2026
- Send them our new feature roadmap
- Invite Lisa to our customer advisory board

Overall - very healthy account. No churn risk.

Best,
David''',
            'from': 'lisa.rodriguez@globex-corp.com',
            'to': 'support@company.com',
            'date': (datetime.now(timezone.utc) - timedelta(days=1)).strftime('%a, %d %b %Y %H:%M:%S %z'),
            'thread_id': 'thread_globex_001'
        },
        {
            'id': 'test_initech_001',
            'subject': 'Initech - Trial Conversion Opportunity',
            'body': '''Team,

We have a hot lead! Initech just finished their 14-day trial and wants to convert to paid.

Contact info:
- Company: Initech
- Contact: Peter Gibbons (Engineering Manager)
- Email: peter@initech.com
- Trial usage: Very engaged - 15 team members active daily
- Use case: Data pipeline automation

Peter said their biggest pain point is manual data transformations taking 20 hours/week. Our automation saved them 15 hours in the trial alone.

Pricing discussion:
- They want 25 seats
- Budget: ~$30K annually
- Start date: ASAP (they're in a crunch)

Competitors: None - we're their first choice

I'm sending contract today. Hoping to close by end of week!

Let's go!
Rachel''',
            'from': 'peter.gibbons@initech.com',
            'to': 'trials@company.com',
            'date': (datetime.now(timezone.utc) - timedelta(hours=6)).strftime('%a, %d %b %Y %H:%M:%S %z'),
            'thread_id': 'thread_initech_001'
        }
    ]

    print(f"\n📧 Storing {len(test_emails)} test emails in Supabase...")

    # Store all emails with embeddings
    document_ids = await document_store.store_emails_batch(user_id, test_emails)

    print(f"✅ Stored {len(document_ids)} emails with vector embeddings")

    # Link to fake entities (simulating what Graphiti would extract)
    print(f"\n🔗 Linking documents to extracted entities...")

    # Email 1: Acme Corp entities
    await document_store.link_document_to_entity(
        document_id=document_ids[0],
        entity_uuid='entity_acme_corp',
        entity_type='Company',
        entity_name='Acme Corp',
        mention_count=3,
        relevance_score=0.95
    )
    await document_store.link_document_to_entity(
        document_id=document_ids[0],
        entity_uuid='entity_sarah_johnson',
        entity_type='Contact',
        entity_name='Sarah Johnson',
        mention_count=2,
        relevance_score=0.90
    )
    await document_store.link_document_to_entity(
        document_id=document_ids[0],
        entity_uuid='entity_john_smith',
        entity_type='Contact',
        entity_name='John Smith',
        mention_count=1,
        relevance_score=0.85
    )

    # Email 2: TechFlow entities
    await document_store.link_document_to_entity(
        document_id=document_ids[1],
        entity_uuid='entity_techflow',
        entity_type='Company',
        entity_name='TechFlow Solutions',
        mention_count=2,
        relevance_score=0.92
    )
    await document_store.link_document_to_entity(
        document_id=document_ids[1],
        entity_uuid='entity_mike_chen',
        entity_type='Contact',
        entity_name='Mike Chen',
        mention_count=2,
        relevance_score=0.88
    )

    # Email 3: Globex entities
    await document_store.link_document_to_entity(
        document_id=document_ids[2],
        entity_uuid='entity_globex',
        entity_type='Company',
        entity_name='Globex Corp',
        mention_count=3,
        relevance_score=0.93
    )
    await document_store.link_document_to_entity(
        document_id=document_ids[2],
        entity_uuid='entity_lisa_rodriguez',
        entity_type='Contact',
        entity_name='Lisa Rodriguez',
        mention_count=2,
        relevance_score=0.91
    )

    # Email 4: Initech entities
    await document_store.link_document_to_entity(
        document_id=document_ids[3],
        entity_uuid='entity_initech',
        entity_type='Company',
        entity_name='Initech',
        mention_count=2,
        relevance_score=0.87
    )
    await document_store.link_document_to_entity(
        document_id=document_ids[3],
        entity_uuid='entity_peter_gibbons',
        entity_type='Contact',
        entity_name='Peter Gibbons',
        mention_count=2,
        relevance_score=0.86
    )

    print(f"✅ Created 9 entity links")

    # Verify storage
    print(f"\n📊 Verification:")
    docs = await document_store.get_documents_for_entities(['entity_acme_corp'])
    print(f"   Documents for 'Acme Corp': {len(docs)}")

    search_results = await document_store.search_documents_semantic(
        query='enterprise pricing discussion',
        user_id=user_id,
        limit=3
    )
    print(f"   Semantic search results: {len(search_results)}")

    print("\n" + "=" * 80)
    print("✅ SEEDING COMPLETE!")
    print("=" * 80)
    print("\nYou can now test the AI agent with queries like:")
    print("- 'What did Sarah email me about?'")
    print("- 'Tell me about Acme Corp'")
    print("- 'What deals are in progress?'")
    print("- 'Who is Mike Chen?'")
    print("- 'Show me enterprise pricing discussions'")
    print("=" * 80)


if __name__ == '__main__':
    asyncio.run(seed_test_emails())
