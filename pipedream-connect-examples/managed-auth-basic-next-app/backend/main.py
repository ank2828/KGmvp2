"""
FastAPI Application Entry Point
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import settings
from services.graphiti_service import GraphitiService
from dependencies import set_graphiti_service
from routes.gmail import router as gmail_router
from routes.auth import router as auth_router
from routes.agent import router as agent_router

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

# CORS - Allow Vercel domains and localhost for development
app.add_middleware(
    CORSMiddleware,
    allow_origin_regex=r"(https://.*\.vercel\.app|http://localhost:300[0-9])",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(gmail_router, prefix="/api", tags=["Gmail"])
app.include_router(auth_router, prefix="/api", tags=["Auth"])
app.include_router(agent_router, prefix="/api", tags=["Agent"])


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
