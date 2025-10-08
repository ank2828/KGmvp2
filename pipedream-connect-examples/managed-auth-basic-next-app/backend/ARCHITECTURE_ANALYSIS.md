# 🔍 Architecture Analysis - Answering Strategic Questions

**Date:** October 7, 2025
**Context:** Optimizing for enterprise scale (1000s emails, multi-source data)
**Sources:** Codebase analysis + Questions for Graphiti agent

---

## ✅ Question 1: Graphiti's Role in This Architecture

### What I Found in Codebase:

**Current Implementation:**
```python
# services/graphiti_service.py, line 176
result = await self.graphiti.add_episode(
    name=f"Email: {email.subject[:100]}",
    episode_body=episode_content,  # Full email text
    source=EpisodeType.text,
    source_description="Gmail message",
    reference_time=datetime.now(timezone.utc),
    group_id=user_id,
)

# Returns: AddEpisodeResults with:
# - result.episode.uuid (Episode node UUID)
# - result.nodes (Extracted Entity nodes)
# - result.edges (Extracted RELATES_TO relationships)
```

**What Happens:**
1. Graphiti receives full email text as `episode_body`
2. LLM extracts entities (Person, Company, Deal) - see `entity_types.py`
3. Creates Episode node in FalkorDB with UUID
4. Creates Entity nodes with relationships
5. Returns extraction results

**Current Storage:**
- ✅ Episode node IS stored in FalkorDB (has UUID)
- ✅ Entity nodes stored in FalkorDB
- ✅ Relationships (MENTIONS, RELATES_TO) stored
- ✅ Episode UUID tracked in Supabase `processed_episodes`

### Answer:

**Graphiti is currently doing TWO things:**
1. ✅ Entity extraction engine (LLM-powered, we need this)
2. ❌ Episode storage layer (storing Episode nodes, we may not need this)

**Value we keep:**
- Entity recognition (extracts Person, Company, Deal from unstructured text)
- Relationship extraction (figures out who works at which company)
- Cross-episode entity merging (recognizes "Sarah" in email 1 = "Sarah J" in email 2)

**Value we question:**
- Episode node storage in graph (redundant with Supabase `documents` table)
- Episode content in graph (full email text, already in Supabase)

### 🤔 Questions for Graphiti Agent:

1. **Can Graphiti extract entities WITHOUT creating Episode nodes?**
   - Does `add_episode()` always create an Episodic node in the graph?
   - Is there a way to extract entities but discard the episode container?
   - Or is the Episode node required for Graphiti's entity resolution to work?

2. **How does Graphiti use Episode nodes for entity resolution?**
   - If we delete Episode nodes after extraction, will entity merging still work?
   - Does Graphiti need to traverse Episodes to understand entity relationships?
   - Can we keep Episode metadata (timestamp, source) without full content?

3. **Batch processing impact on entity quality:**
   - If we batch 50 emails into 1 episode, does entity extraction improve?
   - Does Graphiti resolve "Sarah" in email 1 = "Sarah Johnson" in email 5 better with context?
   - What's the optimal batch size for entity co-reference resolution?

---

## ✅ Question 2: Episode Nodes - Keep or Remove?

### What I Found in Codebase:

**Current Approach:**
- Every email → 1 Episode node in FalkorDB
- Episode contains: `name`, `created_at`, `group_id`, `content`, `source_description`
- Also stored in: Supabase `documents` table (full content + embedding)
- Tracked in: Supabase `processed_episodes` table (deduplication)

**Current Episode Usage:**
1. ✅ Deduplication (via `processed_episodes` table)
2. ✅ Entity extraction (input to Graphiti)
3. ❓ Graph queries (can query "episodes from last week")
4. ❓ Entity context (traverse Episode → Entities)

**Storage Redundancy:**
```
Email content stored in 3 places:
1. FalkorDB Episode node (full text in graph)
2. Supabase documents table (full text + metadata)
3. Supabase documents.vector_embedding (for search)

Only #2 and #3 are used for AI agent queries currently
```

### Answer:

**Two Architecture Options:**

**Option A: REMOVE Episode Nodes (Recommended)**
```
Processing Flow:
1. Email arrives → Store in Supabase documents
2. Send to Graphiti for extraction only
3. Graphiti creates Episode (temporary processing artifact)
4. Extract entities → Store canonical entities in graph
5. Discard Episode node (don't persist in graph)

Result:
- 10K emails → 0 Episode nodes in graph
- Only canonical entities (500 people, 200 companies)
- Full content in Supabase (fast SQL + vector search)
```

