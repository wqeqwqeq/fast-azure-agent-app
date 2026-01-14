"""FastAPI application configuration using Pydantic Settings."""

from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Resource prefix for Azure resources
    resource_prefix: str = "stanley-dev-ui"

    # Chat history storage mode: "postgres" or "redis"
    # Note: "local" mode is not supported in this FastAPI version
    chat_history_mode: str = "redis"

    # Number of days of conversation history to load
    conversation_history_days: int = 7

    # PostgreSQL configuration
    postgres_port: int = 5432
    postgres_admin_login: str = "pgadmin"
    postgres_database: str = "chat_history"
    postgres_sslmode: str = "require"

    # Redis configuration
    redis_port: int = 6380
    redis_ssl: bool = True
    redis_ttl_seconds: int = 1800

    # Workflow configuration
    dynamic_plan: bool = False

    # UI settings
    show_func_result: bool = True

    # Observability settings
    tracing_backend: str = "appinsights"  # "disabled", "local", "appinsights"
    local_otlp_endpoint: str = "http://localhost:4317"
    enable_sensitive_data: bool = True  # Enable to log prompts/responses in traces

    # Default model
    default_model: str = "gpt-4.1"

    # Local testing credentials (for local_psql/local_redis modes)
    local_test_client_id: str = "00000000-0000-0000-0000-000000000001"
    local_test_username: str = "local_user"

    @property
    def key_vault_name(self) -> str:
        """Get Key Vault name derived from resource prefix."""
        return f"{self.resource_prefix.replace('-', '')}kv"

    @property
    def postgres_host(self) -> str:
        """Get PostgreSQL host derived from resource prefix."""
        return f"{self.resource_prefix}-postgres.postgres.database.azure.com"

    @property
    def redis_host(self) -> str:
        """Get Redis host derived from resource prefix."""
        return f"{self.resource_prefix}-redis.redis.cache.windows.net"

    def get_postgres_connection_string(self, password: str) -> str:
        """Build PostgreSQL connection string.

        Args:
            password: PostgreSQL admin password from Key Vault

        Returns:
            PostgreSQL connection string
        """
        return (
            f"postgresql://{self.postgres_admin_login}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}"
            f"/{self.postgres_database}?sslmode={self.postgres_sslmode}"
        )


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
