"""
AI Agent routes for natural language queries
"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from openai import OpenAI

from services.graphiti_service import GraphitiService
from dependencies import get_graphiti_service
from config import settings
from routes.gmail import sanitize_user_id_for_graphiti

logger = logging.getLogger(__name__)
router = APIRouter()

# Initialize OpenAI client
client = OpenAI(api_key=settings.openai_api_key)


class ChatMessage(BaseModel):
    """Individual chat message"""
    role: str  # 'user' or 'assistant'
    content: str

class QueryRequest(BaseModel):
    """Request body for agent query"""
    query: str
    user_id: str
    conversation_history: list[ChatMessage] = []  # Previous conversation history


@router.post("/agent/query")
async def query_agent(
    request: QueryRequest,
    graphiti: GraphitiService = Depends(get_graphiti_service)
):
    """
    Query knowledge graph with natural language using hybrid search.

    PHASE 1 HYBRID SEARCH ARCHITECTURE:
    1. Search Graphiti for entity relationships (facts)
    2. Get documents linked to those entities
    3. Build hybrid context (facts + email content)
    4. Send to GPT-4 with full context + citations

    Args:
        request: Contains query string and user_id
        graphiti: GraphitiService dependency

    Returns:
        AI-generated response with document citations
    """
    try:
        from services.document_store import document_store

        # 1. Search knowledge graph for entity relationships
        sanitized_user_id = sanitize_user_id_for_graphiti(request.user_id)

        logger.info(f"🔍 AI Agent hybrid search:")
        logger.info(f"   Original user_id: {request.user_id}")
        logger.info(f"   Sanitized group_id: {sanitized_user_id}")
        logger.info(f"   Query: {request.query}")

        graph_results = await graphiti.search(request.query, 10, sanitized_user_id)

        logger.info(f"📊 Graph search: {len(graph_results)} facts found")

        # 2. If no graph results, fall back to semantic document search
        if not graph_results:
            logger.info("   No graph facts found, falling back to semantic document search")

            # Semantic search over email bodies
            # IMPORTANT: Use original user_id for Supabase (not sanitized for Graphiti)
            doc_results = await document_store.search_documents_semantic(
                query=request.query,
                user_id=request.user_id,  # Use original user_id, not sanitized
                limit=5,
                source_filter=None,  # Don't filter by source (may have slack, notion, etc)
                min_similarity=0.3  # Lower threshold for better recall
            )

            if not doc_results:
                return {
                    "response": "I don't have any information about that in your emails yet. Try fetching more emails first.",
                    "sources": {"facts": [], "documents": []},
                    "facts_count": 0,
                    "documents_count": 0
                }

            # Build context from documents only
            docs_text = "\n\n".join([
                f"📧 Email from {doc['document'].metadata.get('from', 'Unknown')}\n"
                f"Date: {doc['document'].metadata.get('date', 'Unknown')}\n"
                f"Subject: {doc['document'].subject}\n"
                f"Content: {doc['document'].content[:800]}..."
                for doc in doc_results[:3]
            ])

            context = f"RELEVANT EMAILS:\n\n{docs_text}"

            system_prompt = f"""You are an AI assistant with access to the user's emails.

{context}

INSTRUCTIONS:
- Answer the question based on the email content above
- Quote specific parts of emails when relevant
- Mention the sender and date when citing emails
- Be conversational and comprehensive"""

            messages = [
                {"role": "system", "content": system_prompt},
                *[{"role": msg.role, "content": msg.content} for msg in request.conversation_history],
                {"role": "user", "content": request.query}
            ]

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=messages,
                temperature=0.7,
                max_tokens=1500
            )

            return {
                "response": response.choices[0].message.content,
                "sources": {
                    "facts": [],
                    "documents": [
                        {
                            "subject": doc['document'].subject,
                            "from": doc['document'].metadata.get('from'),
                            "date": doc['document'].metadata.get('date'),
                            "preview": doc['document'].content_preview,
                            "similarity": doc['similarity']
                        }
                        for doc in doc_results[:3]
                    ]
                },
                "facts_count": 0,
                "documents_count": len(doc_results)
            }

        # 3. Extract entity UUIDs from graph results
        entity_uuids = set()
        for result in graph_results:
            entity_uuids.add(result['source'])
            entity_uuids.add(result['target'])

        logger.info(f"🔗 Found {len(entity_uuids)} related entities")

        # 4. Get source documents for these entities
        documents = await document_store.get_documents_for_entities(
            entity_uuids=list(entity_uuids),
            limit=5
        )

        logger.info(f"📄 Retrieved {len(documents)} source documents")

        # 5. Build hybrid context (graph facts + document excerpts)
        facts_text = "\n".join([
            f"- {result['fact']}"
            for result in graph_results
        ])

        docs_text = "\n\n".join([
            f"📧 Email from {doc.metadata.get('from', 'Unknown')}\n"
            f"Date: {doc.metadata.get('date', 'Unknown')}\n"
            f"Subject: {doc.subject}\n"
            f"Content: {doc.content[:800]}..."
            for doc in documents[:3]
        ])

        # 6. Build comprehensive system prompt with both facts and documents
        system_prompt = f"""You are an AI assistant with access to the user's email knowledge graph and original documents.

KNOWLEDGE GRAPH FACTS:
{facts_text}

ORIGINAL EMAILS:
{docs_text}

INSTRUCTIONS:
- Synthesize information from BOTH facts and email content
- Quote specific parts of emails when relevant
- Cite email metadata (sender, date, subject) when quoting
- Combine multiple facts about the same person/topic
- Be conversational and comprehensive
- When asked follow-up questions, refer to conversation history and provide new information"""

        # 7. Build messages with conversation history
        messages = [
            {"role": "system", "content": system_prompt},
            *[{"role": msg.role, "content": msg.content} for msg in request.conversation_history],
            {"role": "user", "content": request.query}
        ]

        # 8. Call OpenAI with enriched context
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=1500  # Increased for richer responses with citations
        )

        return {
            "response": response.choices[0].message.content,
            "sources": {
                "facts": [r["fact"] for r in graph_results[:5]],
                "documents": [
                    {
                        "subject": doc.subject,
                        "from": doc.metadata.get('from'),
                        "date": doc.metadata.get('date'),
                        "preview": doc.content_preview
                    }
                    for doc in documents[:3]
                ]
            },
            "facts_count": len(graph_results),
            "documents_count": len(documents)
        }

    except Exception as e:
        logger.error(f"Agent query failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/test-search")
async def test_search(
    query: str,
    user_id: str,
    limit: int = 5,
    graphiti: GraphitiService = Depends(get_graphiti_service)
):
    """Test endpoint to see raw graph search results"""
    try:
        # CRITICAL: Use SAME sanitization as gmail.py sync function
        sanitized_user_id = sanitize_user_id_for_graphiti(user_id)
        results = await graphiti.search(query, limit, sanitized_user_id)

        return {
            "query": query,
            "user_id": user_id,
            "results_count": len(results),
            "facts": [r["fact"] for r in results]
        }
    except Exception as e:
        logger.error(f"Test search failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))
