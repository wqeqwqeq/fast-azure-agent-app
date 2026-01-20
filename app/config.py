"""FastAPI application configuration using Pydantic Settings."""

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict

from app.opsagent.model_registry import DEFAULT_MODEL, GPT41_MINI


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

    # Agent factory toggle: True = use opsagent (demo), False = use agent_factory
    use_demo_opsagent: bool = False

    # Memory feature toggle (can be overridden per-request)
    use_memory: bool = True

    # UI settings
    show_func_result: bool = True
    # Orchestration agents whose structured output should be displayed in thinking flyout
    orchestration_agents: set[str] = {
        "triage-agent",
        "plan-agent",
        "replan-agent",
        "review-agent",
    }

    # Observability settings
    tracing_backend: str = "appinsights"  # "disabled", "local", "appinsights"
    local_otlp_endpoint: str = "http://localhost:4317"
    enable_sensitive_data: bool = True  # Enable to log prompts/responses in traces

    # Default model (from registry, can be overridden via env)
    default_model: str = DEFAULT_MODEL

    # Memory feature settings (uses sequence numbers, not rounds)
    memory_rolling_window_size: int = 14   # Window covers 14 messages (7 rounds)
    memory_summarize_after_seq: int = 5    # Start summarizing when end_seq >= 5 (after round 3)
    memory_model: str = GPT41_MINI.name     # Use mini model for faster/cheaper summarization

    # Call tracking settings
    call_retention_days: int = 7  # Number of days to retain call records

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
