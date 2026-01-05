"""FastAPI application for OpsAgent Chat API.

This module provides the main FastAPI application with:
- Lifespan management for database connections
- CORS middleware
- Route registration
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import get_settings
from .db import AsyncChatHistoryManager
from .opsagent.utils.keyvault import AKV
from .routes import conversations, messages, settings, user

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

    # Initialize Key Vault client for secrets
    akv = AKV(vault_name=app_settings.key_vault_name)

    # Get database credentials from Key Vault
    postgres_password = akv.get_secret("POSTGRES-ADMIN-PASSWORD") or ""
    postgres_connection_string = app_settings.get_postgres_connection_string(postgres_password)

    # Initialize history manager
    history_manager = AsyncChatHistoryManager(
        history_days=app_settings.conversation_history_days
    )

    # Determine if we should use Redis cache
    use_redis = app_settings.chat_history_mode in ["redis", "local_redis"]

    if use_redis:
        redis_password = akv.get_secret("REDIS-PASSWORD") or ""
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

    # Include routers
    app.include_router(user.router, prefix="/api", tags=["user"])
    app.include_router(settings.router, prefix="/api", tags=["settings"])
    app.include_router(conversations.router, prefix="/api", tags=["conversations"])
    app.include_router(messages.router, prefix="/api", tags=["messages"])

    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}

    return app


# Create the app instance
app = create_app()
