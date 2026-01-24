"""Model registry with centralized, typed model definitions.

This module provides:
- AzOpenAIEnvSettings: Environment-based settings for Mode 1 (local dev)
- ModelDefinition: Immutable model configuration dataclass
- ModelRegistry: Loads secrets and resolves model configurations
- DynamicAgentModelMapping: Per-agent model override with dynamic support

Note: This is a copy of the opsagent model_registry to keep agent_factory independent.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Literal, Optional

from dotenv import load_dotenv
from pydantic import BaseModel
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from app.infrastructure.keyvault import AKV
    from .subagent_registry import SubAgentRegistry

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

# Default model for fallback
DEFAULT_MODEL: ModelName = "gpt-4.1"


# --- Resolved Config (with credentials) ---
@dataclass(frozen=True)
class ResolvedModelConfig:
    """Resolved model configuration with API credentials."""

    deployment_name: str
    endpoint: str
    api_key: str


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


# --- Dynamic Agent-Model Mapping ---
class DynamicAgentModelMapping(BaseModel):
    """Dynamic per-agent model override.

    Unlike fixed field mappings, this accepts any agent key dynamically.
    Orchestration agents have explicit fields, sub-agents use extras.
    """

    # Orchestration agents (always present)
    triage: Optional[ModelName] = None
    plan: Optional[ModelName] = None
    replan: Optional[ModelName] = None
    review: Optional[ModelName] = None
    clarify: Optional[ModelName] = None
    summary: Optional[ModelName] = None

    # Dynamic sub-agents stored in extras
    model_config = {"extra": "allow"}

    def get(self, agent_key: str) -> Optional[str]:
        """Get model name for agent, None if not specified."""
        # First check explicit fields
        if hasattr(self, agent_key):
            value = getattr(self, agent_key, None)
            if value is not None:
                return value
        # Then check extra fields
        if hasattr(self, "model_extra") and self.model_extra:
            return self.model_extra.get(agent_key)
        return None


# --- Model Resolver Factory ---
def create_dynamic_model_resolver(
    workflow_model: ModelName,
    agent_mapping: Optional[DynamicAgentModelMapping] = None,
) -> Callable[[str], ModelName]:
    """Create a resolver that returns model for any agent_key.

    Works with both orchestration agents and dynamically configured sub-agents.

    Usage:
        model_for = create_dynamic_model_resolver(workflow_model, agent_mapping)
        leave_agent = create_leave_agent(registry, model_for("leave"))

    Args:
        workflow_model: Default model to use for all agents
        agent_mapping: Optional per-agent model overrides

    Returns:
        Function that resolves model name for given agent key
    """

    def resolve(agent_key: str) -> ModelName:
        if agent_mapping and (model := agent_mapping.get(agent_key)):
            return model  # type: ignore[return-value]
        return workflow_model

    return resolve


def get_orchestration_agent_keys() -> list[str]:
    """Get list of orchestration agent keys (fixed).

    Returns:
        List of orchestration agent keys
    """
    return ["triage", "plan", "replan", "review", "clarify", "summary"]


def get_all_agent_keys(registry: "SubAgentRegistry") -> list[str]:
    """Get list of all agent keys (orchestration + sub-agents).

    Args:
        registry: SubAgentRegistry with configured sub-agents

    Returns:
        Combined list of all agent keys
    """
    return get_orchestration_agent_keys() + registry.agent_keys


__all__ = [
    "AzOpenAIEnvSettings",
    "ModelDefinition",
    "ModelName",
    "ModelRegistry",
    "ResolvedModelConfig",
    "AVAILABLE_MODELS",
    "DEFAULT_MODEL",
    "GPT41",
    "GPT41_MINI",
    "DynamicAgentModelMapping",
    "create_dynamic_model_resolver",
    "get_orchestration_agent_keys",
    "get_all_agent_keys",
]
