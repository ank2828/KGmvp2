"""
FalkorDB Schema Initialization and Management

This module defines the schema layer for enterprise knowledge graphs.
Run once on deployment, then enforce deduplication via application-level MERGE.

Key Features:
- Range indices for high-cardinality properties
- Vector indices for semantic search (AI agent similarity queries)
- Full-text indices for content search (AI agent text queries)
- Application-level deduplication via MERGE (no DB constraints needed)

Note: FalkorDB constraints require Redis-level commands not accessible via Graphiti driver.
Deduplication is handled by MERGE queries in entity_normalizer.py.

AI Agent Optimization:
- Full-text indices on company names, contact names for fuzzy matching
- Vector indices on embeddings for semantic similarity
- Range indices on domain/email for exact lookups

Usage:
    from services.falkordb_schema import FalkorDBSchema

    schema = FalkorDBSchema(driver)
    await schema.initialize()  # Run once on deployment
    await schema.validate()     # Check schema health
"""

import logging
from typing import Dict, List, Any

logger = logging.getLogger(__name__)


class FalkorDBSchema:
    """Manages FalkorDB schema initialization and validation"""

    def __init__(self, driver):
        """
        Args:
            driver: FalkorDriver instance from GraphitiService
        """
        self.driver = driver

    async def initialize(self, force: bool = False):
        """
        Initialize FalkorDB schema.

        CRITICAL: Run BEFORE any data ingestion.

        Args:
            force: If True, drop existing indices and recreate

        Execution order:
        1. Range indices (fast lookups & deduplication support)
        2. Vector indices (semantic search for AI agents)
        3. Full-text indices (fuzzy text search for AI agents)
        """
        logger.info("=" * 80)
        logger.info("🏗️  INITIALIZING FALKORDB SCHEMA (AI-OPTIMIZED)")
        logger.info("=" * 80)

        if force:
            logger.warning("⚠️  Force mode enabled - dropping existing schema...")
            await self._drop_schema()

        # Step 1: Create range indices
        logger.info("\n📊 Step 1: Creating range indices...")
        await self._create_range_indices()

        # Step 2: Create vector indices for semantic search
        logger.info("\n🧠 Step 2: Creating vector indices...")
        await self._create_vector_indices()

        # Step 3: Create full-text indices for content search
        logger.info("\n🔍 Step 3: Creating full-text indices (AI agent queries)...")
        await self._create_fulltext_indices()

        logger.info("\n" + "=" * 80)
        logger.info("✅ SCHEMA INITIALIZATION COMPLETE")
        logger.info("   Optimized for AI agent queries (vector + full-text search)")
        logger.info("=" * 80)

        # Validate schema
        await self.validate()

    async def _create_range_indices(self):
        """
        Create range indices for high-cardinality properties.

        These enable:
        - Fast equality lookups (WHERE c.domain = 'acme.com')
        - Range queries (WHERE c.created_at > timestamp)
        - Support for MERGE-based deduplication
        """
        indices = [
            # Company indices (domain = dedup key, name = AI search target)
            "CREATE INDEX FOR (c:Company) ON (c.domain)",
            "CREATE INDEX FOR (c:Company) ON (c.canonical_id)",
            "CREATE INDEX FOR (c:Company) ON (c.name)",
            "CREATE INDEX FOR (c:Company) ON (c.source)",
            "CREATE INDEX FOR (c:Company) ON (c.created_at)",

            # Contact indices (email = dedup key, name = AI search target)
            "CREATE INDEX FOR (p:Contact) ON (p.email)",
            "CREATE INDEX FOR (p:Contact) ON (p.canonical_id)",
            "CREATE INDEX FOR (p:Contact) ON (p.name)",
            "CREATE INDEX FOR (p:Contact) ON (p.source)",
            "CREATE INDEX FOR (p:Contact) ON (p.created_at)",

            # Deal indices
            "CREATE INDEX FOR (d:Deal) ON (d.id)",
            "CREATE INDEX FOR (d:Deal) ON (d.canonical_id)",
            "CREATE INDEX FOR (d:Deal) ON (d.name)",
            "CREATE INDEX FOR (d:Deal) ON (d.stage)",
            "CREATE INDEX FOR (d:Deal) ON (d.amount)",
            "CREATE INDEX FOR (d:Deal) ON (d.source)",
            "CREATE INDEX FOR (d:Deal) ON (d.created_at)",

            # Email/Document indices (for provenance)
            "CREATE INDEX FOR (e:Email) ON (e.message_id)",
            "CREATE INDEX FOR (e:Email) ON (e.thread_id)",
            "CREATE INDEX FOR (e:Email) ON (e.timestamp)",
            "CREATE INDEX FOR (d:Document) ON (d.id)",
            "CREATE INDEX FOR (d:Document) ON (d.source)",
            "CREATE INDEX FOR (d:Document) ON (d.created_at)",

            # Multi-source tracking (prevents duplicate imports)
            "CREATE INDEX FOR (n:Entity) ON (n.source)",
            "CREATE INDEX FOR (n:Entity) ON (n.source_id)",
            "CREATE INDEX FOR (n:Entity) ON (n.graphiti_uuid)",

            # User/group partitioning
            "CREATE INDEX FOR (n:Entity) ON (n.group_id)",
        ]

        for idx_query in indices:
            try:
                await self.driver.execute_query(idx_query)
                entity_type = idx_query.split("(")[1].split(":")[1].split(")")[0]
                property_name = idx_query.split("(")[2].split(".")[1].rstrip(")")
                logger.info(f"  ✓ Created index: {entity_type}.{property_name}")
            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.debug(f"  • Index exists (skipping)")
                else:
                    logger.error(f"  ✗ Failed to create index: {idx_query} - {e}")
                    raise

    async def _create_vector_indices(self):
        """
        Create vector indices for semantic search.

        Dimension: 768 (OpenAI text-embedding-ada-002)
        Use 1536 for text-embedding-3-small

        AI Agent Usage:
        - Semantic company matching: "Find companies similar to Acme"
        - Document similarity: "Find docs related to this topic"
        - Hybrid search: vector similarity + graph traversal
        """
        vector_indices = [
            # Document embeddings for semantic search
            """CREATE VECTOR INDEX FOR (d:Document) ON (d.embedding)
               OPTIONS {dimension: 768, similarityFunction: 'cosine'}""",

            # Email embeddings (if generating embeddings for emails)
            """CREATE VECTOR INDEX FOR (e:Email) ON (e.embedding)
               OPTIONS {dimension: 768, similarityFunction: 'cosine'}""",

            # Company embeddings (AI agent semantic company matching)
            """CREATE VECTOR INDEX FOR (c:Company) ON (c.embedding)
               OPTIONS {dimension: 768, similarityFunction: 'cosine'}""",

            # Contact embeddings (AI agent semantic contact matching)
            """CREATE VECTOR INDEX FOR (p:Contact) ON (p.embedding)
               OPTIONS {dimension: 768, similarityFunction: 'cosine'}""",
        ]

        for idx_query in vector_indices:
            try:
                await self.driver.execute_query(idx_query)
                entity_type = idx_query.split("(")[1].split(":")[1].split(")")[0]
                logger.info(f"  ✓ Created vector index: {entity_type}.embedding")
            except Exception as e:
                if "already exists" in str(e).lower():
                    logger.debug(f"  • Vector index exists (skipping)")
                else:
                    logger.error(f"  ✗ Failed to create vector index: {e}")

    async def _create_fulltext_indices(self):
        """
        Create full-text search indices for content.

        AI Agent Usage:
        - Fuzzy name matching: "Show me deals with Acme" → matches "Acme Corp", "ACME Inc"
        - Content search: "Find emails about pricing" → searches email bodies
        - Company search: "Companies in enterprise software" → searches descriptions

        CRITICAL FOR AI ACCURACY: These indices enable fuzzy text matching
        that exact domain/email lookups can't provide.
        """
        fulltext_indices = [
            # Email body search (AI searches email content)
            "CALL db.idx.fulltext.createNodeIndex('Email', 'body')",

            # Document content search (AI searches document text)
            "CALL db.idx.fulltext.createNodeIndex('Document', 'content')",

            # Company name search (AI fuzzy matches company names)
            "CALL db.idx.fulltext.createNodeIndex('Company', 'name')",

            # Company description search (AI searches company details)
            "CALL db.idx.fulltext.createNodeIndex('Company', 'description')",

            # Contact name search (AI fuzzy matches people names)
            "CALL db.idx.fulltext.createNodeIndex('Contact', 'name')",

            # Deal name search (AI searches deal titles)
            "CALL db.idx.fulltext.createNodeIndex('Deal', 'name')",
        ]

        for idx_query in fulltext_indices:
            try:
                await self.driver.execute_query(idx_query)
                parts = idx_query.split("'")
                entity_type = parts[1]
                field = parts[3]
                logger.info(f"  ✓ Created full-text index: {entity_type}.{field}")
            except Exception as e:
                if "already exists" in str(e).lower() or "index exists" in str(e).lower():
                    logger.debug(f"  • Full-text index exists (skipping)")
                else:
                    logger.warning(f"  ⚠️  Failed to create full-text index: {e}")

    async def _drop_schema(self):
        """
        Drop all indices (DANGEROUS - DEV ONLY).
        """
        logger.warning("⚠️  Dropping all indices...")
        logger.warning("  Manual schema cleanup required")

    async def validate(self) -> Dict[str, Any]:
        """
        Validate schema health and report status.

        Returns:
            Dict with schema status: indices, counts
        """
        logger.info("\n🔍 Validating schema...")

        # Check indices
        indices_query = "CALL db.indexes()"
        try:
            result, _, _ = await self.driver.execute_query(indices_query)
            index_count = len(result) if result else 0
            logger.info(f"  • Indices: {index_count} found")
        except Exception as e:
            logger.error(f"  ✗ Failed to query indices: {e}")
            index_count = 0

        # Count entities
        count_query = "MATCH (n) RETURN labels(n)[0] as label, count(n) as count"
        try:
            result, _, _ = await self.driver.execute_query(count_query)
            entity_counts = {row['label']: row['count'] for row in result} if result else {}
            logger.info(f"  • Entity counts: {entity_counts}")
        except Exception as e:
            logger.error(f"  ✗ Failed to count entities: {e}")
            entity_counts = {}

        return {
            "indices": index_count,
            "entity_counts": entity_counts,
            "status": "healthy" if index_count > 0 else "incomplete"
        }

    async def get_schema_info(self) -> Dict[str, List[Dict[str, Any]]]:
        """
        Get complete schema information.

        Returns:
            Dict with indices and relationship types
        """
        # Get indices
        indices_query = "CALL db.indexes()"
        indices_result, _, _ = await self.driver.execute_query(indices_query)

        # Get relationship types
        rel_query = "MATCH ()-[r]->() RETURN DISTINCT type(r) as rel_type, count(r) as count"
        rel_result, _, _ = await self.driver.execute_query(rel_query)

        return {
            "indices": indices_result or [],
            "relationship_types": rel_result or []
        }
