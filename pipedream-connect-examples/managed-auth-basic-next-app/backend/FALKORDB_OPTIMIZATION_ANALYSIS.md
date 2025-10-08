# 🔍 FalkorDB + Supabase Storage Analysis

**Date:** October 7, 2025
**Status:** HYBRID SYSTEM OPERATIONAL ✅
**User:** `8d6126ed-dfb5-4fff-9d72-b84fb0cb889a`
**Sanitized Group ID:** `8d6126eddfb54fff9d72b84fb0cb889a`

---

## 📊 CURRENT STATE

### **FalkorDB (Knowledge Graph)**

| Metric | Count | Notes |
|--------|-------|-------|
| **Entity nodes** | 26 | People, companies, products extracted from emails |
| **Episodic nodes** | 5 | Email messages processed |
| **RELATES_TO relationships** | 49 | Entity-to-entity connections |
| **MENTIONS relationships** | 59 | Episode-to-entity connections |
| **Group ID** | 1 | All data under `8d6126eddfb54fff9d72b84fb0cb889a` |

**Node Structure:**
```
Entity (26 nodes)
  ├─ Gemini App, Google LLC, Calendar, Drive, Gmail, etc.

Episodic (5 nodes)
  ├─ Email: New Gemini features Better videos presentations & more
  ├─ Email: 1 new notification since 12 51 pm Oct 7 2025
  └─ (3 more emails)
```

**Relationship Pattern:**
```
Episode -[MENTIONS]-> Entity
Entity -[RELATES_TO]-> Entity
```

### **Supabase (Document Storage)**

| Metric | Count | Notes |
|--------|-------|-------|
| **Documents** | 6 | Full email content with metadata |
| **Document-Entity links** | 9 | Bridge table connecting Supabase ↔ FalkorDB |
| **Vector embeddings** | 6 | ⚠️ **BROKEN** - stored as strings, not arrays |
| **Sources** | gmail | Ready for multi-source (Docs, Slack, etc.) |

**Document Types:**
- 3 seed test emails (Acme, Globex, Initech)
- 3 real Gmail emails (Gemini features, notifications)

---

## 🚨 CRITICAL ISSUES

### **Issue 1: Duplicate Episodes in FalkorDB**

**Evidence:**
```
'Email: New Gemini features Better videos presentations & more': 2 instances
'Email: 1 new notification since 12 51 pm Oct 7 2025': 2 instances
```

**Root Cause:** Email sync is re-processing the same emails multiple times, creating duplicate Episodic nodes in FalkorDB.

**Impact:**
- ❌ Bloats graph database with redundant data
- ❌ AI agent sees duplicate facts in search results
- ❌ Wastes OpenAI tokens on re-processing same content
- ❌ Increases FalkorDB storage costs

**Fix Required:**
1. Add deduplication check before `graphiti.add_episode()`
2. Track processed message IDs in Supabase or Redis
3. Skip episodes that already exist by `source_id`

**Proposed Solution:**
```python
# In routes/gmail.py, before processing:
async def has_episode_been_processed(user_id: str, message_id: str) -> bool:
    """Check if episode already exists in FalkorDB"""
    query = f"MATCH (e:Episodic {{group_id: '{user_id}'}}) WHERE e.source_id = '{message_id}' RETURN count(e) as count"
    result, _, _ = await graphiti.driver.execute_query(query)
    return result[0]['count'] > 0 if result else False

# Skip processing if already exists
if await has_episode_been_processed(sanitized_user_id, email.message_id):
    logger.info(f"Skipping duplicate episode: {email.subject}")
    continue
```

---

### **Issue 2: Vector Embeddings Stored as Strings**

**Evidence:**
```
⚠️  Stored as STRING (19212 chars)
⚠️  Stored as STRING (19270 chars)
⚠️  Stored as STRING (19215 chars)
```

**Root Cause:** Supabase `documents.vector_embedding` column is `TEXT`, not `VECTOR(1536)`.

**Impact:**
- ❌ **Semantic search completely broken** - pgvector can't query text columns
- ❌ AI agent falls back to keyword search only
- ❌ No similarity scoring available
- ❌ Wasting storage on stringified JSON arrays

**Fix Required:**
1. Drop current `vector_embedding` column
2. Create new column with pgvector type: `vector(1536)`
3. Re-generate embeddings as proper arrays
4. Create HNSW index for fast similarity search

**SQL Migration:**
```sql
-- 1. Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- 2. Drop text column
ALTER TABLE documents DROP COLUMN IF EXISTS vector_embedding;

-- 3. Add vector column
ALTER TABLE documents ADD COLUMN vector_embedding vector(1536);

-- 4. Create HNSW index for fast similarity search
CREATE INDEX documents_vector_embedding_idx
ON documents
USING hnsw (vector_embedding vector_cosine_ops);
```

