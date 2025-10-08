"""
FastAPI Application Entry Point
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from redis import Redis

from config import settings
from services.graphiti_service import GraphitiService
from dependencies import set_graphiti_service
from routes.gmail import router as gmail_router
from routes.auth import router as auth_router
from routes.agent import router as agent_router
from routes.webhooks import router as webhooks_router
from routes.sync_status import router as sync_status_router
from routes.explore import router as explore_router
from routes.process_emails import router as process_emails_router

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifecycle management"""

    # Startup
    logger.info("Starting application...")

    # Validate configuration
    logger.info(f"FalkorDB: {settings.falkordb_host}")
    logger.info(f"Graphiti enabled: {settings.graphiti_enabled}")

    # Initialize Graphiti
    graphiti_service = None
    if settings.graphiti_enabled:
        try:
            graphiti_service = GraphitiService()
            await graphiti_service.initialize()
            set_graphiti_service(graphiti_service)
            logger.info("Graphiti service ready")
        except Exception as e:
            logger.error(f"Failed to initialize Graphiti: {e}")
            logger.warning("Continuing without Graphiti...")

    yield

    # Shutdown
    logger.info("Shutting down application...")
    if graphiti_service:
        await graphiti_service.close()
    logger.info("Shutdown complete")


# Create FastAPI app
app = FastAPI(
    title="Gmail Knowledge Graph API",
    description="Process Gmail emails through Graphiti knowledge graph",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS - Allow all origins for development (restrict in production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(gmail_router, prefix="/api", tags=["Gmail"])
app.include_router(auth_router, prefix="/api", tags=["Auth"])
app.include_router(agent_router, prefix="/api", tags=["Agent"])
app.include_router(webhooks_router, prefix="/api", tags=["Webhooks"])
app.include_router(sync_status_router, prefix="/api", tags=["Sync"])
app.include_router(explore_router, tags=["Explore"])
app.include_router(process_emails_router, prefix="/api", tags=["Email Processing"])


@app.get("/", tags=["Health"])
def root():
    """API root"""
    return {
        "service": "Gmail Knowledge Graph API",
        "status": "running",
        "graphiti_enabled": settings.graphiti_enabled,
    }


@app.get("/health", tags=["Health"])
def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "falkordb_configured": bool(settings.falkordb_host),
        "openai_configured": bool(settings.openai_api_key),
    }


@app.get("/health/redis", tags=["Health"])
async def redis_health():
    """Redis connection health check"""
    try:
        r = Redis.from_url(settings.redis_broker_url)
        r.ping()
        return {
            "status": "healthy",
            "redis": "connected",
            "broker_url": settings.redis_broker_url.split('@')[-1]  # Hide password if present
        }
    except Exception as e:
        return {
            "status": "unhealthy",
            "redis": f"connection_failed: {str(e)}",
            "broker_url": settings.redis_broker_url.split('@')[-1]
        }
