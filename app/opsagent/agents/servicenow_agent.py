"""ServiceNow Agent for ITSM operations."""

from typing import Optional

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from ..middleware.observability import (
    observability_agent_middleware,
    observability_function_middleware,
)
from ..prompts.servicenow_agent import SERVICENOW_AGENT
from ..settings import ModelConfig, resolve_model_config
from ..tools.servicenow_tools import (
    get_change_request,
    get_incident,
    list_change_requests,
    list_incidents,
)


def create_servicenow_agent(model_config: Optional[ModelConfig] = None) -> ChatAgent:
    """Create and return the ServiceNow agent.

    Args:
        model_config: Optional model configuration override. If None, uses
                     singleton settings. Partial overrides are supported.

    Returns:
        Configured ChatAgent instance
    """
    resolved = resolve_model_config(
        model_config=model_config,
        agent_config_deployment=SERVICENOW_AGENT.deployment_name,
        agent_config_api_key=SERVICENOW_AGENT.api_key,
        agent_config_endpoint=SERVICENOW_AGENT.endpoint,
    )

    chat_client = AzureOpenAIChatClient(
        api_key=resolved.api_key,
        endpoint=resolved.endpoint,
        deployment_name=resolved.deployment_name,
    )

    return ChatAgent(
        name=SERVICENOW_AGENT.name,
        description=SERVICENOW_AGENT.description,
        instructions=SERVICENOW_AGENT.instructions,
        chat_client=chat_client,
        tools=[list_change_requests, get_change_request, list_incidents, get_incident],
        middleware=[
            observability_agent_middleware,
            observability_function_middleware,
        ],
    )
