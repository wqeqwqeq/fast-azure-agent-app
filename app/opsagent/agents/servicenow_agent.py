"""ServiceNow Agent for ITSM operations."""

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from ..middleware.observability import (
    observability_agent_middleware,
    observability_function_middleware,
)
from ..prompts.servicenow_agent import SERVICENOW_AGENT
from ..tools.servicenow_tools import (
    get_change_request,
    get_incident,
    list_change_requests,
    list_incidents,
)
from ..utils.settings import get_azure_openai_settings


def create_servicenow_agent() -> ChatAgent:
    """Create and return the ServiceNow agent."""
    settings = get_azure_openai_settings()

    chat_client = AzureOpenAIChatClient(
        api_key=settings.api_key,
        endpoint=settings.endpoint,
        deployment_name=settings.deployment_name,
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
