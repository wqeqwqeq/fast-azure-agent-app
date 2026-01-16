"""Model registry with centralized, typed model definitions.

This module provides:
- AzOpenAIEnvSettings: Environment-based settings for Mode 1 (local dev)
- ModelDefinition: Immutable model configuration dataclass
- ModelRegistry: Loads secrets and resolves model configurations
- AgentModelMapping: Per-agent model override with Pydantic validation
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from app.infrastructure.keyvault import AKV

load_dotenv()


# --- Env Settings (Mode 1: Local Dev) ---
class AzOpenAIEnvSettings(BaseSettings):
    """Azure OpenAI configuration from environment variables.

    Used in Mode 1 (local dev) when no ModelRegistry is provided.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_deployment_name: str = ""


# --- Model Definition ---
@dataclass(frozen=True)
class ModelDefinition:
    """Immutable model configuration."""

    name: str
    display_name: str
    deployment_name: str
    endpoint: str
    secret_name: str


# --- Available Models ---
GPT41 = ModelDefinition(
    name="gpt-4.1",
    display_name="GPT 4.1",
    deployment_name="gpt-4.1",
    endpoint="https://stanleyai.cognitiveservices.azure.com/",
    secret_name="AZURE-OPENAI-API-KEY",
)

GPT41_MINI = ModelDefinition(
    name="gpt-4.1-mini",
    display_name="GPT 4.1 Mini",
    deployment_name="gpt-4.1-mini",
    endpoint="https://stanleyai.cognitiveservices.azure.com/",
    secret_name="AZURE-OPENAI-API-KEY",
)

AVAILABLE_MODELS: list[ModelDefinition] = [GPT41, GPT41_MINI]

# Literal type for Pydantic validation
ModelName = Literal["gpt-4.1", "gpt-4.1-mini"]


# --- Agent Lists by Workflow Type ---
TRIAGE_AGENTS: list[str] = [
    "triage",
    "servicenow",
    "log_analytics",
    "service_health",
    "summary",
]

DYNAMIC_AGENTS: list[str] = [
    "triage",
    "servicenow",
    "log_analytics",
    "review",
    "clarify",
    "plan",
    "service_health",
    "replan",
    "summary",
]


# --- Resolved Config (with credentials) ---
@dataclass(frozen=True)
class ResolvedModelConfig:
    """Resolved model configuration with API credentials."""

    deployment_name: str
    endpoint: str
    api_key: str


# --- Agent-Model Mapping ---
class AgentModelMapping(BaseModel):
    """Optional per-agent model override.

    Each field validates against ModelName Literal type.
    None = use workflow_model.
    """

    triage: Optional[ModelName] = None
    servicenow: Optional[ModelName] = None
    log_analytics: Optional[ModelName] = None
    service_health: Optional[ModelName] = None
    review: Optional[ModelName] = None
    clarify: Optional[ModelName] = None
    plan: Optional[ModelName] = None
    replan: Optional[ModelName] = None
    summary: Optional[ModelName] = None

    def get(self, agent_key: str) -> Optional[str]:
        """Get model name for agent, None if not specified."""
        return getattr(self, agent_key, None)


# --- Model Resolver Factory ---
def create_model_resolver(
    workflow_model: ModelName,
    agent_mapping: Optional[AgentModelMapping] = None,
) -> Callable[[str], ModelName]:
    """Create a resolver that returns model for agent_key.

    Usage:
        model_for = create_model_resolver(workflow_model, agent_mapping)
        servicenow_agent = create_servicenow_agent(registry, model_for("servicenow"))
    """
    def resolve(agent_key: str) -> ModelName:
        if agent_mapping and (model := agent_mapping.get(agent_key)):
            return model  # type: ignore[return-value]
        return workflow_model
    return resolve


# --- Model Registry ---
class ModelRegistry:
    """Registry that loads secrets at startup and resolves model configurations.

    Initialize once in app lifespan and store in app.state.
    """

    def __init__(self, akv: "AKV"):
        """Initialize registry and load required secrets.

        Args:
            akv: Azure Key Vault client with pre-loaded secrets
        """
        self._secrets: dict[str, str] = {}
        for model in AVAILABLE_MODELS:
            if model.secret_name not in self._secrets:
                self._secrets[model.secret_name] = akv.get_secret(model.secret_name)
        self._models = {m.name: m for m in AVAILABLE_MODELS}

    def get(self, model_name: ModelName) -> ResolvedModelConfig:
        """Get resolved model config by name.

        Args:
            model_name: Name of the model (validated by Literal type)

        Returns:
            ResolvedModelConfig with deployment_name, endpoint, api_key
        """
        model = self._models[model_name]
        return ResolvedModelConfig(
            deployment_name=model.deployment_name,
            endpoint=model.endpoint,
            api_key=self._secrets[model.secret_name],
        )

    def list_models(self) -> list[ModelDefinition]:
        """List all available models.

        Returns:
            List of ModelDefinition objects
        """
        return AVAILABLE_MODELS
