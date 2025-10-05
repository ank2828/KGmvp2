#!/usr/bin/env python3
"""
COMPREHENSIVE INTEGRATION TEST: Multi-Source Knowledge Graph Pipeline

Tests the complete architecture:
- Phase 1: Schema initialization
- Phase 2: Custom entity extraction (Gmail)
- Phase 3: Entity normalization
- Phase 4: Cross-source deduplication (HubSpot)
- Phase 5: AI agent query patterns

This validates your entire MVP foundation before production integration.

Run: python test_integration_normalization.py
"""

import asyncio
import re
from datetime import datetime, timezone
from services.graphiti_service import GraphitiService
from services.falkordb_schema import FalkorDBSchema
from services.entity_normalizer import EntityNormalizer
from services.entity_types import ENTITY_TYPES, EXCLUDED_ENTITY_TYPES
from graphiti_core.nodes import EpisodeType


def sanitize_for_falkordb(text: str) -> str:
    """Sanitize text to prevent RediSearch syntax errors"""
    # Replace special characters that break RediSearch
    text = text.replace('@', ' at ')
    text = text.replace('$', ' dollars ')
    text = text.replace(',', '')

    # Remove RediSearch operators
    for char in ['*', '(', ')', '{', '}', '[', ']', '^', '~', '|', ':', ';']:
        text = text.replace(char, ' ')

    # Clean up whitespace
    text = re.sub(r'\s+', ' ', text).strip()
    return text


# Test data: Same company across Gmail and HubSpot
GMAIL_EPISODE = """
From: sarah.johnson@acme.com
Subject: Q4 Enterprise License Discussion
Date: 2025-10-01

Hi team,

I'm Sarah Johnson, CFO at Acme Corporation. We're interested in your enterprise
license for our 500-person organization. Our domain is acme.com, and we're located
in San Francisco, CA.

We're looking at a $250,000 deal for the Q4 Enterprise Suite with Premium Support.
Currently in negotiation stage. My phone is +1 555-123-4567.

Looking forward to discussing pricing.

Best,
Sarah Johnson
CFO, Acme Corporation
"""

HUBSPOT_EPISODE = """
HUBSPOT CRM SYNC:

Company: Acme Corporation
Domain: acme.com
Industry: Enterprise Software
Employees: 500
Location: San Francisco, CA

Contact: Sarah Johnson
Title: Chief Financial Officer
Email: sarah.johnson@acme.com
Phone: +1 555-123-4567
Company: Acme Corporation

Deal: Q4 Enterprise License - Acme Corp
Amount: $250,000
Stage: Negotiation
Close Date: 2025-12-15
Products: Enterprise Suite, Premium Support
Primary Contact: Sarah Johnson
Associated Company: Acme Corporation
"""

SLACK_EPISODE = """
SLACK MESSAGE from #sales channel:

@john: Hey team, just had a great call with folks from acme.com

@sarah: That's Acme Corp right? The enterprise software company?

@john: Yep! Sarah Johnson (their CFO) is super interested in our Q4 deal.
They're based in SF and looking at the $250k package.

@sarah: Nice! Let's make sure we follow up this week.
"""


class IntegrationTestResults:
    """Track test results across all phases"""
    def __init__(self):
        self.phases = {}
        self.failures = []

    def record_phase(self, phase: str, passed: bool, message: str):
        self.phases[phase] = {"passed": passed, "message": message}
        if not passed:
            self.failures.append(f"{phase}: {message}")

    def summary(self):
        total = len(self.phases)
        passed = sum(1 for p in self.phases.values() if p["passed"])
        return {
            "total": total,
            "passed": passed,
            "failed": total - passed,
            "success_rate": (passed / total * 100) if total > 0 else 0
        }


