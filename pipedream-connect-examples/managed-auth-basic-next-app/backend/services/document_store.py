"""
Document Storage Service with Vector Search

Manages full document content in Supabase PostgreSQL with pgvector.
Bridges Supabase documents to FalkorDB entities for hybrid search.

Architecture:
- Supabase: Full email/document content + metadata + embeddings
- FalkorDB: Entity relationships (Company, Contact, Deal)
- Link: document_entities table (document_id ↔ entity_uuid)

Usage:
    # Store email
    doc_id = await document_store.store_email(user_id, email_data)

    # Link to FalkorDB entity
    await document_store.link_document_to_entity(doc_id, entity_uuid, ...)

    # Retrieve documents for entities
    docs = await document_store.get_documents_for_entities(entity_uuids)

    # Semantic search
    docs = await document_store.search_documents_semantic(query, user_id)
"""

import logging
from typing import List, Dict, Any, Optional
from uuid import UUID
from datetime import datetime
from openai import AsyncOpenAI
from pydantic import BaseModel

from config import settings
from services.database import db_service

logger = logging.getLogger(__name__)


class Document(BaseModel):
    """Document model matching Supabase schema"""
    id: UUID
    user_id: str
    source: str
    source_id: str
    doc_type: str
    subject: Optional[str]
    content: str
    content_preview: str
    metadata: Dict[str, Any]
    source_created_at: datetime
    created_at: datetime
    vector_embedding: Optional[List[float]] = None

    class Config:
        # Allow Supabase to return vectors as strings (will be parsed)
        json_encoders = {
            List[float]: lambda v: v
        }


