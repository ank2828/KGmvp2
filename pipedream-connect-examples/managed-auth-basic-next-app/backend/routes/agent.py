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
    Query knowledge graph with natural language.

    Args:
        request: Contains query string and user_id
        graphiti: GraphitiService dependency

    Returns:
        AI-generated response based on knowledge graph context
    """
    try:
        # 1. Search knowledge graph
        # VERIFIED: Matches routes/gmail.py:161
        # Sanitize user_id to avoid RediSearch syntax errors with hyphens
        sanitized_user_id = request.user_id.replace('-', '')
        results = await graphiti.search(request.query, 10, sanitized_user_id)

        # 2. Format context from search results
        # VERIFIED: Result structure from graphiti_service.py:151-159
        # Each result is a dict with keys: fact, source, target, valid_at
        if not results:
            return {
                "response": "I don't have any information about that in your emails yet. Try fetching more emails first."
            }

        context = "\n".join([r["fact"] for r in results])

        # 3. Build comprehensive system prompt
        system_prompt = f"""You are an AI assistant with access to the user's email knowledge graph.

RETRIEVED FACTS:
{context}

INSTRUCTIONS:
- Synthesize ALL relevant facts in your response
- When asked follow-up questions like "what else", refer to the conversation history
- Combine multiple facts about the same person/topic
- Be conversational and comprehensive
- Cite specific facts when making claims
- For follow-up questions, provide new information not covered in previous responses"""

        # 4. Build messages array with conversation history
        # Note: Frontend limits history to last 20 messages (10 exchanges) for token efficiency
        messages = [{"role": "system", "content": system_prompt}]

        # Add previous conversation history
        for msg in request.conversation_history:
            messages.append({"role": msg.role, "content": msg.content})

        # Add current user query
        messages.append({"role": "user", "content": request.query})

        # 5. Call OpenAI with full conversation
        response = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=messages,
            temperature=0.7,
            max_tokens=1000
        )

        return {
            "response": response.choices[0].message.content,
            "sources": [r["fact"] for r in results[:5]],
            "facts_count": len(results)
        }

    except Exception as e:
        logger.error(f"Agent query failed: {e}")
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
        # Sanitize user_id to avoid RediSearch syntax errors with hyphens
        sanitized_user_id = user_id.replace('-', '')
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
