"""Service Health Agent for monitoring data services."""

from typing import Optional

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from ..middleware.observability import (
    observability_agent_middleware,
    observability_function_middleware,
)
from ..prompts.service_health_agent import SERVICE_HEALTH_AGENT
from ..settings import ModelConfig, resolve_model_config
from ..tools.service_health_tools import (
    check_azure_service_health,
    check_databricks_health,
    check_snowflake_health,
)


def create_service_health_agent(model_config: Optional[ModelConfig] = None) -> ChatAgent:
    """Create and return the Service Health agent.

    Args:
        model_config: Optional model configuration override. If None, uses
                     singleton settings. Partial overrides are supported.

    Returns:
        Configured ChatAgent instance
    """
    resolved = resolve_model_config(
        model_config=model_config,
        agent_config_deployment=SERVICE_HEALTH_AGENT.deployment_name,
        agent_config_api_key=SERVICE_HEALTH_AGENT.api_key,
        agent_config_endpoint=SERVICE_HEALTH_AGENT.endpoint,
    )

    chat_client = AzureOpenAIChatClient(
        api_key=resolved.api_key,
        endpoint=resolved.endpoint,
        deployment_name=resolved.deployment_name,
    )

    return ChatAgent(
        name=SERVICE_HEALTH_AGENT.name,
        description=SERVICE_HEALTH_AGENT.description,
        instructions=SERVICE_HEALTH_AGENT.instructions,
        chat_client=chat_client,
        tools=[check_databricks_health, check_snowflake_health, check_azure_service_health],
        middleware=[
            observability_agent_middleware,
            observability_function_middleware,
        ],
    )
