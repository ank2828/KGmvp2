# 🚀 Database Migrations Setup Guide

## 📋 Overview

This guide will walk you through setting up:
1. ✅ Episode deduplication (prevent duplicate processing)
2. ✅ Vector search fix (enable semantic search)

---

## 🎯 Step 1: Create Supabase Tables

### **Open Supabase SQL Editor**
1. Go to https://supabase.com/dashboard
2. Select your project: `rgmgvuuqhghlzbtivcep`
3. Click **SQL Editor** in left sidebar
4. Click **New query**

---

### **Migration 1: Episode Deduplication Table**

Paste this SQL and click **RUN**:

```sql
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
```

**Expected Output:** `Success. No rows returned`

---

### **Migration 2: Fix Vector Embeddings**

Paste this SQL and click **RUN**:

```sql
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
```

**Expected Output:** `Success. No rows returned`

⚠️ **Note:** This will drop the existing (broken) embeddings. You'll need to re-generate them in Step 3.

---

## 🧪 Step 2: Verify Tables Created

Run this query to check:

```sql
-- Check processed_episodes table
SELECT
    table_name,
    column_name,
    data_type
FROM information_schema.columns
WHERE table_name = 'processed_episodes'
ORDER BY ordinal_position;

-- Check vector_embedding column type
SELECT
    column_name,
    data_type,
    udt_name
FROM information_schema.columns
WHERE table_name = 'documents' AND column_name = 'vector_embedding';
```

**Expected Output:**

```
processed_episodes table:
- id (uuid)
- user_id (text)
- source (text)
- source_id (text)
- episode_uuid (uuid)
- processed_at (timestamp with time zone)

documents.vector_embedding:
- data_type: USER-DEFINED
- udt_name: vector
```

✅ If you see `udt_name: vector`, the migration succeeded!

---

## 🔄 Step 3: Re-generate Vector Embeddings

Now that the column type is fixed, re-generate embeddings for existing documents.

### **Backend Terminal:**

```bash
cd backend
source venv311/bin/activate
python3 -c "
import asyncio
from services.document_store import document_store
from services.database import db_service

async def regenerate_embeddings():
    # Get all documents without embeddings
    result = db_service.client.table('documents')\
        .select('id, subject, content, user_id')\
        .is_('vector_embedding', 'null')\
        .execute()

    print(f'Found {len(result.data)} documents needing embeddings')

    for doc in result.data:
        # Generate embedding
        text = f\"{doc.get('subject', '')} {doc.get('content', '')}\"
        embedding = await document_store._generate_embedding(text)

        # Update document
        db_service.client.table('documents')\
            .update({'vector_embedding': embedding})\
            .eq('id', doc['id'])\
            .execute()

        print(f\"✅ Generated embedding for: {doc.get('subject', 'Untitled')[:50]}\")

    print(f'✅ All {len(result.data)} embeddings regenerated!')

asyncio.run(regenerate_embeddings())
"
```

**Expected Output:**
```
Found 6 documents needing embeddings
✅ Generated embedding for: 1 new notification since 12 51 pm Oct 7 2025
✅ Generated embedding for: New Gemini features Better videos presentations
✅ Generated embedding for: Initech - Trial Conversion Opportunity
✅ Generated embedding for: Globex Corp - Customer Success Check-in
✅ Generated embedding for: RE: Q4 Enterprise License - Pricing Discussion
✅ Generated embedding for: TechFlow - Integration Requirements
✅ All 6 embeddings regenerated!
```

---

## 🧹 Step 4: Clean Up Duplicate Episodes in FalkorDB

Remove the 2 duplicate episodes found in the analysis.

### **Backend Terminal:**

```bash
python3 -c "
import asyncio
from services.graphiti_service import GraphitiService

async def clean_duplicates():
    graphiti = GraphitiService()

    # Find duplicates by name
    duplicate_names = [
        'Email: New Gemini features Better videos presentations & more',
        'Email: 1 new notification since 12 51 pm Oct 7 2025'
    ]

    for name in duplicate_names:
        query = f'''
        MATCH (e:Episodic {{name: \$name}})
        WITH e
        ORDER BY e.created_at DESC
        SKIP 1  // Keep the most recent one
        DETACH DELETE e
        RETURN count(e) as deleted
        '''

        result, _, _ = await graphiti.driver.execute_query(query, {'name': name})
        deleted = result[0]['deleted'] if result else 0
        print(f\"✅ Deleted {deleted} duplicate(s) of: {name[:50]}...\")

    print('✅ Duplicate cleanup complete!')

asyncio.run(clean_duplicates())
"
```

**Expected Output:**
```
✅ Deleted 1 duplicate(s) of: Email: New Gemini features Better videos presentations...
✅ Deleted 1 duplicate(s) of: Email: 1 new notification since 12 51 pm Oct 7 2025...
✅ Duplicate cleanup complete!
```

---

