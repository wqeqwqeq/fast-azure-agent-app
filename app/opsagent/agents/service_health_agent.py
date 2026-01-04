"""Service Health Agent for monitoring data services."""

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from ..middleware.observability import (
    observability_agent_middleware,
    observability_function_middleware,
)
from ..prompts.service_health_agent import SERVICE_HEALTH_AGENT
from ..tools.service_health_tools import (
    check_azure_service_health,
    check_databricks_health,
    check_snowflake_health,
)
from ..utils.settings import get_azure_openai_settings


def create_service_health_agent() -> ChatAgent:
    """Create and return the Service Health agent."""
    settings = get_azure_openai_settings()

    chat_client = AzureOpenAIChatClient(
        api_key=settings.api_key,
        endpoint=settings.endpoint,
        deployment_name=settings.deployment_name,
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
