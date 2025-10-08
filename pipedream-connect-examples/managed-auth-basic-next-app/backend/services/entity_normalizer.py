"""
Entity Normalization Layer: Graphiti → FalkorDB

Transforms Graphiti's extracted entities into canonical nodes optimized for AI agent queries.

Architecture:
- Canonical nodes (Company, Contact, Deal) for AI agent searches
- Links to Graphiti entities via CANONICAL_ENTITY relationship
- Preserves Graphiti's rich relationship graph
- Enables hybrid queries: normalized structure + Graphiti context

Key Features:
- Domain/email-based deduplication (deterministic, not LLM similarity)
- Full-text search on canonical names (AI fuzzy matching)
- Cross-source entity resolution (Gmail + HubSpot + Slack)
- Provenance tracking (source, timestamps)

This solves the multi-source deduplication problem while keeping Graphiti's graph intact.
"""

import logging
import re
from typing import Dict, List, Any, Optional
from datetime import datetime, timezone
from uuid import uuid4

logger = logging.getLogger(__name__)


class EntityNormalizer:
    """Normalizes Graphiti entities to canonical FalkorDB nodes"""

    def __init__(self, driver, source: str = "unknown"):
        """
        Args:
            driver: FalkorDriver instance
            source: Data source identifier (gmail, hubspot, slack, etc.)
        """
        self.driver = driver
        self.source = source

    async def normalize_and_persist(
        self,
        graphiti_result,
        group_id: str,
        episode_metadata: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        Main normalization pipeline.

        Creates canonical entities linked to Graphiti's original entities.
        AI agents query canonical nodes, then traverse to Graphiti for relationships.

        Args:
            graphiti_result: Result from graphiti.add_episode()
            group_id: User/tenant identifier
            episode_metadata: Additional context (email subject, timestamp, etc.)

        Returns:
            Dict with normalized entity counts and IDs
        """
        logger.info(f"🔄 Normalizing {len(graphiti_result.nodes)} Graphiti entities...")

        normalized_counts = {
            "companies": 0,
            "contacts": 0,
            "deals": 0,
            "relationships": 0,
            "skipped": 0
        }

        # Process each Graphiti node
        for node in graphiti_result.nodes:
            try:
                # Detect entity type from Graphiti labels
                entity_type = self._detect_entity_type(node.labels)

                if entity_type == "Company":
                    await self._normalize_company(node, group_id)
                    normalized_counts["companies"] += 1

                elif entity_type == "Contact":
                    await self._normalize_contact(node, group_id)
                    normalized_counts["contacts"] += 1

                elif entity_type == "Deal":
                    await self._normalize_deal(node, group_id)
                    normalized_counts["deals"] += 1

                else:
                    logger.debug(f"  • Skipping unknown entity type: {node.name} (labels: {node.labels})")
                    normalized_counts["skipped"] += 1

            except Exception as e:
                logger.error(f"  ✗ Failed to normalize {node.name}: {e}")
                normalized_counts["skipped"] += 1

        # Note: We don't normalize Graphiti relationships - they stay in Graphiti's graph
        # AI agents traverse via: Canonical Entity → CANONICAL_ENTITY → Graphiti Entity → Graphiti Relationships

        logger.info(f"  ✓ Normalized: {normalized_counts}")
        return normalized_counts

    def _detect_entity_type(self, labels: List[str]) -> Optional[str]:
        """
        Extract FalkorDB entity type from Graphiti labels.

        Graphiti labels: ['Entity', 'Company'] → 'Company'
        Graphiti labels: ['Entity', 'Contact'] → 'Contact'
        """
        # Remove generic 'Entity' label
        specific_labels = [l for l in labels if l not in ['Entity', 'Node']]

        # Return first specific label
        return specific_labels[0] if specific_labels else None

    async def _normalize_company(self, node, group_id: str):
        """
        Normalize Company entity.

        Creates canonical Company node linked to Graphiti's original entity.

        Canonical identifier: domain (for cross-source deduplication)
        AI search field: name (for full-text fuzzy matching)
        Link to Graphiti: graphiti_uuid (preserves relationships)
        """
        # Extract domain from node name or attributes
        domain = self._extract_domain(node.name)

        if not domain:
            logger.warning(f"  ⚠️  Company '{node.name}' has no domain - using slugified name")
            domain = self._slugify(node.name)

        # Extract clean company name (for AI search)
        clean_name = self._clean_company_name(node.name)

        # Build normalized company node
        company_data = {
            "name": clean_name,  # AI searches this
            "domain": domain,     # Deduplication key
            "canonical_id": str(uuid4()),
            "graphiti_uuid": node.uuid,  # Link to Graphiti entity
            "source": self.source,
            "group_id": group_id,
            "created_at": int(datetime.now(timezone.utc).timestamp()),
            "last_updated": int(datetime.now(timezone.utc).timestamp()),
        }

        # Add optional attributes from Graphiti node
        if hasattr(node, 'attributes') and node.attributes:
            if 'industry' in node.attributes:
                company_data['industry'] = node.attributes['industry']
            if 'location' in node.attributes:
                company_data['location'] = node.attributes['location']
            if 'description' in node.attributes:
                company_data['description'] = node.attributes['description']

        # CRITICAL: Create canonical Company + link to Graphiti entity
        query = """
        // Step 1: Create/update canonical Company node
        MERGE (c:Company {domain: $domain})
        ON CREATE SET
            c.name = $name,
            c.canonical_id = $canonical_id,
            c.group_id = $group_id,
            c.created_at = $created_at,
            c.last_updated = $last_updated,
            c.industry = $industry,
            c.location = $location,
            c.description = $description
        ON MATCH SET
            c.last_updated = $last_updated,
            c.industry = COALESCE($industry, c.industry),
            c.location = COALESCE($location, c.location),
            c.description = COALESCE($description, c.description)

        // Step 2: Link canonical Company to Graphiti's original entity
        WITH c
        MATCH (graphiti:Entity {uuid: $graphiti_uuid})
        MERGE (c)-[rel:CANONICAL_ENTITY]->(graphiti)

        RETURN c.canonical_id as id, c.name as name
        """

        result, _, _ = await self.driver.execute_query(
            query,
            domain=domain,
            name=clean_name,
            canonical_id=company_data['canonical_id'],
            graphiti_uuid=company_data['graphiti_uuid'],
            source=company_data['source'],
            group_id=company_data['group_id'],
            created_at=company_data['created_at'],
            last_updated=company_data['last_updated'],
            industry=company_data.get('industry'),
            location=company_data.get('location'),
            description=company_data.get('description')
        )

        if result:
            logger.debug(f"  ✓ Company: {result[0]['name']} → {domain} (linked to Graphiti)")

    async def _normalize_contact(self, node, group_id: str):
        """
        Normalize Contact entity.

        Canonical identifier: email (for cross-source deduplication)
        AI search field: name (for full-text fuzzy matching)
        Link to Graphiti: graphiti_uuid (preserves relationships)
        """
        # Extract email from node attributes
        email = self._extract_email(node)

        if not email:
            logger.warning(f"  ⚠️  Contact '{node.name}' has no email - skipping")
            return

        contact_data = {
            "name": node.name,
            "email": email,
            "canonical_id": str(uuid4()),
            "graphiti_uuid": node.uuid,
            "source": self.source,
            "group_id": group_id,
            "created_at": int(datetime.now(timezone.utc).timestamp()),
            "last_updated": int(datetime.now(timezone.utc).timestamp()),
        }

        # Add optional attributes
        if hasattr(node, 'attributes') and node.attributes:
            if 'title' in node.attributes:
                contact_data['title'] = node.attributes['title']
            if 'phone' in node.attributes:
                contact_data['phone'] = node.attributes['phone']

        query = """
        // Create canonical Contact
        MERGE (p:Contact {email: $email})
        ON CREATE SET
            p.name = $name,
            p.canonical_id = $canonical_id,
            p.group_id = $group_id,
            p.created_at = $created_at,
            p.last_updated = $last_updated,
            p.title = $title,
            p.phone = $phone
        ON MATCH SET
            p.last_updated = $last_updated,
            p.title = COALESCE($title, p.title),
            p.phone = COALESCE($phone, p.phone)

        // Link to Graphiti entity
        WITH p
        MATCH (graphiti:Entity {uuid: $graphiti_uuid})
        MERGE (p)-[rel:CANONICAL_ENTITY]->(graphiti)

        RETURN p.canonical_id as id
        """

        result, _, _ = await self.driver.execute_query(
            query,
            email=email,
            name=contact_data['name'],
            canonical_id=contact_data['canonical_id'],
            graphiti_uuid=contact_data['graphiti_uuid'],
            source=contact_data['source'],
            group_id=contact_data['group_id'],
            created_at=contact_data['created_at'],
            last_updated=contact_data['last_updated'],
            title=contact_data.get('title'),
            phone=contact_data.get('phone')
        )
        logger.debug(f"  ✓ Contact: {node.name} → {email}")

    async def _normalize_deal(self, node, group_id: str):
        """
        Normalize Deal entity.

        Canonical identifier: slugified name (for deterministic deduplication within group)
        AI search field: name (for full-text fuzzy matching)
        Link to Graphiti: graphiti_uuid (preserves relationships)
        """
        # Priority: Use CRM ID when available, fallback to slugified name, then UUID
        if hasattr(node, 'attributes') and node.attributes:
            if 'hubspot_deal_id' in node.attributes:
                deal_id = node.attributes['hubspot_deal_id']
            elif 'deal_id' in node.attributes:
                deal_id = node.attributes['deal_id']
            else:
                deal_id = self._slugify(node.name)  # Deterministic deduplication key
                if not deal_id:  # Fallback if slugify returns empty string
                    deal_id = node.uuid
        else:
            deal_id = self._slugify(node.name)
            if not deal_id:  # Fallback if slugify returns empty string
                deal_id = node.uuid

        deal_data = {
            "name": node.name,
            "id": deal_id,
            "canonical_id": str(uuid4()),
            "graphiti_uuid": node.uuid,
            "source": self.source,
            "group_id": group_id,
            "created_at": int(datetime.now(timezone.utc).timestamp()),
            "last_updated": int(datetime.now(timezone.utc).timestamp()),
        }

        # Add optional attributes
        if hasattr(node, 'attributes') and node.attributes:
            if 'amount' in node.attributes:
                deal_data['amount'] = node.attributes['amount']
            if 'stage' in node.attributes:
                deal_data['stage'] = node.attributes['stage']
            if 'products' in node.attributes:
                deal_data['products'] = node.attributes['products']

        query = """
        // Create canonical Deal (deduplication within group_id scope)
        MERGE (d:Deal {id: $id, group_id: $group_id})
        ON CREATE SET
            d.name = $name,
            d.canonical_id = $canonical_id,
            d.created_at = $created_at,
            d.last_updated = $last_updated,
            d.amount = $amount,
            d.stage = $stage,
            d.products = $products
        ON MATCH SET
            d.last_updated = $last_updated,
            d.amount = COALESCE($amount, d.amount),
            d.stage = COALESCE($stage, d.stage),
            d.products = COALESCE($products, d.products)

        // Link to Graphiti entity
        WITH d
        MATCH (graphiti:Entity {uuid: $graphiti_uuid})
        MERGE (d)-[rel:CANONICAL_ENTITY]->(graphiti)

        RETURN d.canonical_id as id
        """

        result, _, _ = await self.driver.execute_query(
            query,
            id=deal_id,
            name=deal_data['name'],
            canonical_id=deal_data['canonical_id'],
            graphiti_uuid=deal_data['graphiti_uuid'],
            source=deal_data['source'],
            group_id=deal_data['group_id'],
            created_at=deal_data['created_at'],
            last_updated=deal_data['last_updated'],
            amount=deal_data.get('amount'),
            stage=deal_data.get('stage'),
            products=deal_data.get('products')
        )
        logger.debug(f"  ✓ Deal: {node.name} → {deal_id}")

    def _extract_domain(self, text: str) -> Optional[str]:
        """
        Extract domain from company name.

        Examples:
        - "Acme Corporation" → "acme.com" (heuristic)
        - "acme.com" → "acme.com"
        - "Google LLC" → "google.com"

        TODO: Enhance with Clearbit/domain lookup API for production accuracy
        """
        if not text:
            return None

        # Check if already a domain
        if '.' in text and ' ' not in text:
            return text.lower()

        # Extract from company name (simple heuristic)
        base_name = text.split()[0].lower()

        # Remove common suffixes
        base_name = re.sub(r'(corp|corporation|inc|llc|ltd)', '', base_name)

        # Return as .com (most common TLD)
        return f"{base_name}.com"

    def _clean_company_name(self, text: str) -> str:
        """
        Clean company name for AI search.

        Keeps human-readable format but removes noise.
        """
        # Remove domain if present in name
        if '@' in text or '.com' in text or '.io' in text:
            # Extract company name before domain
            text = text.split('@')[0].split('.com')[0].split('.io')[0]

        # Capitalize properly
        return text.strip()

    def _extract_email(self, node) -> Optional[str]:
        """Extract email from Graphiti node attributes"""
        if hasattr(node, 'attributes') and node.attributes:
            if 'email' in node.attributes:
                return node.attributes['email']

        # Try to extract from name
        email_pattern = r'[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}'
        match = re.search(email_pattern, node.name)
        return match.group(0) if match else None

    def _slugify(self, text: str) -> str:
        """Convert text to slug: "Q4 Enterprise Deal" → "q4-enterprise-deal" """
        return re.sub(r'[^a-z0-9]+', '-', text.lower()).strip('-')