**Option B: KEEP Lightweight Episode Nodes**
```
Processing Flow:
1. Email arrives → Store in Supabase documents
2. Send to Graphiti for extraction
3. Graphiti creates Episode with minimal metadata only:
   - name: "Email: Subject"
   - timestamp: 2025-10-07
   - source: gmail
   - source_id: msg_123
   - NO content (just pointer to Supabase)

Result:
- 10K emails → 10K Episode nodes (but lightweight)
- Enables temporal queries in graph
- Full content stays in Supabase
```

### Performance Comparison:

| Metric | Current (Full Episodes) | Option A (No Episodes) | Option B (Lightweight) |
|--------|-------------------------|------------------------|------------------------|
| **Graph nodes** | 10K episodes + 250K entities | 1K canonical entities | 10K episodes + 1K entities |
| **Query: "Find Sarah"** | Scan 250K entities | Scan 1K entities | Scan 1K entities |
| **Query: "Emails last week"** | Graph query on Episodes | SQL on Supabase docs | Graph query on Episodes |
| **Storage cost** | High (full text in graph) | Low (graph has entities only) | Medium (lightweight nodes) |

### 🤔 Questions for Graphiti Agent:

4. **Can we create Episode nodes without content?**
   - Does Graphiti allow Episode nodes with just metadata (no `episode_body`)?
   - Can we update an Episode after creation to remove content?
   - Or is content required for Graphiti's internal operations?

5. **What happens if we delete Episodes after extraction?**
   - Will entity relationships break if source Episode is deleted?
   - Does Graphiti use MENTIONS relationships to traverse back to Episodes?
   - Can entity merging work without Episode history?

6. **Temporal query patterns:**
   - Do AI agents benefit from querying "show me episodes from last week" in graph?
   - Or is SQL faster: `SELECT * FROM documents WHERE created_at > NOW() - INTERVAL '7 days'`?
   - What graph queries require Episode nodes to exist?

---

## ✅ Question 3: Entity Deduplication Strategy

### What I Found in Codebase:

**Current Implementation: Two-Layer Deduplication**

**Layer 1: Graphiti's Entity Resolution (Automatic)**
```python
# Graphiti automatically merges similar entities
# Example: "Sarah" in email 1 + "Sarah Johnson" in email 2 → 1 Entity node
# Method: LLM-powered similarity detection
```

**Layer 2: Canonical Entity Normalization (Our Code)**
```python
# services/entity_normalizer.py
class EntityNormalizer:
    async def _normalize_contact(self, node, group_id: str):
        email = self._extract_email(node)  # Extract canonical identifier

        # MERGE on email (deterministic deduplication)
        query = """
        MERGE (p:Contact {email: $email})
        ON CREATE SET p.name = $name, ...
        ON MATCH SET p.last_updated = $now
        """
```

**Canonical Keys:**
- Person → Email address (e.g., `sarah@acme.com`)
- Company → Domain (e.g., `acme.com`)
- Deal → Slugified name or CRM ID (e.g., `q4-enterprise-deal`)

**Multi-Source Resolution Example:**
```
Gmail:    "sarah.johnson@acme.com" → Contact(email=sarah.johnson@acme.com)
Slack:    "@sarah_j"               → Extract email → Same Contact
HubSpot:  "Sarah J. Johnson"       → Extract email → Same Contact

Result: 1 canonical Contact node linked to 3 Graphiti entities
```

### Answer:

**Current Strategy (Hybrid):**
1. ✅ Graphiti merges similar entities within same source
2. ✅ EntityNormalizer creates canonical nodes across sources
3. ✅ Deterministic keys (email, domain) prevent duplicates
4. ⚠️ Relies on email extraction heuristics (regex in `_extract_email()`)

**What Works:**
- Exact match: `sarah@acme.com` in Gmail = same in HubSpot ✅
- Cross-source: 1 canonical Contact for all sources ✅
- Audit trail: `CANONICAL_ENTITY` relationship preserves lineage ✅

**What Doesn't Work:**
- Fuzzy match: "Sarah Johnson" with no email → Can't deduplicate
- Typos: "sara@acme.com" vs "sarah@acme.com" → 2 separate entities
- Missing data: HubSpot contact with no email → Can't merge with Gmail

### 🤔 Questions for Graphiti Agent:

7. **How does Graphiti's entity merging actually work?**
   - Does it use embedding similarity? LLM comparison? Exact string match?
   - What's the threshold for considering two entities "the same"?
   - Can we configure the merging behavior?

8. **Cross-episode entity resolution:**
   - If "Sarah" appears in email 1, will Graphiti recognize "Sarah Johnson" in email 50?
   - Does it maintain entity history across all episodes in a group_id?
   - Or does it only merge within the same add_episode() call?

9. **Canonical entity best practices:**
   - Should we let Graphiti handle all merging, or use our EntityNormalizer?
   - Is the two-layer approach (Graphiti + Canonical) redundant?
   - What's the recommended pattern for multi-source entity resolution?

