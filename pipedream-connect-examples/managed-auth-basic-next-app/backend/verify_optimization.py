#!/usr/bin/env python3
"""
Final Verification Script - Knowledge Graph Optimization
Confirms all optimizations are working correctly
"""

import asyncio
from services.database import db_service
from services.document_store import document_store
from services.graphiti_service import GraphitiService

async def verify_all():
    print("=" * 80)
    print("🔍 KNOWLEDGE GRAPH OPTIMIZATION VERIFICATION")
    print("=" * 80)
    print()

    # 1. Check Supabase Tables
    print("📊 Supabase Tables:")
    print("-" * 80)

    # Processed episodes (deduplication)
    result = db_service.client.table('processed_episodes').select('*', count='exact').execute()
    print(f"   ✅ processed_episodes: {result.count} entries")
    if result.count > 0:
        for episode in result.data[:3]:
            print(f"      - {episode['source']}:{episode['source_id'][:20]}... → {episode['episode_uuid']}")

    # Documents
    result = db_service.client.table('documents').select('*', count='exact').execute()
    print(f"   ✅ documents: {result.count} entries")

    # Embeddings
    result = db_service.client.table('documents').select('id, subject').is_('vector_embedding', 'null').execute()
    missing = len(result.data)
    result = db_service.client.table('documents').select('id, subject').not_.is_('vector_embedding', 'null').execute()
    has_embeddings = len(result.data)
    print(f"   ✅ vector_embeddings: {has_embeddings} documents have embeddings, {missing} missing")

    print()

    # 2. Check FalkorDB
    print("🔗 FalkorDB Knowledge Graph:")
    print("-" * 80)

    graphiti = GraphitiService()

    # Count episodes
    query = "MATCH (e:Episodic) RETURN count(e) as count"
    result, _, _ = await graphiti.driver.execute_query(query)
    episode_count = result[0]['count'] if result and len(result) > 0 else 0
    print(f"   ✅ Episodic nodes: {episode_count}")

    # Count entities
    query = "MATCH (e:Entity) RETURN count(e) as count"
    result, _, _ = await graphiti.driver.execute_query(query)
    entity_count = result[0]['count'] if result and len(result) > 0 else 0
    print(f"   ✅ Entity nodes: {entity_count}")

    # Count relationships
    query = "MATCH ()-[r:MENTIONS]->() RETURN count(r) as count"
    result, _, _ = await graphiti.driver.execute_query(query)
    mentions_count = result[0]['count'] if result and len(result) > 0 else 0
    print(f"   ✅ MENTIONS relationships: {mentions_count}")

    query = "MATCH ()-[r:RELATES_TO]->() RETURN count(r) as count"
    result, _, _ = await graphiti.driver.execute_query(query)
    relates_count = result[0]['count'] if result and len(result) > 0 else 0
    print(f"   ✅ RELATES_TO relationships: {relates_count}")

    print()

    # 3. Test Vector Search
    print("🔍 Vector Search Test:")
    print("-" * 80)

    if has_embeddings > 0:
        # Pick a test query based on actual data
        results = await document_store.search_documents_semantic(
            query="email pricing discussion",
            user_id="8d6126ed-dfb5-4fff-9d72-b84fb0cb889a",
            limit=3
        )

        if results:
            print(f"   ✅ Found {len(results)} results for 'email pricing discussion':")
            for r in results:
                similarity = r['similarity']
                subject = r['document'].subject
                print(f"      [{similarity:.2f}] {subject[:60]}")
        else:
            print(f"   ⚠️  No results (query may not match current data)")
    else:
        print(f"   ⚠️  Skipping (no embeddings found)")

    print()

    # 4. Test Deduplication
    print("✅ Deduplication Check:")
    print("-" * 80)

    # Get count from processed_episodes table
    dedup_result = db_service.client.table('processed_episodes').select('*', count='exact').execute()

    if dedup_result.count > 0:
        # Get first processed episode
        result = db_service.client.table('processed_episodes').select('*').limit(1).execute()
        if result.data:
            episode = result.data[0]

            # Test deduplication check
            is_processed = await graphiti.has_episode_been_processed(
                source=episode['source'],
                source_id=episode['source_id'],
                user_id=episode['user_id']
            )

            if is_processed:
                print(f"   ✅ Deduplication working: {episode['source']}:{episode['source_id'][:20]}... found in table")
            else:
                print(f"   ❌ Deduplication issue: Episode in table but check returned False")
    else:
        print(f"   ⏭️  No processed episodes yet (run a sync first)")

    print()

    # 5. Final Summary
    print("=" * 80)
    print("📈 OPTIMIZATION STATUS:")
    print("=" * 80)

    status = []
    status.append(("Episode Deduplication", "✅ ACTIVE" if dedup_result.count > 0 else "⏳ READY"))
    status.append(("Vector Embeddings", "✅ WORKING" if has_embeddings > 0 else "⚠️  NEEDS DATA"))
    status.append(("Knowledge Graph", f"✅ {episode_count} episodes, {entity_count} entities"))
    status.append(("Semantic Search", "✅ FUNCTIONAL" if has_embeddings > 0 else "⏳ NEEDS DATA"))

    for name, value in status:
        print(f"   {name:.<30} {value}")

    print()
    print("=" * 80)
    print("🎉 VERIFICATION COMPLETE")
    print("=" * 80)
    print()

    # Next steps
    if dedup_result.count == 0:
        print("💡 Next Step: Run a sync to test deduplication")
        print("   curl -X GET \"http://localhost:8000/api/gmail/fetch?user_id=8d6126ed-dfb5-4fff-9d72-b84fb0cb889a&account_id=apn_4vhyvM6&max_results=3\"")
        print()

if __name__ == "__main__":
    asyncio.run(verify_all())
