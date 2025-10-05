#!/usr/bin/env python3
"""
FalkorDB Schema Initialization Script

Run ONCE on deployment to set up enterprise schema.

Usage:
    python -m migrations.init_schema

This script:
1. Initializes FalkorDB indices (range, vector, full-text)
2. Validates schema health
3. Reports index counts and entity statistics

CRITICAL: Run BEFORE any data ingestion.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from services.graphiti_service import GraphitiService
from services.falkordb_schema import FalkorDBSchema

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

logger = logging.getLogger(__name__)


async def main():
    """Initialize FalkorDB schema"""
    logger.info("=" * 80)
    logger.info("🚀 FALKORDB SCHEMA INITIALIZATION")
    logger.info("=" * 80)
    print()

    # Step 1: Initialize Graphiti service (provides FalkorDB driver)
    logger.info("Step 1: Connecting to FalkorDB via Graphiti...")
    graphiti_service = GraphitiService()
    await graphiti_service.initialize()
    logger.info("✅ Connected to FalkorDB")
    print()

    # Step 2: Initialize schema
    logger.info("Step 2: Initializing FalkorDB schema...")
    schema = FalkorDBSchema(graphiti_service.driver)

    # Set force=False to skip dropping existing indices
    # Set force=True to recreate all indices (DANGEROUS - dev only)
    await schema.initialize(force=False)
    print()

    # Step 3: Validate schema health
    logger.info("Step 3: Validating schema...")
    health = await schema.validate()
    print()

    # Step 4: Report results
    logger.info("=" * 80)
    logger.info("📊 SCHEMA INITIALIZATION SUMMARY")
    logger.info("=" * 80)
    print()

    logger.info(f"Status: {health['status']}")
    logger.info(f"Indices created: {health['indices']}")
    logger.info(f"Entity counts: {health['entity_counts']}")
    print()

    if health['status'] == 'healthy':
        logger.info("✅ Schema initialization complete!")
        logger.info("   Your FalkorDB is ready for entity normalization.")
    else:
        logger.warning("⚠️  Schema initialization incomplete")
        logger.warning("   Some indices may be missing. Check logs above.")

    print()
    logger.info("=" * 80)

    # Cleanup
    await graphiti_service.close()

    return 0 if health['status'] == 'healthy' else 1


if __name__ == "__main__":
    try:
        exit_code = asyncio.run(main())
        sys.exit(exit_code)
    except KeyboardInterrupt:
        logger.info("\n⚠️  Interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"\n❌ Schema initialization failed: {e}", exc_info=True)
        sys.exit(1)
