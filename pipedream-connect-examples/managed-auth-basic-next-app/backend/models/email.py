"""
Email data models
"""

from typing import Optional, List
from pydantic import BaseModel, Field


class EmailMessage(BaseModel):
    """Structured email data from Pipedream"""
    subject: str
    sender: str
    date: str
    message_id: str
    body: Optional[str] = None

    class Config:
        json_schema_extra = {
            "example": {
                "subject": "Q4 Planning Meeting",
                "sender": "john@company.com",
                "date": "2025-01-15T10:30:00Z",
                "message_id": "abc123",
            }
        }


class GraphProcessingResult(BaseModel):
    """Result from Graphiti processing"""
    episode_uuid: str
    entities_extracted: int
    relationships_extracted: int
    entity_names: List[str]
    relationships: List[str]
    processing_time_ms: float


class EmailProcessingResponse(BaseModel):
    """Response for processed email"""
    email: EmailMessage
    graph_processing: Optional[GraphProcessingResult] = None
    error: Optional[str] = None
    skipped: bool = False
