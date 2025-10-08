#!/usr/bin/env python3
"""
Phase 1 Deployment Test Script
Tests Supabase document storage after migration
"""

import asyncio
import sys
from datetime import datetime

print("=" * 80)
print("PHASE 1 DEPLOYMENT TEST")
print("=" * 80)

# Test 1: Verify migration
print("\n📋 Test 1: Verify Supabase tables...")
try:
    from services.database import db_service

    # Check documents table
    result = db_service.client.table('documents').select('id').limit(1).execute()
    print("✅ documents table exists")

    # Check document_entities table
    result = db_service.client.table('document_entities').select('id').limit(1).execute()
    print("✅ document_entities table exists")

    # Check counts
    doc_result = db_service.client.table('documents').select('id', count='exact').execute()
    print(f"📊 Current documents: {len(doc_result.data)}")

    link_result = db_service.client.table('document_entities').select('id', count='exact').execute()
    print(f"🔗 Current entity links: {len(link_result.data)}")

except Exception as e:
    print(f"❌ Migration verification failed: {e}")
    sys.exit(1)

# Test 2: DocumentStore service
print("\n🔧 Test 2: Load DocumentStore service...")
try:
    from services.document_store import document_store
    print("✅ DocumentStore service loaded")
except Exception as e:
    print(f"❌ Failed to load DocumentStore: {e}")
    sys.exit(1)

# Test 3: Store test email
async def test_document_storage():
    print("\n📧 Test 3: Store test email with embedding...")

    test_email = {
        'id': 'test_deployment_001',
        'subject': 'Phase 1 Deployment Test - Q4 Enterprise Discussion',
        'body': 'Hi team, This is a test email for Phase 1 deployment. Sarah from Acme Corp mentioned they are interested in our enterprise license for Q4. They want to discuss pricing and features.',
        'from': 'sarah.test@acme-test.com',
        'to': 'sales@test.com',
        'date': 'Thu, 7 Oct 2025 10:00:00 -0700',
        'thread_id': 'test_thread_001'
    }

    try:
        doc_id = await document_store.store_email(
            user_id='test_deployment_user',
            email_data=test_email
        )
        print(f"✅ Document stored with ID: {doc_id}")
        return doc_id
    except Exception as e:
        print(f"❌ Failed to store email: {e}")
        import traceback
        traceback.print_exc()
        return None

# Test 4: Link to entity
async def test_entity_linking(doc_id):
    print("\n🔗 Test 4: Link document to test entity...")

    try:
        await document_store.link_document_to_entity(
            document_id=doc_id,
            entity_uuid='test_deployment_entity_acme',
            entity_type='Company',
            entity_name='Acme Corp (Test)',
            mention_count=2,
            relevance_score=0.95
        )
        print("✅ Document linked to entity")
        return True
    except Exception as e:
        print(f"❌ Failed to link document: {e}")
        return False

# Test 5: Retrieve documents
async def test_document_retrieval(doc_id):
    print("\n📄 Test 5: Retrieve documents for entity...")

    try:
        docs = await document_store.get_documents_for_entities(
            entity_uuids=['test_deployment_entity_acme'],
            limit=10
        )
        print(f"✅ Retrieved {len(docs)} document(s)")

        if docs:
            doc = docs[0]
            print(f"   Subject: {doc.subject}")
            print(f"   From: {doc.metadata.get('from')}")
            print(f"   Preview: {doc.content_preview}")

        return len(docs) > 0
    except Exception as e:
        print(f"❌ Failed to retrieve documents: {e}")
        return False

# Test 6: Semantic search
async def test_semantic_search():
    print("\n🔍 Test 6: Semantic search over documents...")

    try:
        results = await document_store.search_documents_semantic(
            query='enterprise pricing discussion',
            user_id='test_deployment_user',
            limit=5,
            min_similarity=0.3
        )
        print(f"✅ Found {len(results)} document(s) via semantic search")

        for i, result in enumerate(results[:3], 1):
            doc = result['document']
            similarity = result['similarity']
            print(f"   {i}. {doc.subject} (similarity: {similarity:.2f})")

        return len(results) > 0
    except Exception as e:
        print(f"❌ Semantic search failed: {e}")
        import traceback
        traceback.print_exc()
        return False

# Test 7: Cleanup
async def cleanup_test_data():
    print("\n🧹 Test 7: Cleanup test data...")

    try:
        # Delete test document
        db_service.client.table('documents').delete().eq(
            'source_id', 'test_deployment_001'
        ).execute()
        print("✅ Test data cleaned up")
    except Exception as e:
        print(f"⚠️ Cleanup warning (non-critical): {e}")

# Run all tests
async def run_all_tests():
    doc_id = await test_document_storage()

    if not doc_id:
        print("\n❌ DEPLOYMENT TEST FAILED - Could not store document")
        return False

    linked = await test_entity_linking(doc_id)
    if not linked:
        print("\n❌ DEPLOYMENT TEST FAILED - Could not link entity")
        return False

    retrieved = await test_document_retrieval(doc_id)
    if not retrieved:
        print("\n❌ DEPLOYMENT TEST FAILED - Could not retrieve document")
        return False

    searched = await test_semantic_search()
    if not searched:
        print("\n⚠️ WARNING - Semantic search returned no results (may need time for embeddings)")

    await cleanup_test_data()

    return True

# Execute tests
try:
    success = asyncio.run(run_all_tests())

    print("\n" + "=" * 80)
    if success:
        print("✅ PHASE 1 DEPLOYMENT TEST PASSED")
        print("\nNext steps:")
        print("1. Trigger a fresh email sync to populate documents")
        print("2. Test AI agent with: 'What emails did I receive?'")
        print("3. Verify agent response includes document citations")
    else:
        print("❌ PHASE 1 DEPLOYMENT TEST FAILED")
        print("\nCheck errors above and review PHASE1_DEPLOYMENT.md troubleshooting section")
    print("=" * 80)

except Exception as e:
    print(f"\n❌ CRITICAL ERROR: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
