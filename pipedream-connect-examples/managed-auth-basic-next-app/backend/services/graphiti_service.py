"""
Graphiti Knowledge Graph Service
"""

import logging
import time
from typing import Dict, List, Any
from datetime import datetime, timezone

from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodeType

from config import settings
from models.email import EmailMessage, GraphProcessingResult
from services.database import db_service
from services.entity_types import ENTITY_TYPES, EXCLUDED_ENTITY_TYPES

logger = logging.getLogger(__name__)


class GraphitiService:
    """Manages Graphiti knowledge graph operations"""

    def __init__(self):
        """Initialize with FalkorDB Cloud driver"""

        from graphiti_core.driver.falkordb_driver import FalkorDriver

        # CRITICAL: Parse host:port from FalkorDB Cloud connection string
        # Cloud endpoint format: "host.cloud:62994"
        host_parts = settings.falkordb_host.rsplit(':', 1)
        host = host_parts[0]
        port = int(host_parts[1]) if len(host_parts) > 1 else settings.falkordb_port

        logger.info(f"Connecting to FalkorDB - Host: {host}, Port: {port}")

        # Create FalkorDB driver
        self.driver = FalkorDriver(
            host=host,
            port=port,
            username=settings.falkordb_username,
            password=settings.falkordb_password,
            database=settings.falkordb_database,
        )

        # Initialize Graphiti
        self.graphiti = Graphiti(graph_driver=self.driver)
        self._initialized = False

        logger.info(f"Graphiti service created")

    async def has_episode_been_processed(
        self,
        source: str,
        source_id: str,
        user_id: str
    ) -> bool:
        """
        Check if an episode has already been processed (deduplication).

        Uses Supabase tracking table for multi-source deduplication.
        Works for Gmail, Slack, HubSpot, Google Docs, etc.

        Args:
            source: Data source identifier (e.g., 'gmail', 'slack', 'hubspot')
            source_id: Unique ID from source system (e.g., Gmail message_id)
            user_id: User's ID for multi-tenant isolation

        Returns:
            True if episode already exists, False otherwise
        """
        try:
            result = db_service.client.table('processed_episodes')\
                .select('id')\
                .match({
                    'user_id': user_id,
                    'source': source,
                    'source_id': source_id
                })\
                .execute()

            exists = len(result.data) > 0

            if exists:
                logger.info(f"✅ Episode already processed: {source}:{source_id}")

            return exists

        except Exception as e:
            logger.warning(f"Error checking episode deduplication: {e}")
            # If check fails, assume episode doesn't exist to avoid blocking
            return False

    async def mark_episode_as_processed(
        self,
        source: str,
        source_id: str,
        user_id: str,
        episode_uuid: str
    ):
        """
        Mark an episode as processed in Supabase tracking table.

        Args:
            source: Data source identifier (e.g., 'gmail', 'slack', 'hubspot')
            source_id: Unique ID from source system
            user_id: User's ID
            episode_uuid: UUID of the Episodic node created in FalkorDB
        """
        try:
            db_service.client.table('processed_episodes').insert({
                'user_id': user_id,
                'source': source,
                'source_id': source_id,
                'episode_uuid': episode_uuid
            }).execute()

            logger.info(f"✅ Marked as processed: {source}:{source_id} → {episode_uuid}")

        except Exception as e:
            # Log but don't fail - episode was already processed successfully
            logger.error(f"Failed to mark episode as processed: {e}")

    async def initialize(self):
        """Build indices (call once on startup)"""
        if self._initialized:
            logger.warning("Graphiti already initialized, skipping...")
            return

        try:
            logger.info("Building Graphiti indices and constraints...")
            await self.graphiti.build_indices_and_constraints()
            self._initialized = True
            logger.info("Graphiti indices ready")
        except Exception as e:
            logger.error(f"Failed to initialize Graphiti: {e}")
            raise

    async def process_email(
        self,
        email: EmailMessage,
        user_id: str = "default_user",
        source: str = "gmail"
    ) -> GraphProcessingResult:
        """
        Process a single email through Graphiti with deduplication.

        Args:
            email: EmailMessage model
            user_id: User identifier for graph partitioning
            source: Data source identifier (default: 'gmail')

        Returns:
            GraphProcessingResult with extracted entities/relationships
        """
        start_time = time.time()

        try:
            # Check if episode already processed (deduplication)
            if await self.has_episode_been_processed(source, email.message_id, user_id):
                logger.info(f"⏭️  Skipping duplicate episode: {email.subject[:50]}...")
                return GraphProcessingResult(
                    episode_uuid="",
                    entities_extracted=0,
                    relationships_extracted=0,
                    entity_names=[],
                    relationships=[],
                    processing_time_ms=0
                )

            # Build episode content
            episode_content = self._build_episode_content(email)

            # Process through Graphiti
            logger.info(f"Processing email: {email.subject[:50]}...")

            result = await self.graphiti.add_episode(
                name=f"Email: {email.subject[:100]}",
                episode_body=episode_content,
                source=EpisodeType.text,
                source_description="Gmail message",
                reference_time=datetime.now(timezone.utc),
                group_id=user_id,
                entity_types=ENTITY_TYPES,
                excluded_entity_types=EXCLUDED_ENTITY_TYPES,
            )

            # Mark as processed in deduplication table
            await self.mark_episode_as_processed(
                source=source,
                source_id=email.message_id,
                user_id=user_id,
                episode_uuid=result.episode.uuid
            )

            # Extract results
            entity_names = [node.name for node in result.nodes]
            relationships = [edge.fact for edge in result.edges[:5]]

            processing_time = (time.time() - start_time) * 1000

            logger.info(
                f"Processed '{email.subject[:30]}...' in {processing_time:.0f}ms "
                f"({len(result.nodes)} entities, {len(result.edges)} relationships)"
            )

            return GraphProcessingResult(
                episode_uuid=result.episode.uuid,
                entities_extracted=len(result.nodes),
                relationships_extracted=len(result.edges),
                entity_names=entity_names,
                relationships=relationships,
                processing_time_ms=processing_time,
            )

        except Exception as e:
            logger.error(f"Failed to process email '{email.subject}': {e}")
            raise

    def _build_episode_content(self, email: EmailMessage) -> str:
        """Format email data as episode content"""
        content = f"""
Email Message:
From: {email.sender}
Subject: {email.subject}
Date: {email.date}
Message ID: {email.message_id}
        """.strip()

        if email.body:
            content += f"\n\nBody:\n{email.body}"

        return content

    async def search(
        self,
        query: str,
        limit: int = 10,
        user_id: str = "default_user"
    ) -> List[Dict[str, Any]]:
        """Search knowledge graph"""
        try:
            results = await self.graphiti.search(
                query,
                group_ids=[user_id],
                num_results=limit
            )

            return [
                {
                    "fact": edge.fact,
                    "source": edge.source_node_uuid,
                    "target": edge.target_node_uuid,
                    "valid_at": edge.valid_at.isoformat() if edge.valid_at else None,
                }
                for edge in results
            ]
        except Exception as e:
            logger.error(f"Search failed for '{query}': {e}")
            raise

    async def clear_database(self) -> Dict[str, Any]:
        """
        Clear all data from FalkorDB Cloud (DEV/TEST ONLY).

        WARNING: This permanently deletes all nodes, edges, and episodes.
        Use only for development testing.

        Returns:
            Dictionary with deletion counts and status
        """
        try:
            logger.warning("⚠️  Clearing all data from FalkorDB Cloud...")

            # Count nodes before deletion (for reporting)
            count_query = "MATCH (n) RETURN count(n) as node_count"
            result, _, _ = await self.driver.execute_query(count_query)
            nodes_before = result[0]['node_count'] if result else 0

            # Delete all nodes and relationships
            # DETACH DELETE removes all relationships connected to nodes
            delete_query = "MATCH (n) DETACH DELETE n"
            await self.driver.execute_query(delete_query)

            logger.info(f"✅ Deleted {nodes_before} nodes and all relationships")

            # Rebuild indices and constraints
            # This ensures the database is ready for new data
            logger.info("Rebuilding Graphiti indices...")
            await self.graphiti.build_indices_and_constraints()
            logger.info("✅ Indices rebuilt")

            return {
                "success": True,
                "nodes_deleted": nodes_before,
                "message": f"Cleared {nodes_before} nodes and all relationships. Indices rebuilt."
            }

        except Exception as e:
            logger.error(f"❌ Failed to clear database: {e}")
            raise Exception(f"Database clear failed: {str(e)}")

    async def close(self):
        """Cleanup connections"""
        try:
            await self.graphiti.close()
            logger.info("Graphiti closed")
        except Exception as e:
            logger.error(f"Error closing Graphiti: {e}")

    @property
    def is_initialized(self) -> bool:
        return self._initialized
