# 🌐 Multi-Source Knowledge Graph Schema Design

**Purpose:** Define node types, relationships, and metadata for scaling to multiple data sources (Gmail, Slack, HubSpot, Google Docs, Notion, etc.)

**Date:** October 7, 2025
**Status:** Design Document (Implementation in Progress)

---

## 🎯 Design Principles

### **1. Source Agnostic**
- Same entity (e.g., "Sarah Johnson") appears across Gmail, Slack, Notion
- Need entity resolution to merge cross-app mentions

### **2. Webhook Ready**
- Live data streaming via webhooks (not just batch syncs)
- Idempotency for webhook retries
- Real-time updates to knowledge graph

### **3. Scalable**
- 1000s of users, 100Ks of documents
- Fast queries with indices
- Efficient storage (don't duplicate data)

---

## 📊 Entity Type Taxonomy

### **Core Entity Types**

| Entity Type | Description | Sources | Example |
|-------------|-------------|---------|---------|
| **Person** | Individuals (contacts, colleagues) | Gmail, Slack, HubSpot, LinkedIn | "Sarah Johnson" |
| **Company** | Organizations | Gmail, HubSpot, LinkedIn, Crunchbase | "Acme Corp" |
| **Deal** | Sales opportunities | HubSpot, emails, CRM | "Q4 Enterprise License - $50K" |
| **Document** | Files and content | Google Docs, Notion, Confluence | "Product Roadmap Q4 2025" |
| **Project** | Work initiatives | Notion, Asana, Jira | "Website Redesign" |
| **Event** | Meetings, deadlines | Google Calendar, Slack events | "Demo with Acme - Oct 15" |

### **Entity Properties (Graphiti Standard)**

All entities created by Graphiti have these built-in properties:

```cypher
(entity:Entity {
    uuid: "entity_abc123",           // Graphiti UUID
    name: "Sarah Johnson",           // Entity name
    summary: "VP of Sales at Acme Corp, interested in enterprise features",
    created_at: "2025-10-07T...",
    group_id: "8d6126ed..."          // User isolation
})
```

### **Custom Labels (Graphiti Feature)**

Graphiti can add custom labels like `Company`, `Contact`, `Deal` to entities:

```cypher
// Person entity with Contact label
(entity:Entity:Contact {
    name: "Sarah Johnson",
    summary: "VP of Sales at Acme Corp"
})

// Company entity with Company label
(entity:Entity:Company {
    name: "Acme Corp",
    summary: "Enterprise SaaS company, 500+ employees"
})
```

---

## 📝 Episodic Type Taxonomy

### **Episode Types by Source**

| Source | Episode Type | Content | Metadata |
|--------|--------------|---------|----------|
| **Gmail** | Email | Subject + Body + Sender | from, to, date, thread_id, labels |
| **Slack** | SlackMessage | Message text + Channel | channel, user, thread_ts, reactions |
| **Google Docs** | DocEdit | Document title + content | doc_id, editor, last_modified, version |
| **Notion** | NotionPage | Page title + blocks | page_id, workspace, created_by |
| **HubSpot** | HubSpotActivity | Deal update, note, call | object_type, object_id, activity_type |
| **Google Calendar** | CalendarEvent | Meeting title + attendees | event_id, start_time, location |
| **Linear** | LinearIssue | Issue title + description | issue_id, status, assignee, priority |

### **Episode Properties**

Episodes in FalkorDB have these properties:

```cypher
(episode:Episodic {
    uuid: "episode_xyz789",                    // Graphiti UUID
    name: "Email: Q4 Enterprise Deal Update",  // Episode name
    created_at: "2025-10-07T...",
    group_id: "8d6126ed...",                   // User isolation
    content: "Full email body text...",        // Full content
    source_description: "Gmail message"        // Source type
})
```

### **Custom Metadata (Planned Enhancement)**

To enable richer queries, we should add source-specific metadata:

```cypher
// Gmail episode with metadata
(ep:Episodic {
    uuid: "...",
    name: "Email: Q4 Enterprise Deal Update",
    source: "gmail",                    // NEW: Source identifier
    source_id: "msg_abc123",            // NEW: Gmail message ID
    source_url: "https://mail.google.com/...",  // NEW: Deep link
    sender: "sarah.johnson@acme-corp.com",      // NEW: Email from
    recipients: ["alex@company.com"],           // NEW: Email to
    timestamp: "2025-10-07T14:30:00Z",         // NEW: Email date
    thread_id: "thread_xyz"                    // NEW: Gmail thread
})

// Slack episode with metadata
(ep:Episodic {
    uuid: "...",
    name: "Slack: Deal update in #sales",
    source: "slack",                    // Source identifier
    source_id: "1698765432.123456",     // Slack timestamp
    source_url: "https://workspace.slack.com/...",
    channel: "#sales",                  // Slack channel
    user: "sarah_johnson",              // Slack user
    thread_ts: "1698765400.123000",     // Thread parent
    reactions: ["thumbsup", "fire"]     // Reactions
})
```

**Note:** Graphiti currently doesn't support custom properties on episodes. This is a future enhancement we can request or implement via custom post-processing.

---

## 🔗 Relationship Taxonomy

### **Built-in Graphiti Relationships**

| Relationship | Direction | Description | Example |
|--------------|-----------|-------------|---------|
| **MENTIONS** | Episode → Entity | Episode references entity | Email → Sarah Johnson |
| **RELATES_TO** | Entity → Entity | Entities are connected | Acme Corp → Sarah Johnson |

### **Semantic Facts (Graphiti Feature)**

The `RELATES_TO` relationships include natural language facts:

```cypher
(sarah:Entity {name: "Sarah Johnson"})-[r:RELATES_TO {
    fact: "Sarah Johnson is VP of Sales at Acme Corp",
    valid_at: "2025-10-07T..."
}]->(acme:Entity {name: "Acme Corp"})

(acme:Entity {name: "Acme Corp"})-[r:RELATES_TO {
    fact: "Acme Corp is interested in Q4 enterprise license pricing",
    valid_at: "2025-10-07T..."
}]->(deal:Entity {name: "Q4 Enterprise License"})
```

### **Temporal Relationships (Future)**

For time-based queries:

```cypher
// Find all deals discussed in the last 30 days
MATCH (ep:Episodic)-[:MENTIONS]->(deal:Entity:Deal)
WHERE ep.timestamp >= datetime() - duration({days: 30})
RETURN deal
```

---

## 🗄️ Storage Architecture

### **Hybrid Storage Model**

```
┌─────────────────────────────────────────────────────────┐
│                    USER DATA INPUT                       │
│  (Gmail, Slack, HubSpot, Docs via Pipedream Webhooks)  │
└────────────────────┬────────────────────────────────────┘
                     │
                     ├──────────────────┬──────────────────┐
                     ▼                  ▼                  ▼
        ┌────────────────────┐ ┌──────────────┐ ┌─────────────────┐
        │  SUPABASE          │ │  FALKORDB    │ │  PROCESSED      │
        │  (Documents)       │ │  (Graph)     │ │  EPISODES       │
        ├────────────────────┤ ├──────────────┤ ├─────────────────┤
        │ • Full content     │ │ • Entities   │ │ • Deduplication │
        │ • Metadata         │ │ • Facts      │ │ • Multi-source  │
        │ • Vector embeddings│ │ • MENTIONS   │ │ • Audit trail   │
        │ • Semantic search  │ │ • RELATES_TO │ │ • Idempotency   │
        └────────────────────┘ └──────────────┘ └─────────────────┘
                     ▲                  ▲                  ▲
                     │                  │                  │
                     └──────────────────┴──────────────────┘
                                        │
                                        ▼
                            ┌────────────────────────┐
                            │   AI AGENT (GPT-4)     │
                            │   Hybrid Search:       │
                            │   • Graph facts        │
                            │   • Full documents     │
                            │   • Semantic search    │
                            └────────────────────────┘
```

### **Data Flow**

```
1. Webhook arrives (Gmail, Slack, etc.)
   ↓
2. Check processed_episodes (deduplication)
   ├─ Already processed? → Skip
   └─ New? → Continue
   ↓
3. Store in Supabase documents
   ├─ Full content
   ├─ Generate vector embedding
   └─ Store metadata
   ↓
4. Process through Graphiti
   ├─ Extract entities (GPT-4)
   ├─ Extract relationships (GPT-4)
   ├─ Create Episode node
   ├─ Create/update Entity nodes
   └─ Create MENTIONS relationships
   ↓
5. Link Supabase ↔ FalkorDB
   ├─ document_entities table
   └─ Enables hybrid queries
   ↓
6. Mark as processed
   └─ processed_episodes table
```

---

## 🔍 Query Patterns

### **1. Find All Mentions of a Person**

```cypher
// Find all episodes mentioning Sarah Johnson
MATCH (ep:Episodic)-[:MENTIONS]->(entity:Entity {name: "Sarah Johnson"})
RETURN ep.name, ep.timestamp
ORDER BY ep.timestamp DESC
LIMIT 10
```

### **2. Find Related Entities**

```cypher
// Find all entities related to a deal
MATCH (deal:Entity:Deal {name: "Q4 Enterprise License"})
       -[r:RELATES_TO]-(related:Entity)
RETURN related.name, r.fact
```

### **3. Temporal Queries (Requires Metadata Enhancement)**

```cypher
// Find all Slack messages from last week
MATCH (ep:Episodic {source: "slack"})
WHERE ep.timestamp >= datetime() - duration({days: 7})
RETURN ep.name, ep.channel, ep.user
ORDER BY ep.timestamp DESC
```

### **4. Multi-Source Entity Tracking**

```cypher
// Find all sources mentioning a company
MATCH (ep:Episodic)-[:MENTIONS]->(company:Entity:Company {name: "Acme Corp"})
RETURN ep.source, count(ep) as mention_count
ORDER BY mention_count DESC
```

---

## 🛠️ Entity Resolution Strategy

### **Problem: Same Entity, Different Names**

```
Gmail:   "Sarah Johnson" <sarah.johnson@acme-corp.com>
Slack:   "@sarah_j"
HubSpot: "Sarah J. Johnson"
Notion:  "Sarah"
```

### **Solution: Graphiti Entity Merging**

Graphiti uses LLM-powered entity resolution to merge similar entities:

1. **Extract entities** from each episode
2. **Semantic matching** via embeddings
3. **Merge entities** if similarity > threshold
4. **Update relationships** to point to merged entity

**Example:**
```cypher
// Before: 3 separate entities
(entity1:Entity {name: "Sarah Johnson"})
(entity2:Entity {name: "Sarah J"})
(entity3:Entity {name: "@sarah_j"})

// After: 1 merged entity
(entity:Entity {
    name: "Sarah Johnson",
    summary: "VP of Sales at Acme Corp, Slack: @sarah_j, Email: sarah.johnson@acme-corp.com"
})
```

### **Entity Resolution Configuration**

In `graphiti_service.py`, configure entity merging:

```python
# Graphiti automatically handles entity resolution
# You can configure similarity threshold in Graphiti settings
result = await self.graphiti.add_episode(
    name=f"Email: {email.subject}",
    episode_body=episode_content,
    # Graphiti will merge entities with high similarity
)
```

---

## 📈 Scaling Considerations

### **Performance at Scale**

| Metric | 1 User | 100 Users | 1000 Users |
|--------|--------|-----------|------------|
| **Episodes** | 500 | 50K | 500K |
| **Entities** | 5K | 500K | 5M |
| **Relationships** | 10K | 1M | 10M |
| **Documents** | 500 | 50K | 500K |
| **Embeddings** | 500 | 50K | 500K |

### **Optimizations Needed**

1. **FalkorDB Indices**
   ```cypher
   CREATE INDEX ON :Episodic(group_id, timestamp)
   CREATE INDEX ON :Episodic(source, source_id)
   CREATE INDEX ON :Entity(name, group_id)
   ```

2. **Supabase Partitioning**
   ```sql
   -- Partition documents by month
   CREATE TABLE documents_2025_10 PARTITION OF documents
   FOR VALUES FROM ('2025-10-01') TO ('2025-11-01');
   ```

3. **Redis Caching**
   ```python
   # Cache entity lookups
   entity_cache = redis.get(f"entity:{name}:{group_id}")
   if entity_cache:
       return json.loads(entity_cache)
   ```

4. **Batch Processing**
   ```python
   # Process webhooks in 30-second batches
   # Reduce OpenAI API calls by 10x
   await graphiti.add_episodes_batch(episodes)
   ```

---

## 🎯 Implementation Roadmap

### **Phase 1: Foundation** ✅ (Complete)
- [x] Gmail integration
- [x] Supabase document storage
- [x] Vector embeddings
- [x] Episode deduplication
- [x] Basic entity extraction

### **Phase 2: Multi-Source** (Current)
- [ ] Google Docs integration
- [ ] Slack integration
- [ ] Webhook handlers with idempotency
- [ ] Entity resolution testing

### **Phase 3: Optimization** (Future)
- [ ] Custom episode metadata
- [ ] Temporal queries
- [ ] Redis caching
- [ ] Batch processing
- [ ] Performance monitoring

### **Phase 4: Advanced Features** (Future)
- [ ] HubSpot CRM integration
- [ ] Notion integration
- [ ] Linear integration
- [ ] Automated entity merging
- [ ] Real-time knowledge graph updates

---

## 🧪 Testing Strategy

### **Multi-Source Test Scenario**

1. **Gmail:** Send email: "Meeting with Sarah tomorrow about Acme deal"
2. **Slack:** Post message: "@sarah_j confirmed the Acme demo for Friday"
3. **Notion:** Create page: "Acme Corp - Deal Notes"
4. **Query AI Agent:** "What's the status of the Acme deal?"

**Expected Result:**
- AI agent finds:
  - 1 Email episode
  - 1 Slack episode
  - 1 Notion episode
- All 3 mention:
  - Entity: Sarah Johnson (merged across sources)
  - Entity: Acme Corp (recognized as same company)
- Response synthesizes all 3 sources

---

## 📚 Reference

### **Source Metadata Standards**

```python
# Gmail
{
    'source': 'gmail',
    'source_id': 'msg_abc123',
    'source_url': 'https://mail.google.com/mail/u/0/#inbox/msg_abc123',
    'metadata': {
        'from': 'sarah.johnson@acme-corp.com',
        'to': 'alex@company.com',
        'thread_id': 'thread_xyz',
        'labels': ['INBOX', 'IMPORTANT']
    }
}

# Slack
{
    'source': 'slack',
    'source_id': '1698765432.123456',
    'source_url': 'https://workspace.slack.com/archives/C123/p1698765432123456',
    'metadata': {
        'channel': '#sales',
        'user': 'sarah_johnson',
        'thread_ts': '1698765400.123000',
        'reactions': ['thumbsup']
    }
}

# Google Docs
{
    'source': 'google_docs',
    'source_id': 'doc_abc123',
    'source_url': 'https://docs.google.com/document/d/doc_abc123',
    'metadata': {
        'title': 'Acme Corp - Deal Notes',
        'editor': 'alex@company.com',
        'version': 15,
        'last_modified': '2025-10-07T14:30:00Z'
    }
}
```

---

## ✅ Success Criteria

Multi-source schema is production-ready when:

- [ ] 3+ data sources integrated (Gmail, Slack, Docs)
- [ ] Entities merge correctly across sources
- [ ] Deduplication works for all sources
- [ ] AI agent can query cross-source knowledge
- [ ] Performance: <500ms query time for 10K episodes
- [ ] Webhook handlers have 99.9% idempotency
- [ ] Zero duplicate episodes created

---

**Last Updated:** October 7, 2025
**Status:** Design Complete, Implementation 40% Complete
**Next:** Implement Google Docs integration with same deduplication pattern