## ✅ Step 5: Test Deduplication

Try syncing the same emails again - they should be skipped.

### **Backend Terminal:**

```bash
# Test endpoint (replace with your actual user_id and account_id)
curl -X POST "http://localhost:8000/api/gmail/fetch-messages-list?external_user_id=8d6126ed-dfb5-4fff-9d72-b84fb0cb889a&account_id=apn_4vhyvM6&max_results=5"
```

**Expected Log Output:**
```
✅ Episode already processed: gmail:msg_12345
⏭️  Skipping duplicate episode: New Gemini features Better videos...
✅ Episode already processed: gmail:msg_67890
⏭️  Skipping duplicate episode: 1 new notification since...
```

---

## ✅ Step 6: Test Semantic Search

Verify vector search is working.

### **Backend Terminal:**

```bash
python3 -c "
import asyncio
from services.document_store import document_store

async def test_search():
    results = await document_store.search_documents_semantic(
        query='What did Sarah email me about?',
        user_id='8d6126ed-dfb5-4fff-9d72-b84fb0cb889a',
        limit=3,
        min_similarity=0.3
    )

    print(f'Found {len(results)} results:')
    for result in results:
        doc = result['document']
        similarity = result['similarity']
        print(f\"  [{similarity:.2f}] {doc.subject}\")
        print(f\"      From: {doc.metadata.get('from', 'Unknown')}\")
        print(f\"      Preview: {doc.content_preview[:80]}...\")
        print()

asyncio.run(test_search())
"
```

**Expected Output:**
```
Found 1 results:
  [0.54] RE: Q4 Enterprise License - Pricing Discussion
      From: sarah.johnson@acme-corp.com
      Preview: Hi team, I had a great call with Sarah Johnson from Acme Corp yesterday...
```

---

## 🎉 Success Criteria

After completing all steps, verify:

- [ ] `processed_episodes` table exists in Supabase
- [ ] `documents.vector_embedding` column is type `vector(1536)` (not TEXT)
- [ ] All 6 documents have embeddings regenerated
- [ ] FalkorDB has 3 Episodic nodes (2 duplicates deleted)
- [ ] Re-syncing same emails shows "skipping duplicate" logs
- [ ] Semantic search returns results with similarity scores

---

## 🔍 Troubleshooting

### **Issue: Migration fails with "relation already exists"**

**Solution:** That's OK - it means the table already exists. Skip to the next migration.

---

### **Issue: Embedding regeneration fails with "column vector_embedding does not exist"**

**Solution:** Run Migration 2 again to create the vector column.

---

### **Issue: Semantic search returns no results**

**Diagnosis:**
```sql
-- Check if embeddings exist
SELECT id, subject, vector_embedding IS NULL as missing_embedding
FROM documents
WHERE user_id = '8d6126ed-dfb5-4fff-9d72-b84fb0cb889a';
```

**Solution:** If `missing_embedding` is `true`, re-run Step 3 to regenerate embeddings.

---

### **Issue: Duplicate episodes still being created**

**Diagnosis:** Check if `processed_episodes` table is being populated:

```sql
SELECT source, count(*)
FROM processed_episodes
WHERE user_id = '8d6126ed-dfb5-4fff-9d72-b84fb0cb889a'
GROUP BY source;
```

**Solution:** If empty, check backend logs for errors when calling `mark_episode_as_processed()`.

---

## 📊 Verify Everything Works

### **Final Test: Full Gmail Sync Flow**

```bash
# Fetch 5 new emails
curl -X POST "http://localhost:8000/api/gmail/sync-30-days?user_id=8d6126ed-dfb5-4fff-9d72-b84fb0cb889a&account_id=apn_4vhyvM6&days=7"
```

**Expected Behavior:**
1. ✅ Emails fetched from Gmail
2. ✅ Stored in Supabase `documents` table
3. ✅ Embeddings generated automatically
4. ✅ Deduplication check runs before Graphiti
5. ✅ If new: Process through Graphiti → Mark as processed
6. ✅ If duplicate: Skip processing
7. ✅ AI agent can query both graph facts + semantic search

---

## 🎯 Next Steps After Setup

1. **Add Google Docs integration** - Same deduplication pattern
2. **Add Slack integration** - Same deduplication pattern
3. **Set up webhook handlers** - Idempotency keys for live data
4. **Monitor OpenAI costs** - Embeddings cost $0.02/1M tokens

---

## 📚 Reference

- **Supabase Dashboard:** https://supabase.com/dashboard/project/rgmgvuuqhghlzbtivcep
- **Migration Files:** `backend/migrations/`
- **Deduplication Code:** `backend/services/graphiti_service.py` (lines 51-121)
- **Vector Storage:** `backend/services/document_store.py` (lines 234-306)

---

✅ **You're all set!** The knowledge graph is now optimized for scale with:
- Multi-source deduplication
- Fast vector search
- Production-ready architecture
