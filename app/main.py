"""FastAPI application for OpsAgent Chat API.

This module provides the main FastAPI application with:
- Lifespan management for database connections
- CORS middleware
- Route registration
- Static file serving for frontend UI
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from .config import get_settings
from .infrastructure import AsyncChatHistoryManager
from .infrastructure.keyvault import AKV
from .opsagent.model_registry import ModelRegistry
from .routes import conversations, evaluation, messages, models, settings, user

# All secrets to pre-load at startup
REQUIRED_SECRETS = [
    "POSTGRES-ADMIN-PASSWORD",
    "REDIS-PASSWORD",
    "AZURE-OPENAI-API-KEY",
    "APPLICATIONINSIGHTS-CONNECTION-STRING",
]

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application lifespan for database connections.

    Initializes PostgreSQL pool and Redis connection on startup.
    Cleans up connections on shutdown.
    """
    app_settings = get_settings()
    logger.info(f"Starting application with mode: {app_settings.chat_history_mode}")

    # Initialize Key Vault client and pre-load all secrets
    akv = AKV(vault_name=app_settings.key_vault_name)
    akv.load_secrets(REQUIRED_SECRETS)
    app.state.keyvault = akv

    # Create ModelRegistry and store in app.state
    # This loads all required model secrets at startup
    app.state.model_registry = ModelRegistry(akv)

    # Get database credentials from pre-loaded secrets
    postgres_password = akv.get_secret("POSTGRES-ADMIN-PASSWORD")
    postgres_connection_string = app_settings.get_postgres_connection_string(postgres_password)

    # Initialize history manager
    history_manager = AsyncChatHistoryManager(
        history_days=app_settings.conversation_history_days
    )

    # Determine if we should use Redis cache
    use_redis = app_settings.chat_history_mode in ["redis", "local_redis"]

    if use_redis:
        redis_password = akv.get_secret("REDIS-PASSWORD")
        await history_manager.initialize(
            postgres_connection_string=postgres_connection_string,
            redis_host=app_settings.redis_host,
            redis_password=redis_password,
            redis_port=app_settings.redis_port,
            redis_ssl=app_settings.redis_ssl,
            redis_ttl=app_settings.redis_ttl_seconds,
        )
        logger.info("Initialized with PostgreSQL + Redis write-through cache")
    else:
        await history_manager.initialize(
            postgres_connection_string=postgres_connection_string,
        )
        logger.info("Initialized with PostgreSQL only")

    # Store in app state for dependency injection
    app.state.history_manager = history_manager

    yield

    # Cleanup on shutdown
    logger.info("Shutting down application")
    await history_manager.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application.

    Returns:
        Configured FastAPI application instance
    """
    app = FastAPI(
        title="OpsAgent Chat API",
        description="FastAPI-based chat API for OpsAgent with PostgreSQL + Redis caching",
        version="1.0.0",
        lifespan=lifespan,
    )

    # Add CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Serve static files
    static_dir = Path(__file__).parent / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    # Include routers
    app.include_router(user.router, prefix="/api", tags=["user"])
    app.include_router(models.router, prefix="/api", tags=["models"])
    app.include_router(settings.router, prefix="/api", tags=["settings"])
    app.include_router(conversations.router, prefix="/api", tags=["conversations"])
    app.include_router(messages.router, prefix="/api", tags=["messages"])
    app.include_router(evaluation.router, prefix="/api", tags=["evaluation"])

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}

    @app.get("/")
    async def root():
        """Serve the frontend UI."""
        static_dir = Path(__file__).parent / "static"
        return FileResponse(static_dir / "index.html")

    return app


# Create the app instance
app = create_app()