async def test_full_pipeline():
    """Comprehensive integration test"""

    print("=" * 80)
    print("🧪 COMPREHENSIVE INTEGRATION TEST: Multi-Source Knowledge Graph")
    print("=" * 80)
    print()

    results = IntegrationTestResults()
    test_user = "integration_test_v1"

    # Initialize services
    print("🔧 Initializing services...")
    graphiti = GraphitiService()
    await graphiti.initialize()
    print("✅ Services initialized")
    print()

    # ========================================================================
    # PHASE 1: Schema Initialization
    # ========================================================================
    print("=" * 80)
    print("PHASE 1: SCHEMA INITIALIZATION")
    print("=" * 80)
    print()

    schema = FalkorDBSchema(graphiti.driver)
    await schema.initialize(force=False)

    health = await schema.validate()

    if health['status'] == 'healthy' and health['indices'] >= 10:
        results.record_phase(
            "Phase 1: Schema Init",
            True,
            f"✅ {health['indices']} indices created"
        )
        print(f"✅ PASS: Schema healthy with {health['indices']} indices")
    else:
        results.record_phase(
            "Phase 1: Schema Init",
            False,
            f"❌ Only {health['indices']} indices (expected >=10)"
        )
        print(f"❌ FAIL: Insufficient indices")
    print()

    # ========================================================================
    # PHASE 2: Custom Entity Extraction (Gmail)
    # ========================================================================
    print("=" * 80)
    print("PHASE 2: CUSTOM ENTITY EXTRACTION (Gmail Source)")
    print("=" * 80)
    print()

    print("📧 Processing Gmail episode with custom entity types...")
    gmail_result = await graphiti.graphiti.add_episode(
        name="Gmail: Email from Sarah at Acme",
        episode_body=sanitize_for_falkordb(GMAIL_EPISODE),
        source_description="Gmail email",
        reference_time=datetime(2025, 10, 1, 10, 0, 0, tzinfo=timezone.utc),
        source=EpisodeType.text,
        group_id=test_user,
        entity_types=ENTITY_TYPES,
        excluded_entity_types=EXCLUDED_ENTITY_TYPES
    )

    gmail_entities = len(gmail_result.nodes)
    print(f"Extracted {gmail_entities} entities:")
    for node in gmail_result.nodes:
        print(f"  - {node.name} | Labels: {node.labels}")
    print()

    if 3 <= gmail_entities <= 5:
        results.record_phase(
            "Phase 2: Entity Extraction",
            True,
            f"✅ Clean extraction: {gmail_entities} entities (expected 3-5)"
        )
        print(f"✅ PASS: Clean entity extraction ({gmail_entities} entities)")
    else:
        results.record_phase(
            "Phase 2: Entity Extraction",
            False,
            f"❌ Over-extraction: {gmail_entities} entities (expected 3-5)"
        )
        print(f"❌ FAIL: Too many entities extracted")
    print()

    # ========================================================================
    # PHASE 3: Entity Normalization (Gmail)
    # ========================================================================
    print("=" * 80)
    print("PHASE 3: ENTITY NORMALIZATION (Gmail → Canonical Nodes)")
    print("=" * 80)
    print()

    print("🔄 Normalizing Gmail entities...")
    normalizer_gmail = EntityNormalizer(driver=graphiti.driver, source='gmail')
    gmail_normalized = await normalizer_gmail.normalize_and_persist(
        graphiti_result=gmail_result,
        group_id=test_user
    )

    print(f"Normalized: {gmail_normalized}")
    print()

    # Validate canonical nodes were created
    query_canonical = f"""
    MATCH (c:Company {{group_id: '{test_user}'}})
    RETURN c.name as name, c.domain as domain, c.source as source
    """
    canonical_result, _, _ = await graphiti.driver.execute_query(query_canonical)

    if canonical_result and len(canonical_result) > 0:
        company = canonical_result[0]
        results.record_phase(
            "Phase 3: Normalization",
            True,
            f"✅ Created canonical Company: {company['name']} ({company['domain']})"
        )
        print(f"✅ PASS: Canonical Company created: {company['name']} → {company['domain']}")
    else:
        results.record_phase(
            "Phase 3: Normalization",
            False,
            "❌ No canonical Company node created"
        )
        print("❌ FAIL: Normalization did not create canonical nodes")
    print()

    # ========================================================================
    # PHASE 4: Cross-Source Deduplication (HubSpot)
    # ========================================================================
    print("=" * 80)
    print("PHASE 4: CROSS-SOURCE DEDUPLICATION (HubSpot → Same Company)")
    print("=" * 80)
    print()

    print("🏢 Processing HubSpot episode...")
    hubspot_result = await graphiti.graphiti.add_episode(
        name="HubSpot: Acme Corporation Deal",
        episode_body=sanitize_for_falkordb(HUBSPOT_EPISODE),
        source_description="HubSpot CRM sync",
        reference_time=datetime(2025, 10, 2, 14, 0, 0, tzinfo=timezone.utc),
        source=EpisodeType.text,
        group_id=test_user,
        entity_types=ENTITY_TYPES,
        excluded_entity_types=EXCLUDED_ENTITY_TYPES
    )

    print(f"Extracted {len(hubspot_result.nodes)} entities from HubSpot")
    print()

    print("🔄 Normalizing HubSpot entities...")
    normalizer_hubspot = EntityNormalizer(driver=graphiti.driver, source='hubspot')
    hubspot_normalized = await normalizer_hubspot.normalize_and_persist(
        graphiti_result=hubspot_result,
        group_id=test_user
    )

    print(f"Normalized: {hubspot_normalized}")
    print()

    # Wait for processing
    await asyncio.sleep(2)

    # CRITICAL TEST: Should still be only 1 canonical Company
    query_dedup = f"""
    MATCH (c:Company {{group_id: '{test_user}'}})
    RETURN c.name as name, c.domain as domain, c.source as source
    """
    dedup_result, _, _ = await graphiti.driver.execute_query(query_dedup)

    company_count = len(dedup_result) if dedup_result else 0

    if company_count == 1:
        company = dedup_result[0]
        results.record_phase(
            "Phase 4: Deduplication",
            True,
            f"✅ Cross-source dedup working: 1 Company across Gmail+HubSpot"
        )
        print(f"✅ PASS: Deduplication working!")
        print(f"   Company: {company['name']}")
        print(f"   Domain: {company['domain']}")
        print(f"   Sources: {company['source']}")
    else:
        results.record_phase(
            "Phase 4: Deduplication",
            False,
            f"❌ Deduplication failed: {company_count} companies (expected 1)"
        )
        print(f"❌ FAIL: Found {company_count} companies (expected 1)")
    print()

    # ========================================================================
    # PHASE 5: Slack Message (3rd Source)
    # ========================================================================
    print("=" * 80)
    print("PHASE 5: THIRD SOURCE TEST (Slack → Same Company)")
    print("=" * 80)
    print()

    print("💬 Processing Slack message...")
    slack_result = await graphiti.graphiti.add_episode(
        name="Slack: Sales channel discussion about Acme",
        episode_body=sanitize_for_falkordb(SLACK_EPISODE),
        source_description="Slack message",
        reference_time=datetime(2025, 10, 3, 16, 30, 0, tzinfo=timezone.utc),
        source=EpisodeType.text,
        group_id=test_user,
        entity_types=ENTITY_TYPES,
        excluded_entity_types=EXCLUDED_ENTITY_TYPES
    )

    print(f"Extracted {len(slack_result.nodes)} entities from Slack")
    print()

    normalizer_slack = EntityNormalizer(driver=graphiti.driver, source='slack')
    slack_normalized = await normalizer_slack.normalize_and_persist(
        graphiti_result=slack_result,
        group_id=test_user
    )

    await asyncio.sleep(2)

    # Should STILL be only 1 company
    final_companies, _, _ = await graphiti.driver.execute_query(query_dedup)
    final_count = len(final_companies) if final_companies else 0

    if final_count == 1:
        results.record_phase(
            "Phase 5: Multi-Source",
            True,
            "✅ 3-source dedup: Gmail+HubSpot+Slack → 1 Company"
        )
        print(f"✅ PASS: Still 1 company after 3 sources!")
    else:
        results.record_phase(
            "Phase 5: Multi-Source",
            False,
            f"❌ Multi-source failed: {final_count} companies"
        )
        print(f"❌ FAIL: {final_count} companies after 3 sources")
    print()

    # ========================================================================
    # PHASE 6: CANONICAL_ENTITY Relationship
    # ========================================================================
    print("=" * 80)
    print("PHASE 6: CANONICAL_ENTITY LINKS (Preserved Graphiti Graph)")
    print("=" * 80)
    print()

    query_links = f"""
    MATCH (canonical:Company {{group_id: '{test_user}'}})-[:CANONICAL_ENTITY]->(graphiti:Entity)
    RETURN canonical.name as canonical_name,
           graphiti.name as graphiti_name,
           graphiti.uuid as graphiti_uuid
    """

    links_result, _, _ = await graphiti.driver.execute_query(query_links)
    link_count = len(links_result) if links_result else 0

    if link_count >= 1:
        results.record_phase(
            "Phase 6: CANONICAL_ENTITY Links",
            True,
            f"✅ Found {link_count} canonical→graphiti links"
        )
        print(f"✅ PASS: {link_count} CANONICAL_ENTITY links created")
        for link in links_result[:3]:
            print(f"   {link['canonical_name']} → {link['graphiti_name']}")
    else:
        results.record_phase(
            "Phase 6: CANONICAL_ENTITY Links",
            False,
            "❌ No CANONICAL_ENTITY relationships found"
        )
        print("❌ FAIL: No links between canonical and Graphiti entities")
    print()

    # ========================================================================
    # PHASE 7: AI AGENT QUERY PATTERNS
    # ========================================================================
    print("=" * 80)
    print("PHASE 7: AI AGENT QUERY PATTERNS")
    print("=" * 80)
    print()

    # Query 1: Full-text search on company name
    print("Query 1: Full-text search for 'Acme'")
    query_fulltext = f"""
    CALL db.idx.fulltext.queryNodes('Company', 'acme')
    YIELD node, score
    WHERE node.group_id = '{test_user}'
    RETURN node.name as name, node.domain as domain, score
    LIMIT 5
    """

    try:
        fulltext_result, _, _ = await graphiti.driver.execute_query(query_fulltext)
        if fulltext_result and len(fulltext_result) > 0:
            print(f"✅ Full-text search found {len(fulltext_result)} results")
            for row in fulltext_result:
                print(f"   {row['name']} ({row['domain']}) - score: {row['score']}")
            results.record_phase("Phase 7.1: Full-text Search", True, "✅ Working")
        else:
            print("⚠️  Full-text search returned no results")
            results.record_phase("Phase 7.1: Full-text Search", False, "❌ No results")
    except Exception as e:
        print(f"⚠️  Full-text index may not be ready yet: {e}")
        results.record_phase("Phase 7.1: Full-text Search", False, f"❌ Error: {e}")
    print()

    # Query 2: Graph traversal (canonical → graphiti → relationships)
    print("Query 2: Graph traversal via CANONICAL_ENTITY")
    query_traversal = f"""
    MATCH (c:Company {{group_id: '{test_user}'}})
    MATCH (c)-[:CANONICAL_ENTITY]->(graphiti:Entity)
    MATCH (graphiti)-[r]-(related:Entity)
    RETURN c.name as company,
           type(r) as relationship_type,
           related.name as related_entity,
           count(*) as relationship_count
    LIMIT 10
    """

    traversal_result, _, _ = await graphiti.driver.execute_query(query_traversal)

    if traversal_result and len(traversal_result) > 0:
        print(f"✅ Graph traversal found {len(traversal_result)} relationships")
        for row in traversal_result[:5]:
            print(f"   {row['company']} -{row['relationship_type']}-> {row['related_entity']}")
        results.record_phase("Phase 7.2: Graph Traversal", True, "✅ Relationships preserved")
    else:
        print("❌ No relationships found via traversal")
        results.record_phase("Phase 7.2: Graph Traversal", False, "❌ No relationships")
    print()

    # Query 3: Exact domain lookup
    print("Query 3: Exact domain lookup")
    query_exact = f"""
    MATCH (c:Company {{domain: 'acme.com', group_id: '{test_user}'}})
    RETURN c.name as name, c.domain as domain, c.source as source
    """

    exact_result, _, _ = await graphiti.driver.execute_query(query_exact)

    if exact_result and len(exact_result) > 0:
        print(f"✅ Exact lookup found company")
        print(f"   {exact_result[0]}")
        results.record_phase("Phase 7.3: Exact Lookup", True, "✅ Fast domain lookup")
    else:
        print("❌ Exact lookup failed")
        results.record_phase("Phase 7.3: Exact Lookup", False, "❌ Failed")
    print()

    # ========================================================================
    # FINAL SUMMARY
    # ========================================================================
    print("=" * 80)
    print("📊 INTEGRATION TEST SUMMARY")
    print("=" * 80)
    print()

    summary = results.summary()

    print(f"Total Phases: {summary['total']}")
    print(f"Passed: {summary['passed']} ✅")
    print(f"Failed: {summary['failed']} ❌")
    print(f"Success Rate: {summary['success_rate']:.1f}%")
    print()

    if summary['failed'] > 0:
        print("❌ FAILURES:")
        for failure in results.failures:
            print(f"   - {failure}")
        print()

    print("DETAILED RESULTS:")
    for phase, result in results.phases.items():
        status = "✅" if result['passed'] else "❌"
        print(f"  {status} {phase}: {result['message']}")
    print()

    # Overall verdict
    if summary['success_rate'] >= 90:
        print("=" * 80)
        print("🎉 INTEGRATION TEST PASSED!")
        print("=" * 80)
        print()
        print("Your multi-source knowledge graph architecture is working!")
        print()
        print("Next steps:")
        print("1. Integrate normalizer into sync_tasks.py")
        print("2. Integrate normalizer into webhook_tasks.py")
        print("3. Run production Gmail sync (3 days)")
        print("4. Ship to beta customers")
    elif summary['success_rate'] >= 70:
        print("=" * 80)
        print("⚠️  INTEGRATION TEST PARTIALLY PASSED")
        print("=" * 80)
        print()
        print("Core functionality working, but some issues found.")
        print("Review failures above and address before production.")
    else:
        print("=" * 80)
        print("❌ INTEGRATION TEST FAILED")
        print("=" * 80)
        print()
        print("Critical issues found. Do not proceed to production.")
        print("Review failures and fix before re-testing.")

    print()
    print("=" * 80)

    # Cleanup
    await graphiti.close()

    return summary['success_rate'] >= 90


if __name__ == "__main__":
    success = asyncio.run(test_full_pipeline())
    exit(0 if success else 1)
