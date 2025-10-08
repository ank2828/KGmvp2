"""
Graph Data Explorer Routes
Read-only endpoints for inspecting FalkorDB contents
"""

from fastapi import APIRouter, Query, Depends
from dependencies import get_graphiti_service
from services.graphiti_service import GraphitiService

router = APIRouter(prefix="/api/explore", tags=["explore"])


@router.get("/episodes")
async def get_episodes(
    limit: int = Query(10, ge=1, le=100),
    graphiti: GraphitiService = Depends(get_graphiti_service)
):
    """
    Get episodes (email bodies) from the knowledge graph.

    Args:
        limit: Maximum number of episodes to return (1-100)

    Returns:
        List of episodes with name, body, and creation time
    """

    query = f"""
    MATCH (e:Episode)
    RETURN e.name AS name,
           e.episode_body AS body,
           e.created_at AS created_at
    ORDER BY e.created_at DESC
    LIMIT {limit}
    """

    result, _, _ = await graphiti.driver.execute_query(query)

    episodes = [
        {
            "name": row['name'],
            "body": row['body'],
            "created_at": row['created_at']
        }
        for row in result
    ]

    return {"episodes": episodes, "count": len(episodes)}


@router.get("/entities")
async def get_entities(
    limit: int = Query(20, ge=1, le=200),
    graphiti: GraphitiService = Depends(get_graphiti_service)
):
    """
    Get extracted entities from the knowledge graph.

    Args:
        limit: Maximum number of entities to return (1-200)

    Returns:
        List of entities with name, summary, and labels
    """

    query = f"""
    MATCH (n:Entity)
    RETURN n.name AS name,
           n.summary AS summary,
           labels(n) AS labels,
           n.created_at AS created_at
    ORDER BY n.created_at DESC
    LIMIT {limit}
    """

    result, _, _ = await graphiti.driver.execute_query(query)

    entities = [
        {
            "name": row['name'],
            "summary": row['summary'],
            "labels": row['labels'],
            "created_at": row['created_at']
        }
        for row in result
    ]

    return {"entities": entities, "count": len(entities)}


@router.get("/relationships")
async def get_relationships(
    limit: int = Query(20, ge=1, le=200),
    graphiti: GraphitiService = Depends(get_graphiti_service)
):
    """
    Get relationships between entities.

    Args:
        limit: Maximum number of relationships to return (1-200)

    Returns:
        List of relationships with source, target, and fact
    """

    query = f"""
    MATCH (a:Entity)-[r]->(b:Entity)
    RETURN a.name AS source,
           type(r) AS type,
           b.name AS target,
           r.fact AS fact
    LIMIT {limit}
    """

    result, _, _ = await graphiti.driver.execute_query(query)

    relationships = [
        {
            "source": row['source'],
            "type": row['type'],
            "target": row['target'],
            "fact": row['fact']
        }
        for row in result
    ]

    return {"relationships": relationships, "count": len(relationships)}
