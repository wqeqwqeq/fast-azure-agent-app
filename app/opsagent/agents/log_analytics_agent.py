"""Log Analytics Agent for Azure Data Factory pipeline monitoring."""

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from ..middleware.observability import (
    observability_agent_middleware,
    observability_function_middleware,
)
from ..prompts.log_analytics_agent import LOG_ANALYTICS_AGENT
from ..tools.log_analytics_tools import (
    get_pipeline_run_details,
    list_failed_pipelines,
    query_pipeline_status,
)
from ..utils.settings import get_azure_openai_settings


def create_log_analytics_agent() -> ChatAgent:
    """Create and return the Log Analytics agent."""
    settings = get_azure_openai_settings()

    chat_client = AzureOpenAIChatClient(
        api_key=settings.azure_openai_api_key,
        endpoint=settings.azure_openai_endpoint,
        deployment_name=LOG_ANALYTICS_AGENT.deployment_name or settings.azure_openai_deployment_name,
    )

    return ChatAgent(
        name=LOG_ANALYTICS_AGENT.name,
        description=LOG_ANALYTICS_AGENT.description,
        instructions=LOG_ANALYTICS_AGENT.instructions,
        chat_client=chat_client,
        tools=[query_pipeline_status, get_pipeline_run_details, list_failed_pipelines],
        middleware=[
            observability_agent_middleware,
            observability_function_middleware,
        ],
    )
