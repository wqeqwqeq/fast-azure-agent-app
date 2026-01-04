"""Triage Agent for routing user queries to specialized agents."""

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from ..middleware.observability import (
    observability_agent_middleware,
    observability_function_middleware,
)
from ..prompts.triage_agent import TRIAGE_AGENT
from ..schemas.triage import TriageOutput
from ..utils.settings import get_azure_openai_settings


def create_triage_agent() -> ChatAgent:
    """Create and return the Triage agent."""
    settings = get_azure_openai_settings()

    chat_client = AzureOpenAIChatClient(
        api_key=settings.api_key,
        endpoint=settings.endpoint,
        deployment_name=settings.deployment_name,
    )

    return ChatAgent(
        name=TRIAGE_AGENT.name,
        description=TRIAGE_AGENT.description,
        instructions=TRIAGE_AGENT.instructions,
        chat_client=chat_client,
        response_format=TriageOutput,
        middleware=[
            observability_agent_middleware,
            observability_function_middleware,
        ],
    )
