"""Azure OpenAI settings and model configuration for opsagent.

This module provides:
- AzOpenAIEnvSettings: Settings loaded from environment variables
- ModelConfig: Optional override configuration for agent model injection
- ResolvedModelConfig: Resolved configuration with all required values
- resolve_model_config: Helper function to resolve model configuration with priority
"""

from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class AzOpenAIEnvSettings(BaseSettings):
    """Azure OpenAI configuration loaded from environment variables.

    These values serve as the lowest priority fallback when no injection
    or agent-specific config is provided.
    """

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_deployment_name: str = ""


@dataclass(frozen=True)
class ModelConfig:
    """Optional model configuration for agent injection.

    When provided to agent factories, these values override the env settings.
    All fields are optional - None means "use default from env settings".

    Example usage:
        # Use default settings from env
        agent = create_triage_agent()

        # Override deployment only
        agent = create_triage_agent(model_config=ModelConfig(deployment_name="gpt-4o"))

        # Full override for testing/multi-tenant
        agent = create_triage_agent(model_config=ModelConfig(
            deployment_name="my-gpt4",
            api_key="sk-xxx",
            endpoint="https://my-openai.azure.com/"
        ))
    """

    deployment_name: Optional[str] = None
    api_key: Optional[str] = None
    endpoint: Optional[str] = None


@dataclass(frozen=True)
class ResolvedModelConfig:
    """Fully resolved model configuration with all required values.

    This is the result of resolving a ModelConfig against env settings.
    All fields are guaranteed to be non-None strings.
    """

    deployment_name: str
    api_key: str
    endpoint: str


def resolve_model_config(
    model_config: Optional[ModelConfig] = None,
    agent_config_deployment: str = "",
    agent_config_api_key: str = "",
    agent_config_endpoint: str = "",
) -> ResolvedModelConfig:
    """Resolve model configuration with priority order.

    Priority (highest to lowest):
    1. Agent prompt config (agent_config_* parameters)
    2. Injected ModelConfig
    3. Environment settings (AzOpenAIEnvSettings)

    Args:
        model_config: Optional override configuration from caller
        agent_config_deployment: Agent-specific deployment from prompt config
        agent_config_api_key: Agent-specific API key from prompt config
        agent_config_endpoint: Agent-specific endpoint from prompt config

    Returns:
        ResolvedModelConfig with all values resolved
    """
    env_settings = AzOpenAIEnvSettings()

    return ResolvedModelConfig(
        deployment_name=(
            agent_config_deployment
            or (model_config.deployment_name if model_config else None)
            or env_settings.azure_openai_deployment_name
        ),
        api_key=(
            agent_config_api_key
            or (model_config.api_key if model_config else None)
            or env_settings.azure_openai_api_key
        ),
        endpoint=(
            agent_config_endpoint
            or (model_config.endpoint if model_config else None)
            or env_settings.azure_openai_endpoint
        ),
    )