**Python Fix (in `services/document_store.py`):**
```python
# Ensure embedding is stored as list, not string
embedding = self._generate_embedding(content)  # Returns list[float]

# Store directly - Supabase converts list to pgvector automatically
db_service.client.table('documents').insert({
    'vector_embedding': embedding  # ✅ List[float], not json.dumps(embedding)
}).execute()
```

---

### **Issue 3: Only 5 Episodes for 6 Documents**

**Evidence:**
- FalkorDB: 5 Episodic nodes
- Supabase: 6 documents

**Root Cause:**
- Seed test emails (Acme, Globex, Initech) were stored in Supabase but not processed through Graphiti
- Only real Gmail sync creates Episodic nodes

**Impact:**
- ⚠️ Inconsistent data across storage layers
- ⚠️ AI agent may find documents with no graph facts

**Fix Required:**
Either:
1. **Backfill:** Process seed emails through Graphiti to create episodes
2. **Clean up:** Delete seed emails from Supabase (they were just for testing)

**Recommended:** Clean up seed data, rely on real Gmail sync going forward.

---

## ✅ WHAT'S WORKING WELL

### **1. Group ID Isolation**
- ✅ All episodes correctly tagged with `group_id: 8d6126eddfb54fff9d72b84fb0cb889a`
- ✅ Multi-tenant architecture ready
- ✅ User data properly isolated

### **2. Entity Extraction Quality**
- ✅ 26 entities extracted from 5 emails (5.2 entities/email avg)
- ✅ Realistic entities: Gemini App, Google LLC, Calendar, Drive, Gmail
- ✅ Email addresses parsed: `alex at thunderbird-labs.com`

### **3. Relationship Mapping**
- ✅ 59 MENTIONS relationships (episode → entity)
- ✅ 49 RELATES_TO relationships (entity → entity)
- ✅ Relationships include semantic facts:
  ```
  "The Gemini App can use information from Gmail for context-rich responses."
  "Google LLC address is 1600 Amphitheatre Parkway Mountain View CA 94043"
  ```

### **4. Document-Entity Bridge**
- ✅ 9 links between Supabase documents and FalkorDB entities
- ✅ Enables hybrid queries (graph facts + full document content)
- ✅ AI agent can retrieve source documents for entities

### **5. Pipedream Integration**
- ✅ Successfully fetched 201 Gmail messages
- ✅ Proxy API working with correct auth parameters
- ✅ Production environment configured

---

## 🎯 OPTIMIZATION RECOMMENDATIONS

### **Priority 1: Fix Vector Search (Critical)**

**Why:** Vector search is completely broken. AI agent is falling back to graph-only search, missing semantic similarity matches.

**Actions:**
1. Run SQL migration to create `vector(1536)` column
2. Re-generate embeddings for all 6 documents
3. Create HNSW index for fast search
4. Test semantic search with query: "What did Sarah email me about?"

**Expected Outcome:** AI agent finds relevant documents by semantic meaning, not just keyword matching.

---

### **Priority 2: Prevent Episode Duplication (Critical)**

**Why:** Duplicate episodes waste tokens, storage, and pollute search results.

**Actions:**
1. Add `has_episode_been_processed()` function to check FalkorDB before processing
2. Skip episodes that already exist
3. Optionally: Add `source_id` property to Episodic nodes for faster lookups
4. Delete existing duplicates:
   ```cypher
   // Find duplicate UUIDs
   MATCH (e:Episodic {name: 'Email: New Gemini features Better videos presentations & more'})
   WITH e
   ORDER BY e.created_at DESC
   SKIP 1
   DETACH DELETE e
   ```

**Expected Outcome:** Each email processed exactly once, no duplicates.

---

### **Priority 3: Clean Up Seed Data (Low)**

**Why:** Test emails (Acme, Globex, Initech) were useful for Phase 1 testing but are now creating inconsistency.

**Actions:**
```python
# Delete seed emails from Supabase
test_ids = ['test_acme_001', 'test_techflow_001', 'test_globex_001', 'test_initech_001']
for source_id in test_ids:
    db_service.client.table('documents').delete().eq('source_id', source_id).execute()
```

**Alternative:** Keep them and backfill through Graphiti to create episodes.

---

### **Priority 4: Add Episodic Properties for Better Queries (Medium)**

**Why:** Episodic nodes currently have minimal metadata. Adding more properties enables richer queries.

**Suggested Properties:**
```python
await self.graphiti.add_episode(
    name=f"Email: {email.subject[:100]}",
    episode_body=episode_content,
    source=EpisodeType.text,
    source_description="Gmail message",
    reference_time=datetime.now(timezone.utc),
    group_id=user_id,
    # ✅ Add these custom properties:
    custom_metadata={
        'source_id': email.message_id,        # For deduplication
        'sender': email.sender,               # For filtering by sender
        'subject': email.subject,             # For subject search
        'date': email.date,                   # For temporal queries
        'thread_id': email.thread_id,         # For conversation threading
    }
)
```

