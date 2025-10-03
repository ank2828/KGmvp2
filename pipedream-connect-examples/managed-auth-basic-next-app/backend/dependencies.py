"""
FastAPI dependency injection providers
"""

from typing import Optional
from fastapi import HTTPException, status

# This will be set by main.py on startup
_graphiti_service: Optional["GraphitiService"] = None


def set_graphiti_service(service: "GraphitiService"):
    """Called by main.py lifespan to register service"""
    global _graphiti_service
    _graphiti_service = service


def get_graphiti_service() -> "GraphitiService":
    """Dependency for routes to access Graphiti service"""
    if _graphiti_service is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graphiti service not initialized"
        )

    if not _graphiti_service.is_initialized:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Graphiti service still initializing"
        )

    return _graphiti_service
