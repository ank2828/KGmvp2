-- ============================================================================
-- PHASE 1: SUPABASE DOCUMENT STORAGE LAYER
-- ============================================================================
-- Purpose: Store full email content with vector embeddings for semantic search
-- Replaces: FalkorDB Episode queries (too slow for document retrieval)
-- Architecture: Hybrid storage (Supabase for content, FalkorDB for relationships)
-- ============================================================================

-- Enable pgvector extension for semantic search
CREATE EXTENSION IF NOT EXISTS vector;

-- ============================================================================
-- TABLE: documents
-- ============================================================================
-- Stores individual emails/messages from all sources (Gmail, Slack, HubSpot)
-- Each row = 1 email (not batched like FalkorDB Episodes)
-- ============================================================================

CREATE TABLE IF NOT EXISTS documents (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- User ownership
    user_id TEXT NOT NULL,  -- Matches Supabase auth user ID

    -- Source tracking
    source TEXT NOT NULL,        -- 'gmail', 'slack', 'hubspot', 'notion'
    source_id TEXT NOT NULL,     -- External ID (Gmail message_id, Slack message_ts)
    doc_type TEXT NOT NULL,      -- 'email', 'slack_message', 'deal', 'note'

    -- Content fields
    subject TEXT,                -- Email subject or message title
    content TEXT NOT NULL,       -- Full body content (plain text)
    content_preview TEXT,        -- First 200 chars for UI display

    -- Metadata (JSONB for flexibility across different sources)
    -- Gmail: {from, to, date, thread_id}
    -- Slack: {channel_id, user_id, thread_ts, team_id}
    -- HubSpot: {deal_id, stage, owner_id}
    metadata JSONB DEFAULT '{}'::jsonb,

    -- Timestamps
    source_created_at TIMESTAMPTZ,  -- When email was sent/message posted
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Vector search (OpenAI text-embedding-3-small = 1536 dimensions)
    vector_embedding vector(1536),

    -- Deduplication constraint (same source document can't be stored twice)
    CONSTRAINT unique_source_document UNIQUE(source, source_id, user_id)
);

-- ============================================================================
-- INDICES: Optimized for AI agent queries
-- ============================================================================

-- 1. User + source queries ("Show me all Gmail emails")
CREATE INDEX IF NOT EXISTS idx_documents_user_source
    ON documents(user_id, source);

-- 2. Temporal queries ("Show me emails from last month")
CREATE INDEX IF NOT EXISTS idx_documents_created
    ON documents(source_created_at DESC);

-- 3. User + temporal queries (combined)
CREATE INDEX IF NOT EXISTS idx_documents_user_created
    ON documents(user_id, source_created_at DESC);

-- 4. Source ID lookups (find by Gmail message_id)
CREATE INDEX IF NOT EXISTS idx_documents_source_id
    ON documents(source_id);

-- 5. Full-text search on subject + content (fallback for keyword queries)
CREATE INDEX IF NOT EXISTS idx_documents_fts
    ON documents
    USING gin(to_tsvector('english', COALESCE(subject, '') || ' ' || content));

-- 6. Vector similarity search (cosine distance for semantic search)
-- Using HNSW for fast approximate nearest neighbor search
CREATE INDEX IF NOT EXISTS idx_documents_vector
    ON documents
    USING hnsw (vector_embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- Note: hnsw is faster than ivfflat for < 1M vectors
-- For 100K emails, HNSW query time: ~10ms vs ivfflat: ~50ms

-- ============================================================================
-- TABLE: document_entities
-- ============================================================================
-- Links Supabase documents to FalkorDB entities (bridge between systems)
-- Enables queries like: "Find all emails mentioning Company X"
-- ============================================================================

CREATE TABLE IF NOT EXISTS document_entities (
    -- Primary key
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),

    -- Foreign key to documents table
    document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,

    -- FalkorDB entity reference (NO foreign key - different database)
    entity_uuid TEXT NOT NULL,     -- Graphiti entity UUID from FalkorDB
    entity_type TEXT NOT NULL,     -- 'Company', 'Contact', 'Deal'
    entity_name TEXT NOT NULL,     -- Cached for quick lookups without FalkorDB query

    -- Mention context (for relevance scoring)
    mention_count INT DEFAULT 1,   -- How many times entity appears in document
    relevance_score FLOAT DEFAULT 1.0,  -- 0.0-1.0, from Graphiti extraction confidence

    -- Timestamps
    created_at TIMESTAMPTZ DEFAULT NOW(),

    -- Prevent duplicate links
    CONSTRAINT unique_document_entity UNIQUE(document_id, entity_uuid)
);

-- ============================================================================
-- INDICES: Optimized for entity-based document retrieval
-- ============================================================================

-- 1. Find documents for an entity ("Show me all emails mentioning Sarah")
CREATE INDEX IF NOT EXISTS idx_doc_entities_entity
    ON document_entities(entity_uuid);

-- 2. Find entities in a document ("What entities are in this email?")
CREATE INDEX IF NOT EXISTS idx_doc_entities_document
    ON document_entities(document_id);

-- 3. Filter by entity type ("Show me all emails mentioning companies")
CREATE INDEX IF NOT EXISTS idx_doc_entities_entity_type
    ON document_entities(entity_type);

-- 4. Relevance-based queries (for ranking results)
CREATE INDEX IF NOT EXISTS idx_doc_entities_relevance
    ON document_entities(relevance_score DESC);

-- ============================================================================
-- TRIGGERS: Auto-update timestamps
-- ============================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_documents_updated_at
    BEFORE UPDATE ON documents
    FOR EACH ROW
    EXECUTE PROCEDURE update_updated_at_column();

-- ============================================================================
-- RPC FUNCTION: Vector similarity search
-- ============================================================================
-- Custom function for semantic search with hybrid filtering
-- Combines vector similarity + metadata filters
-- ============================================================================

CREATE OR REPLACE FUNCTION match_documents (
    query_embedding vector(1536),
    match_threshold float DEFAULT 0.5,
    match_count int DEFAULT 10,
    filter_user_id text DEFAULT NULL,
    filter_source text DEFAULT NULL
)
RETURNS TABLE (
    id uuid,
    user_id text,
    source text,
    source_id text,
    doc_type text,
    subject text,
    content text,
    content_preview text,
    metadata jsonb,
    source_created_at timestamptz,
    created_at timestamptz,
    similarity float
)
LANGUAGE plpgsql
AS $$
BEGIN
    RETURN QUERY
    SELECT
        d.id,
        d.user_id,
        d.source,
        d.source_id,
        d.doc_type,
        d.subject,
        d.content,
        d.content_preview,
        d.metadata,
        d.source_created_at,
        d.created_at,
        1 - (d.vector_embedding <=> query_embedding) as similarity
    FROM documents d
    WHERE
        -- Optional user filter
        (filter_user_id IS NULL OR d.user_id = filter_user_id)
        -- Optional source filter
        AND (filter_source IS NULL OR d.source = filter_source)
        -- Similarity threshold
        AND 1 - (d.vector_embedding <=> query_embedding) > match_threshold
    ORDER BY d.vector_embedding <=> query_embedding
    LIMIT match_count;
END;
$$;

-- ============================================================================
-- COMMENTS: Document schema for maintainability
-- ============================================================================

COMMENT ON TABLE documents IS 'Full content storage for emails, Slack messages, HubSpot deals, etc. Each row = 1 document (not batched).';
COMMENT ON COLUMN documents.vector_embedding IS 'OpenAI text-embedding-3-small (1536 dims) for semantic search';
COMMENT ON COLUMN documents.metadata IS 'Source-specific metadata as JSONB (from/to for Gmail, channel_id for Slack, etc)';
COMMENT ON COLUMN documents.content_preview IS 'First 200 chars for UI display without fetching full content';

COMMENT ON TABLE document_entities IS 'Links Supabase documents to FalkorDB entities. Enables citation: "This fact came from email X"';
COMMENT ON COLUMN document_entities.entity_uuid IS 'Graphiti entity UUID from FalkorDB (no FK - different database)';
COMMENT ON COLUMN document_entities.relevance_score IS 'Confidence score from Graphiti extraction (0.0-1.0)';

-- ============================================================================
-- MIGRATION COMPLETE
-- ============================================================================
-- Next steps:
-- 1. Run this migration in Supabase SQL editor
-- 2. Verify tables created: SELECT tablename FROM pg_tables WHERE schemaname='public' AND tablename LIKE 'document%';
-- 3. Test vector search function: SELECT match_documents(...)
-- ============================================================================