class DocumentStore:
    """Manages document storage and vector search in Supabase"""

    def __init__(self):
        self.client = db_service.client
        self.openai = AsyncOpenAI(api_key=settings.openai_api_key)
        self._embedding_cache = {}  # Simple in-memory cache for deduplication

    async def store_email(
        self,
        user_id: str,
        email_data: Dict[str, Any],
        generate_embedding: bool = True
    ) -> UUID:
        """
        Store Gmail email with vector embedding.

        Args:
            user_id: User identifier (Supabase auth user ID)
            email_data: {
                'id': Gmail message ID,
                'subject': Email subject,
                'body': Email body content,
                'from': Sender email,
                'to': Recipient email,
                'date': Sent date (string or datetime),
                'thread_id': Gmail thread ID
            }
            generate_embedding: Whether to generate vector embedding (default True)

        Returns:
            document_id: UUID of stored document

        Raises:
            Exception: If storage fails
        """
        try:
            # Build searchable content (subject + body)
            searchable_content = f"{email_data.get('subject', '')} {email_data.get('body', '')}"

            # Generate vector embedding
            embedding = None
            if generate_embedding:
                embedding = await self._generate_embedding(searchable_content)

            # Content preview (first 200 chars)
            content = email_data.get('body', '')
            preview = content[:200] + '...' if len(content) > 200 else content

            # Parse date
            source_created_at = email_data.get('date')
            if isinstance(source_created_at, str):
                # Parse Gmail date format (e.g., "Mon, 1 Jan 2025 10:00:00 -0800")
                from email.utils import parsedate_to_datetime
                try:
                    source_created_at = parsedate_to_datetime(source_created_at)
                except Exception as e:
                    logger.warning(f"Failed to parse date '{source_created_at}': {e}")
                    source_created_at = datetime.utcnow()
            elif source_created_at is None:
                source_created_at = datetime.utcnow()

            # Ensure timezone-aware
            if source_created_at.tzinfo is None:
                from datetime import timezone
                source_created_at = source_created_at.replace(tzinfo=timezone.utc)

            # Upsert document (deduplicate on source_id)
            result = self.client.table('documents').upsert({
                'user_id': user_id,
                'source': 'gmail',
                'source_id': email_data['id'],
                'doc_type': 'email',
                'subject': email_data.get('subject', ''),
                'content': content,
                'content_preview': preview,
                'metadata': {
                    'from': email_data.get('from', ''),
                    'to': email_data.get('to', ''),
                    'date': email_data.get('date', ''),
                    'thread_id': email_data.get('thread_id', '')
                },
                'source_created_at': source_created_at.isoformat(),
                'vector_embedding': embedding
            }, on_conflict='source,source_id,user_id').execute()

            document_id = UUID(result.data[0]['id'])
            logger.debug(f"Stored document {document_id} for email {email_data['id']}")
            return document_id

        except Exception as e:
            logger.error(f"Failed to store email {email_data.get('id')}: {e}")
            raise

    async def store_emails_batch(
        self,
        user_id: str,
        emails: List[Dict[str, Any]]
    ) -> List[UUID]:
        """
        Store multiple emails efficiently with batched embeddings.

        Args:
            user_id: User identifier
            emails: List of email_data dicts

        Returns:
            List of document UUIDs
        """
        if not emails:
            return []

        try:
            # Step 1: Prepare all texts for embedding
            texts = [
                f"{email.get('subject', '')} {email.get('body', '')}"
                for email in emails
            ]

            # Step 2: Generate embeddings in batch (cheaper + faster)
            embeddings = await self._generate_embeddings_batch(texts)

            # Step 3: Store all documents
            document_ids = []
            for email, embedding in zip(emails, embeddings):
                # Parse date
                source_created_at = email.get('date')
                if isinstance(source_created_at, str):
                    from email.utils import parsedate_to_datetime
                    try:
                        source_created_at = parsedate_to_datetime(source_created_at)
                    except:
                        source_created_at = datetime.utcnow()
                elif source_created_at is None:
                    source_created_at = datetime.utcnow()

                # Ensure timezone-aware
                if source_created_at.tzinfo is None:
                    from datetime import timezone
                    source_created_at = source_created_at.replace(tzinfo=timezone.utc)

                # Content preview
                content = email.get('body', '')
                preview = content[:200] + '...' if len(content) > 200 else content

                # Upsert document
                result = self.client.table('documents').upsert({
                    'user_id': user_id,
                    'source': 'gmail',
                    'source_id': email['id'],
                    'doc_type': 'email',
                    'subject': email.get('subject', ''),
                    'content': content,
                    'content_preview': preview,
                    'metadata': {
                        'from': email.get('from', ''),
                        'to': email.get('to', ''),
                        'date': email.get('date', ''),
                        'thread_id': email.get('thread_id', '')
                    },
                    'source_created_at': source_created_at.isoformat(),
                    'vector_embedding': embedding
                }, on_conflict='source,source_id,user_id').execute()

                document_ids.append(UUID(result.data[0]['id']))

            logger.info(f"Stored {len(document_ids)} emails in batch")
            return document_ids

        except Exception as e:
            logger.error(f"Failed to store email batch: {e}")
            raise

    async def _generate_embedding(self, text: str) -> List[float]:
        """
        Generate OpenAI vector embedding for text.

        Args:
            text: Text to embed

        Returns:
            Embedding vector (1536 dimensions)
        """
        try:
            # Check cache (simple deduplication)
            cache_key = text[:100]  # Use first 100 chars as key
            if cache_key in self._embedding_cache:
                return self._embedding_cache[cache_key]

            # Truncate to ~8000 tokens (OpenAI limit)
            text = text[:32000]  # ~8k tokens

            # Generate embedding
            response = await self.openai.embeddings.create(
                model="text-embedding-3-small",  # 1536 dimensions, $0.02/1M tokens
                input=text
            )

            embedding = response.data[0].embedding

            # Cache result
            self._embedding_cache[cache_key] = embedding

            return embedding

        except Exception as e:
            logger.error(f"Embedding generation failed: {e}")
            # Return zero vector as fallback (still allows storage, but no semantic search)
            return [0.0] * 1536

    async def _generate_embeddings_batch(self, texts: List[str]) -> List[List[float]]:
        """
        Generate embeddings for multiple texts in single API call.

        Args:
            texts: List of texts to embed

        Returns:
            List of embedding vectors
        """
        try:
            # Truncate all texts
            truncated_texts = [text[:32000] for text in texts]

            # OpenAI supports up to 2048 inputs per request
            # For larger batches, chunk them
            batch_size = 2048
            all_embeddings = []

            for i in range(0, len(truncated_texts), batch_size):
                batch = truncated_texts[i:i + batch_size]

                response = await self.openai.embeddings.create(
                    model="text-embedding-3-small",
                    input=batch
                )

                batch_embeddings = [item.embedding for item in response.data]
                all_embeddings.extend(batch_embeddings)

            return all_embeddings

        except Exception as e:
            logger.error(f"Batch embedding generation failed: {e}")
            # Return zero vectors as fallback
            return [[0.0] * 1536 for _ in texts]

    async def link_document_to_entity(
        self,
        document_id: UUID,
        entity_uuid: str,
        entity_type: str,
        entity_name: str,
        mention_count: int = 1,
        relevance_score: float = 1.0
    ):
        """
        Link a document to a FalkorDB entity.

        Args:
            document_id: Supabase document UUID
            entity_uuid: Graphiti entity UUID from FalkorDB
            entity_type: Entity type ('Company', 'Contact', 'Deal')
            entity_name: Entity name (cached for quick lookups)
            mention_count: Number of times entity appears in document
            relevance_score: Extraction confidence (0.0-1.0)
        """
        try:
            self.client.table('document_entities').insert({
                'document_id': str(document_id),
                'entity_uuid': entity_uuid,
                'entity_type': entity_type,
                'entity_name': entity_name,
                'mention_count': mention_count,
                'relevance_score': relevance_score
            }).execute()

            logger.debug(f"Linked document {document_id} to entity {entity_name}")

        except Exception as e:
            # Ignore duplicate link errors
            if "duplicate" in str(e).lower() or "unique" in str(e).lower():
                logger.debug(f"Document-entity link already exists (skipping)")
            else:
                logger.error(f"Failed to link document to entity: {e}")

    async def get_documents_for_entities(
        self,
        entity_uuids: List[str],
        limit: int = 10
    ) -> List[Document]:
        """
        Get documents that mention specific entities.

        Args:
            entity_uuids: List of Graphiti entity UUIDs
            limit: Max documents to return

        Returns:
            List of Document objects, sorted by relevance + recency
        """
        if not entity_uuids:
            return []

        try:
            # Query document_entities with join to documents
            # Exclude vector_embedding to avoid serialization issues
            result = self.client.table('document_entities')\
                .select('documents!inner(id,user_id,source,source_id,doc_type,subject,content,content_preview,metadata,source_created_at,created_at), relevance_score')\
                .in_('entity_uuid', entity_uuids)\
                .order('relevance_score', desc=True)\
                .limit(limit * 2)\
                .execute()  # Fetch 2x to account for duplicates

            # Extract documents and deduplicate
            documents = []
            seen_ids = set()

            for row in result.data:
                doc_data = row['documents']
                doc_id = doc_data['id']

                # Deduplicate (same doc may link to multiple entities)
                if doc_id not in seen_ids:
                    # Add empty vector_embedding since we excluded it
                    doc_data['vector_embedding'] = None
                    documents.append(Document(**doc_data))
                    seen_ids.add(doc_id)

                if len(documents) >= limit:
                    break

            logger.info(f"Retrieved {len(documents)} documents for {len(entity_uuids)} entities")
            return documents

        except Exception as e:
            logger.error(f"Failed to get documents for entities: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def search_documents_semantic(
        self,
        query: str,
        user_id: str,
        limit: int = 10,
        source_filter: Optional[str] = None,
        min_similarity: float = 0.5
    ) -> List[Dict[str, Any]]:
        """
        Semantic search using vector embeddings.

        Args:
            query: Natural language search query
            user_id: User identifier
            limit: Max results
            source_filter: Optional source filter ('gmail', 'slack', etc)
            min_similarity: Minimum cosine similarity (0.0-1.0)

        Returns:
            List of documents with similarity scores
        """
        try:
            # Generate query embedding
            query_embedding = await self._generate_embedding(query)

            # Call Supabase RPC function
            result = self.client.rpc(
                'match_documents',
                {
                    'query_embedding': query_embedding,
                    'match_threshold': min_similarity,
                    'match_count': limit,
                    'filter_user_id': user_id,
                    'filter_source': source_filter
                }
            ).execute()

            # Convert to Document objects with similarity scores
            documents = [
                {
                    'document': Document(**doc),
                    'similarity': doc['similarity']
                }
                for doc in result.data
            ]

            logger.info(f"Semantic search found {len(documents)} documents for query: '{query}'")
            return documents

        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []

    async def fetch_documents_by_ids(
        self,
        document_ids: List[UUID]
    ) -> List[Document]:
        """
        Fetch specific documents by ID.

        Args:
            document_ids: List of document UUIDs

        Returns:
            List of Document objects
        """
        if not document_ids:
            return []

        try:
            # Exclude vector_embedding to avoid serialization issues
            result = self.client.table('documents')\
                .select('id,user_id,source,source_id,doc_type,subject,content,content_preview,metadata,source_created_at,created_at')\
                .in_('id', [str(doc_id) for doc_id in document_ids])\
                .execute()

            # Add empty vector_embedding
            documents = []
            for doc in result.data:
                doc['vector_embedding'] = None
                documents.append(Document(**doc))

            return documents

        except Exception as e:
            logger.error(f"Failed to fetch documents by IDs: {e}")
            return []

    async def get_document_by_source_id(
        self,
        source: str,
        source_id: str,
        user_id: str
    ) -> Optional[Document]:
        """
        Get document by external source ID (e.g., Gmail message_id).

        Args:
            source: Source name ('gmail', 'slack', etc)
            source_id: External ID
            user_id: User identifier

        Returns:
            Document if found, None otherwise
        """
        try:
            # Exclude vector_embedding
            result = self.client.table('documents')\
                .select('id,user_id,source,source_id,doc_type,subject,content,content_preview,metadata,source_created_at,created_at')\
                .eq('source', source)\
                .eq('source_id', source_id)\
                .eq('user_id', user_id)\
                .limit(1)\
                .execute()

            if result.data:
                doc_data = result.data[0]
                doc_data['vector_embedding'] = None
                return Document(**doc_data)
            return None

        except Exception as e:
            logger.error(f"Failed to get document by source_id: {e}")
            return None


# Singleton instance
document_store = DocumentStore()