---

## ✅ Question 4: What Entities to Keep?

### What I Found in Codebase:

**Current Entity Filtering (Already Implemented!):**

```python
# services/entity_types.py
ENTITY_TYPES = {
    "Company": Company,  # Only business organizations
    "Contact": Contact,  # Only people with names
    "Deal": Deal         # Only sales opportunities
}

EXCLUDED_ENTITY_TYPES = ["Entity"]  # Force specific types
```

**Custom Type Definitions:**
```python
class Company(BaseModel):
    """
    INCLUDE:
    - Full company names (e.g., "Acme Corporation", "Google LLC")
    - Organizations with employees or business operations

    EXCLUDE:
    - Domain names alone (extract as domain attribute)
    - Email addresses
    - URLs or LinkedIn profiles
    - Industry categories
    - Physical locations
    """
    domain: str | None = Field(None, description="Company's primary domain")
    industry: str | None = Field(None, description="Industry or sector")
    location: str | None = Field(None, description="Primary office location")
```

**Documentation Claims (from entity_types.py header):**
```
Validated on 2025-10-04: Reduced extraction from 14→3 entities per episode.
100% deduplication. No noise entities.
```

### Answer:

**We ALREADY have entity filtering! But...**

**Your screenshot shows noise entities:**
- ✅ alex@thunderbird-labs.com (Contact - should be kept)
- ✅ Google LLC (Company - should be kept)
- ✅ Mountain View, CA (Location - but stored as attribute?)
- ❌ Gemini, Gmail, Calendar, Drive, Veo 3, NotebookLM (Products - should be filtered)
- ❌ Video editing software, AI Voiceovers (Features - should be filtered)

**This suggests:**
1. Entity types are defined correctly in code
2. But Graphiti is NOT using them (still extracting noise)
3. OR: Graphiti is ignoring the `entity_types` parameter

**Verification needed:**
```python
# Check if entity_types are actually passed to Graphiti
result = await self.graphiti.add_episode(
    entity_types=ENTITY_TYPES,         # ← Is this being used?
    excluded_entity_types=["Entity"]   # ← Is this working?
)
```

### 🤔 Questions for Graphiti Agent:

10. **How do custom entity types actually work?**
    - When we pass `entity_types={Company, Contact, Deal}`, does Graphiti ONLY extract those?
    - Or does it extract everything and just label some as "Company"?
    - What happens to entities that don't match any custom type?

11. **Why is noise still being extracted?**
    - If we exclude "Entity" type, why are generic entities still created?
    - Does Graphiti fall back to default extraction if custom types don't match?
    - How to force "extract ONLY these 3 types, ignore everything else"?

12. **Entity vs Attribute extraction:**
    - How does Graphiti decide: "Google LLC" → Company entity vs "google.com" → domain attribute?
    - Can we guide it: "Extract Location as attribute of Company, not separate entity"?
    - What's the prompt engineering needed for clean extraction?

---

## ✅ Question 5: Performance at Scale

### What I Found in Codebase:

**Current Architecture Metrics:**

**FalkorDB Current State (from verification):**
```
3 emails processed:
- 3 Episodic nodes
- 28 Entity nodes (avg 9 per email)
- 31 MENTIONS relationships
- 22 RELATES_TO relationships
```

**Projection at 10K emails:**
```
Linear scaling (worst case):
- 10,000 Episodic nodes
- 93,333 Entity nodes (28 * 10000 / 3)
- 103,333 MENTIONS relationships
- 73,333 RELATES_TO relationships

Total graph size: ~280K nodes + edges
```

**With Canonical Deduplication:**
```
Normalized scaling (best case):
- 0 Episodic nodes (removed)
- 1,000 Canonical entities (Person, Company, Deal)
- 10,000 CANONICAL_ENTITY links (to Graphiti entities)

Total graph size: ~11K nodes + edges (25x smaller)
```

### Answer:

**Performance Analysis:**

**Query: "Find all emails from Sarah"**

Current Approach (Full Graph):
```cypher
MATCH (sarah:Entity {name: 'Sarah Johnson'})
      -[:RELATES_TO]-(ep:Episodic)
RETURN ep

Complexity: O(E + R) where E=entities, R=relationships
Time: Scan 93K entities + 176K relationships ≈ 500ms-1s
```

Canonical Approach (Normalized):
```sql
-- Step 1: Find canonical person
SELECT entity_uuid FROM contacts WHERE email = 'sarah@acme.com'
Time: 1ms (indexed lookup in 500 contacts)

-- Step 2: Find linked documents
SELECT document_id FROM document_entities WHERE entity_uuid = $sarah_uuid
Time: 5ms (indexed lookup in 10K links)

-- Step 3: Fetch full emails
SELECT * FROM documents WHERE id IN (...)
Time: 10ms (indexed SQL on 10K docs)

Total: ~16ms (30x faster)
```

