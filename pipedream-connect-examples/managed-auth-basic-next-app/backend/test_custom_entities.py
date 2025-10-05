#!/usr/bin/env python3
"""
Phase 0 Validation: Test Custom Entity Extraction with Graphiti

Tests custom entity types with strict exclusion rules to prevent over-extraction.
"""

import asyncio
from datetime import datetime, timezone
from pydantic import BaseModel, Field
from services.graphiti_service import GraphitiService
from graphiti_core.nodes import EpisodeType


# Define custom entity types with strict exclusion rules in docstrings
class Company(BaseModel):
    """
    A business organization or corporation.

    INCLUDE:
    - Full company names (e.g., "Acme Corporation", "Google LLC")
    - Organizations with employees or business operations

    EXCLUDE:
    - Domain names alone (e.g., "acme.com" - extract as domain attribute)
    - Email addresses (e.g., "info@acme.com")
    - URLs or LinkedIn profiles
    - Industry categories (e.g., "Enterprise Software")
    - Physical locations (e.g., "San Francisco office")

    Extract domain, industry, location as ATTRIBUTES, not separate entities.
    """
    domain: str | None = Field(None, description="Company's primary domain (e.g., acme.com)")
    industry: str | None = Field(None, description="Industry or sector")
    location: str | None = Field(None, description="Primary office location")


class Contact(BaseModel):
    """
    A person, typically with a professional role.

    INCLUDE:
    - Full names of people (e.g., "Sarah Johnson", "John Smith")
    - Individuals with job titles or roles

    EXCLUDE:
    - Email addresses alone (extract as email attribute)
    - Phone numbers alone (extract as phone attribute)
    - LinkedIn URLs or social profiles
    - Job titles without names (e.g., just "CFO" or "Chief Financial Officer")
    - Generic role descriptions

    Extract email, phone, title as ATTRIBUTES, not separate entities.
    """
    email: str | None = Field(None, description="Contact's email address")
    phone: str | None = Field(None, description="Contact's phone number")
    title: str | None = Field(None, description="Job title or role")


class Deal(BaseModel):
    """
    A sales opportunity or business transaction with a name.

    INCLUDE:
    - Named sales opportunities (e.g., "Q4 Enterprise License - Acme Corp")
    - Business transactions with identifiers
    - Specific deals with context

    EXCLUDE:
    - Money amounts alone (e.g., "$250,000" or "250000 dollars")
    - Deal stage names alone (e.g., "Negotiation", "Proposal")
    - Generic product names without deal context
    - Individual contract terms

    Extract amount, stage, products as ATTRIBUTES, not separate entities.
    """
    amount: int | None = Field(None, description="Deal value in dollars")
    stage: str | None = Field(None, description="Sales stage (e.g., 'Negotiation')")
    products: str | None = Field(None, description="Products or services in the deal")


