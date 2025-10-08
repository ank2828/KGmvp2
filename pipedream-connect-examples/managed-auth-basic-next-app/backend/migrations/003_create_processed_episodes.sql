-- Migration: Create processed_episodes deduplication table
-- Purpose: Track which episodes have been processed to prevent duplicates
-- Multi-source ready: Works for Gmail, Slack, HubSpot, Google Docs, etc.

CREATE TABLE IF NOT EXISTS processed_episodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    source TEXT NOT NULL,  -- 'gmail', 'hubspot', 'slack', 'google_docs', etc.
    source_id TEXT NOT NULL,  -- Gmail message_id, HubSpot event_id, Slack message_id, etc.
    episode_uuid UUID,  -- Link to FalkorDB Episodic node UUID
    processed_at TIMESTAMPTZ DEFAULT NOW(),

    -- Prevent duplicate processing
    CONSTRAINT unique_episode UNIQUE(user_id, source, source_id)
);

-- Index for fast lookups during deduplication check
CREATE INDEX IF NOT EXISTS idx_processed_episodes_lookup
ON processed_episodes(user_id, source, source_id);

-- Index for querying by episode UUID (reverse lookup)
CREATE INDEX IF NOT EXISTS idx_processed_episodes_uuid
ON processed_episodes(episode_uuid);

-- Index for audit queries (what was processed when)
CREATE INDEX IF NOT EXISTS idx_processed_episodes_source_time
ON processed_episodes(user_id, source, processed_at DESC);

COMMENT ON TABLE processed_episodes IS 'Tracks processed episodes across all data sources to prevent duplicate processing';
COMMENT ON COLUMN processed_episodes.source IS 'Data source identifier: gmail, slack, hubspot, google_docs, notion, etc.';
COMMENT ON COLUMN processed_episodes.source_id IS 'Unique ID from source system (e.g., Gmail message ID, Slack timestamp)';
COMMENT ON COLUMN processed_episodes.episode_uuid IS 'UUID of the Episodic node created in FalkorDB';
