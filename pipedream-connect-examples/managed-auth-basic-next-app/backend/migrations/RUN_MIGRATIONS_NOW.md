# ⚡ RUN THESE MIGRATIONS NOW

**Time Required:** 10 minutes
**Where:** Supabase SQL Editor

---

## 🚀 Step 1: Open Supabase SQL Editor

1. Go to: https://supabase.com/dashboard/project/rgmgvuuqhghlzbtivcep
2. Click **SQL Editor** (left sidebar)
3. Click **New query**

---

## 📋 Step 2: Migration 1 - Episode Deduplication

**Copy and paste this SQL, then click RUN:**

```sql
-- Migration: Create processed_episodes deduplication table
CREATE TABLE IF NOT EXISTS processed_episodes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id TEXT NOT NULL,
    source TEXT NOT NULL,
    source_id TEXT NOT NULL,
    episode_uuid UUID,
    processed_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT unique_episode UNIQUE(user_id, source, source_id)
);

CREATE INDEX IF NOT EXISTS idx_processed_episodes_lookup
ON processed_episodes(user_id, source, source_id);

CREATE INDEX IF NOT EXISTS idx_processed_episodes_uuid
ON processed_episodes(episode_uuid);

CREATE INDEX IF NOT EXISTS idx_processed_episodes_source_time
ON processed_episodes(user_id, source, processed_at DESC);
```

**Expected:** `Success. No rows returned`

✅ Check: Run `SELECT count(*) FROM processed_episodes;` → should return `0`

---

## 🔍 Step 3: Migration 2 - Fix Vector Embeddings

**Copy and paste this SQL, then click RUN:**

```sql
-- Migration: Fix vector_embedding column
CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE documents DROP COLUMN IF EXISTS vector_embedding;
ALTER TABLE documents ADD COLUMN vector_embedding vector(1536);

CREATE INDEX IF NOT EXISTS documents_vector_embedding_idx
ON documents
USING hnsw (vector_embedding vector_cosine_ops);
```

**Expected:** `Success. No rows returned`

✅ Check: Run this query to verify column type:
```sql
SELECT column_name, data_type, udt_name
FROM information_schema.columns
WHERE table_name = 'documents' AND column_name = 'vector_embedding';
```

**Expected result:**
```
column_name: vector_embedding
data_type: USER-DEFINED
udt_name: vector
```

---

## ✅ Migrations Complete!

Now go back to your terminal and:

1. **Re-generate embeddings** (see SETUP_MIGRATIONS.md Step 3)
2. **Clean duplicate episodes** (see SETUP_MIGRATIONS.md Step 4)
3. **Test everything works** (see SETUP_MIGRATIONS.md Step 5-6)

---

**Need help?** See `SETUP_MIGRATIONS.md` for full step-by-step guide