async def test_custom_entities():
    """Test custom entity extraction with strict type definitions"""

    print("=" * 80)
    print("🧪 PHASE 0: CUSTOM ENTITY EXTRACTION TEST")
    print("=" * 80)
    print()

    # Initialize Graphiti
    print("Initializing Graphiti service...")
    graphiti = GraphitiService()
    await graphiti.initialize()
    print("✅ Graphiti initialized")
    print()

    test_user = "test_custom_entities_v2"

    # Define custom entity types
    entity_types = {
        "Company": Company,
        "Contact": Contact,
        "Deal": Deal
    }

    print(f"Test User: {test_user}")
    print(f"Entity Types: {list(entity_types.keys())}")
    print()

    # EPISODE 1: Email from Acme contact
    print("📧 Creating Episode 1: Email from Acme Corporation contact...")

    email_episode = """
From: sarah.johnson@acme.com
Subject: Q4 Enterprise License Discussion
Date: 2025-10-01

Hi team,

I'm Sarah Johnson, CFO at Acme Corporation. We're interested in your enterprise
license for our 500-person organization. Our domain is acme.com, and we're located
in San Francisco, CA.

We're looking at a $250,000 deal for the Q4 Enterprise Suite with Premium Support.
Currently in negotiation stage. My phone is +1 555-123-4567 and LinkedIn is
linkedin.com/in/sarahjohnson.

Looking forward to discussing pricing.

Best,
Sarah Johnson
CFO, Acme Corporation
"""

    result1 = await graphiti.graphiti.add_episode(
        name="Email from Sarah Johnson at Acme",
        episode_body=email_episode,
        source_description="Email from potential customer",
        reference_time=datetime(2025, 10, 1, 10, 0, 0, tzinfo=timezone.utc),
        source=EpisodeType.text,
        group_id=test_user,
        entity_types=entity_types,
        excluded_entity_types=["Entity"]  # CRITICAL: Only extract custom types
    )

    print(f"✅ Episode 1: Extracted {len(result1.nodes)} entities, {len(result1.edges)} relationships")
    for node in result1.nodes:
        print(f"   - {node.name}")
    print()

    # EPISODE 2: HubSpot CRM data
    print("🏢 Creating Episode 2: HubSpot CRM record for Acme...")

    hubspot_episode = """
HUBSPOT CRM RECORD:

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

    result2 = await graphiti.graphiti.add_episode(
        name="HubSpot: Acme Corporation Deal",
        episode_body=hubspot_episode,
        source_description="HubSpot CRM sync",
        reference_time=datetime(2025, 10, 2, 14, 0, 0, tzinfo=timezone.utc),
        source=EpisodeType.text,
        group_id=test_user,
        entity_types=entity_types,
        excluded_entity_types=["Entity"]  # Same exclusion rule
    )

    print(f"✅ Episode 2: Extracted {len(result2.nodes)} entities, {len(result2.edges)} relationships")
    for node in result2.nodes:
        print(f"   - {node.name}")
    print()

    # Wait for processing
    print("⏳ Waiting 5 seconds for processing...")
    await asyncio.sleep(5)
    print()

    # VALIDATION: Query FalkorDB
    print("=" * 80)
    print("🔍 VALIDATION RESULTS")
    print("=" * 80)
    print()

    # Count total entities
    query_total = f"""
    MATCH (n:Entity)
    WHERE n.group_id = '{test_user}'
    RETURN COUNT(n) AS total_entities
    """

    result, _, _ = await graphiti.driver.execute_query(query_total)
    total_entities = result[0]['total_entities'] if result else 0

    print(f"📊 TOTAL ENTITIES EXTRACTED: {total_entities}")
    print()

    # Show all entities
    query_all = f"""
    MATCH (n:Entity)
    WHERE n.group_id = '{test_user}'
    RETURN n.name AS name, labels(n) AS labels
    ORDER BY n.created_at
    """

    result_all, _, _ = await graphiti.driver.execute_query(query_all)

    if result_all:
        print("Entities created:")
        for idx, row in enumerate(result_all, 1):
            print(f"  {idx}. {row['name']} | Labels: {row['labels']}")
        print()

    # Check for deduplication - how many "Acme" entities?
    query_acme = f"""
    MATCH (n:Entity)
    WHERE n.group_id = '{test_user}' AND n.name CONTAINS 'Acme'
    RETURN n.name AS name
    """

    result_acme, _, _ = await graphiti.driver.execute_query(query_acme)
    acme_count = len(result_acme) if result_acme else 0

    print(f"🔍 Deduplication Test: Found {acme_count} entities containing 'Acme'")
    if result_acme:
        for row in result_acme:
            print(f"   - {row['name']}")
    print()

    # SUCCESS CRITERIA
    print("=" * 80)
    print("📋 TEST RESULTS")
    print("=" * 80)
    print()

    success = True

    if total_entities <= 5:
        print("✅ EXCELLENT: Custom entity types working!")
        print("   Expected: 3-5 entities (1 Company, 1 Contact, 1 Deal)")
        print(f"   Actual: {total_entities} entities")
        print()
        print("   ✅ Path A is viable - proceed with classification layer")
    elif total_entities <= 8:
        print("⚠️  WARNING: Some over-extraction still occurring")
        print(f"   Expected: 3-5 entities, Got: {total_entities}")
        print()
        print("   💡 Next steps:")
        print("   - Review entity type docstrings for stricter EXCLUDE rules")
        print("   - Consider hybrid approach (Path A + some deterministic cleanup)")
    else:
        print("❌ FAILURE: Too many entities extracted")
        print(f"   Expected: 3-5 entities, Got: {total_entities}")
        print()
        print("   🚨 Path A won't work - Need Path B (deterministic extraction) from day one")
        success = False

    print()

    if acme_count == 1:
        print("✅ DEDUPLICATION WORKING: Exactly 1 'Acme' entity across both episodes")
    elif acme_count == 2:
        print("⚠️  DEDUPLICATION PARTIAL: 2 'Acme' entities (email vs HubSpot may be separate)")
    else:
        print(f"❌ DEDUPLICATION FAILING: {acme_count} 'Acme' entities found")
        success = False

    print()
    print("=" * 80)

    # Cleanup
    await graphiti.close()

    return success


if __name__ == "__main__":
    asyncio.run(test_custom_entities())
