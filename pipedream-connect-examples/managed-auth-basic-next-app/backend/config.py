"""
Application Configuration
Validates all required environment variables on startup
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field, validator


class Settings(BaseSettings):
    """Application settings with validation"""

    # FalkorDB Cloud
    falkordb_host: str = Field(..., env="FALKORDB_HOST")
    falkordb_port: int = Field(6379, env="FALKORDB_PORT")
    falkordb_username: Optional[str] = Field(None, env="FALKORDB_USERNAME")
    falkordb_password: str = Field(..., env="FALKORDB_PASSWORD")
    falkordb_database: str = Field("default_db", env="FALKORDB_DATABASE")

    # OpenAI (required for Graphiti)
    openai_api_key: str = Field(..., env="OPENAI_API_KEY")

    # Pipedream Connect
    pipedream_project_id: str = Field(..., env="PIPEDREAM_PROJECT_ID")
    pipedream_client_id: str = Field(..., env="PIPEDREAM_CLIENT_ID")
    pipedream_client_secret: str = Field(..., env="PIPEDREAM_CLIENT_SECRET")
    pipedream_project_environment: Optional[str] = Field("development", env="PIPEDREAM_PROJECT_ENVIRONMENT")

    # Supabase
    supabase_url: str = Field(..., env="SUPABASE_URL")
    supabase_service_key: str = Field(..., env="SUPABASE_SERVICE_KEY")

    # Webhook Security
    pipedream_webhook_secret: Optional[str] = Field(None, env="PIPEDREAM_WEBHOOK_SECRET")

    # Redis (Celery broker and result backend)
    redis_broker_url: str = Field(default="redis://localhost:6379/0", env="REDIS_BROKER_URL")
    redis_result_backend: str = Field(default="redis://localhost:6379/1", env="REDIS_RESULT_BACKEND")

    # Application settings
    max_emails_per_batch: int = Field(10, env="MAX_EMAILS_PER_BATCH")
    max_email_body_length: int = Field(5000, env="MAX_EMAIL_BODY_LENGTH")
    graphiti_enabled: bool = Field(True, env="GRAPHITI_ENABLED")

    class Config:
        env_file = ".env"
        case_sensitive = False

    @validator("falkordb_host")
    def validate_host(cls, v):
        if not v or v == "localhost":
            raise ValueError("FALKORDB_HOST must be a valid FalkorDB Cloud endpoint")
        return v


# Global settings instance
settings = Settings()