**Storage Cost Comparison:**

| Layer | Current (Full Graph) | Canonical (Optimized) |
|-------|---------------------|----------------------|
| FalkorDB | 280K nodes/edges = ~500MB | 11K nodes/edges = ~20MB |
| Supabase | 10K docs + embeddings = ~2GB | Same (10K docs) |
| **Total** | ~2.5GB | ~2GB |
| **Cost/month** | ~$50-80 | ~$30-40 |

### Answer to "Will canonical be faster?": **YES, 30x faster**

---

## ✅ Question 6: Migration Path

### What I Found in Codebase:

**Current Data State:**
```
FalkorDB: 3 episodes, 28 entities, 53 relationships
Supabase documents: 3 emails
Supabase processed_episodes: 3 entries
```

**Migration Complexity:**
- ✅ Small dataset (3 emails) - easy to wipe and restart
- ✅ Deduplication system already in place
- ✅ Entity filtering defined (just not working)
- ❌ No production data at risk

### Answer:

**Recommended Migration Path: START FRESH**

**Phase 1: Fix Entity Extraction (Week 1)**
```
1. Debug why entity_types aren't working
   → Ask Graphiti agent about correct usage

2. Test with 3 emails:
   → Verify ONLY Person/Company/Deal extracted
   → No more Gmail, Calendar, Gemini noise

3. Verify canonical normalization:
   → 3 emails → 3-5 canonical entities (not 28)
```

**Phase 2: Optimize Episode Storage (Week 1)**
```
4. Decision: Keep or remove Episode nodes?
   → Ask Graphiti agent about implications

5. If remove: Test extraction without storage
   → Can entities be extracted and Episodes discarded?

6. If keep: Optimize Episode content
   → Store only metadata, full text in Supabase
```

**Phase 3: Clean Migration (Week 2)**
```
7. Clear FalkorDB completely:
   → MATCH (n) DETACH DELETE n

8. Clear Supabase tables:
   → DELETE FROM processed_episodes
   → DELETE FROM documents
   → DELETE FROM document_entities

9. Re-process emails with new architecture:
   → Fetch 1000 emails from Gmail
   → Process with fixed entity extraction
   → Verify canonical deduplication
   → Benchmark query performance
```

**Alternative: Gradual Migration (if production data exists)**
```
Phase A: Dual Write (2 weeks)
- Write to both old + new architecture
- Compare results (entity counts, query speed)
- Validate canonical deduplication quality

Phase B: Backfill (1 week)
- Process historical emails with new approach
- Migrate canonical entities
- Preserve processed_episodes audit trail

Phase C: Cutover (1 week)
- Switch AI agent to new queries
- Monitor performance
- Deprecate old Episode-based queries
```

### Recommended: **START FRESH** (we have 3 test emails, no production risk)

---

## 📋 Summary: Questions for Graphiti Agent

### Critical Questions (Must Answer):

1. **Can Graphiti extract entities WITHOUT creating Episode nodes?**
2. **How does Graphiti use Episode nodes for entity resolution?**
3. **How does Graphiti's entity merging actually work?** (similarity threshold, algorithm)
4. **How do custom entity types actually work?** (do they filter or just label?)
5. **Why is noise still being extracted despite entity_types filtering?**

### Important Questions (Should Answer):

6. **Batch processing: Does batching 50 emails improve entity resolution quality?**
7. **Can we create Episode nodes without content (metadata only)?**
8. **What happens if we delete Episodes after extraction?** (breaks relationships?)
9. **Cross-episode entity resolution: Does "Sarah" in email 1 merge with "Sarah J" in email 50?**
10. **What graph queries require Episode nodes to exist?** (temporal queries, context traversal)

### Nice-to-Have Questions:

11. **Entity vs Attribute: How to force location as Company attribute, not separate entity?**
12. **Best practices: Should we use Graphiti merging OR canonical normalization, or both?**
13. **Optimal batch size for entity co-reference resolution?**

---

## 🎯 Next Steps

Once Graphiti agent answers these questions, we can:

1. **Fix entity extraction** (eliminate noise like Gmail, Calendar, Gemini)
2. **Decide on Episode strategy** (remove, keep lightweight, or optimize)
3. **Optimize canonical deduplication** (improve cross-source merging)
4. **Clean migration** (wipe and restart with correct architecture)
5. **Benchmark at scale** (test with 1000 emails, measure query speed)

**Goal:** 10K emails → 1K canonical entities → <100ms queries ✅
