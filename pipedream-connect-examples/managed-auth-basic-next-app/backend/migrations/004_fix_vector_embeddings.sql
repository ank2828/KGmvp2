-- Migration: Fix vector_embedding column to use proper pgvector type
-- Purpose: Enable semantic search with pgvector
-- Issue: Currently stored as TEXT (19K+ chars), needs to be vector(1536)

-- Step 1: Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Step 2: Drop broken TEXT column
ALTER TABLE documents DROP COLUMN IF EXISTS vector_embedding;

-- Step 3: Add proper vector column (1536 dimensions for text-embedding-3-small)
ALTER TABLE documents ADD COLUMN vector_embedding vector(1536);

-- Step 4: Create HNSW index for fast similarity search
-- HNSW (Hierarchical Navigable Small World) is the fastest algorithm for ANN search
CREATE INDEX IF NOT EXISTS documents_vector_embedding_idx
ON documents
USING hnsw (vector_embedding vector_cosine_ops);

-- Note: After running this migration, you must re-generate embeddings for all existing documents
-- The vector_embedding column will be NULL until embeddings are regenerated

COMMENT ON COLUMN documents.vector_embedding IS 'OpenAI text-embedding-3-small vector (1536 dimensions) for semantic search';
