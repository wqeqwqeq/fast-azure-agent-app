"""Log Analytics Agent for Azure Data Factory pipeline monitoring."""

from typing import Optional

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from ..middleware.observability import (
    observability_agent_middleware,
    observability_function_middleware,
)
from ..prompts.log_analytics_agent import LOG_ANALYTICS_AGENT
from ..settings import ModelConfig, resolve_model_config
from ..tools.log_analytics_tools import (
    get_pipeline_run_details,
    list_failed_pipelines,
    query_pipeline_status,
)


def create_log_analytics_agent(model_config: Optional[ModelConfig] = None) -> ChatAgent:
    """Create and return the Log Analytics agent.

    Args:
        model_config: Optional model configuration override. If None, uses
                     singleton settings. Partial overrides are supported.

    Returns:
        Configured ChatAgent instance
    """
    resolved = resolve_model_config(
        model_config=model_config,
        agent_config_deployment=LOG_ANALYTICS_AGENT.deployment_name,
        agent_config_api_key=LOG_ANALYTICS_AGENT.api_key,
        agent_config_endpoint=LOG_ANALYTICS_AGENT.endpoint,
    )

    chat_client = AzureOpenAIChatClient(
        api_key=resolved.api_key,
        endpoint=resolved.endpoint,
        deployment_name=resolved.deployment_name,
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