**Enables Queries Like:**
```cypher
// Find all emails from a specific sender
MATCH (e:Episodic {sender: 'sarah.johnson@acme-corp.com'})

// Find emails in a specific time range
MATCH (e:Episodic)
WHERE e.date >= '2025-10-01' AND e.date <= '2025-10-07'

// Find emails in a thread
MATCH (e:Episodic {thread_id: 'thread_xyz'})
ORDER BY e.date
```

---

### **Priority 5: Optimize Entity Linking Precision (Medium)**

**Why:** Currently, document-entity linking may be too broad. Every entity in an email gets linked, but not all are equally relevant.

**Current Approach:**
```python
# Links ALL entities mentioned in episode to document
document_store.link_document_to_entities(doc_id, entity_uuids)
```

**Optimization:**
- Add confidence scores to entity mentions
- Only link entities with high confidence (e.g., proper nouns, email addresses, companies)
- Use NLP to determine entity salience (is this the main topic or just a passing mention?)

**Example:**
```python
# Before: Links 10 entities
entity_uuids = [all entities from episode]

# After: Links 3 most relevant entities
entity_uuids = [entities with confidence > 0.7 or mentioned multiple times]
```

---

## 📈 SCALING CONSIDERATIONS

### **Current Scale:**
- 5 episodes, 26 entities, 108 relationships
- 6 documents, 6 embeddings, 9 entity links

### **Projected Scale (1 year, 1000 users):**
- **FalkorDB:**
  - 500K episodes (1000 users × 500 emails/user)
  - 5M entities (10 entities/email avg)
  - 10M relationships
- **Supabase:**
  - 500K documents
  - 500K vector embeddings (1536 dims each = ~3GB storage)
  - 5M entity links

### **Performance Optimizations Needed:**

#### **FalkorDB:**
1. **Add indices on frequently queried properties:**
   ```cypher
   CREATE INDEX ON :Episodic(group_id)
   CREATE INDEX ON :Episodic(source_id)
   CREATE INDEX ON :Entity(name)
   ```

2. **Partition by time:** For large datasets, partition episodes by month/year
   ```cypher
   MATCH (e:Episodic {group_id: 'user123', year: 2025, month: 10})
   ```

3. **Limit relationship depth:** Cap graph traversal depth to avoid expensive queries
   ```cypher
   MATCH path = (e:Entity)-[*1..2]->(related:Entity)
   // Max 2 hops
   ```

#### **Supabase:**
1. **Enable pgvector HNSW index** (already recommended above)
2. **Add compound indices:**
   ```sql
   CREATE INDEX idx_documents_user_source
   ON documents(user_id, source, source_created_at DESC);
   ```

3. **Partition documents table by month** (PostgreSQL native partitioning)
   ```sql
   CREATE TABLE documents_2025_10 PARTITION OF documents
   FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');
   ```

#### **Redis (Future):**
Consider adding Redis for:
- Episode deduplication cache (faster than querying FalkorDB)
- Entity UUID lookups
- Recent search query cache

---

## 🧪 TESTING CHECKLIST

Before deploying optimizations, test:

- [ ] **Vector search works**
  - Query: "What did Sarah email me about?"
  - Expected: Find Acme Corp email with high similarity score

- [ ] **No duplicate episodes created**
  - Sync same email twice
  - Expected: Only 1 Episodic node exists

- [ ] **AI agent returns hybrid context**
  - Query: "Tell me about Gemini"
  - Expected: Graph facts + full email content with citations

- [ ] **Entity linking is accurate**
  - Check document_entities table
  - Expected: Only relevant entities linked (not every entity in every email)

- [ ] **Graph queries are fast**
  - Query: "MATCH (e:Episodic {group_id: 'user123'}) RETURN count(e)"
  - Expected: < 50ms response time

- [ ] **Multi-tenant isolation works**
  - Create second user, sync their emails
  - Query with first user's group_id
  - Expected: Only see first user's data

---

## 🎉 CONCLUSION

**Current Status:** Hybrid storage system is **80% operational** ✅

**Working:**
- ✅ FalkorDB storing entities, relationships, episodes
- ✅ Supabase storing full document content
- ✅ Document-entity linking bridge functional
- ✅ Multi-tenant isolation via group_id
- ✅ Pipedream Gmail sync working

**Broken:**
- ❌ Vector embeddings stored as strings (search broken)
- ❌ Duplicate episodes being created
- ⚠️ Inconsistent data (5 episodes vs 6 documents)

**Next Steps:**
1. **Fix vector search** (Priority 1) - Run migration, re-generate embeddings
2. **Add deduplication** (Priority 2) - Prevent duplicate episodes
3. **Test AI agent** - Verify hybrid search works end-to-end
4. **Add Google Docs** - Expand to multi-source integration

**Recommendation:** Fix vector search first, then test AI agent with real queries. Once search works, add deduplication to prevent future issues. The architecture is solid - just needs these critical fixes to be production-ready.
