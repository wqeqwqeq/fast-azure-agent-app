"""Clarify Agent for handling ambiguous user requests.

This agent helps users refine unclear queries by providing
polite clarification requests and possible interpretations.
"""

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from ..middleware.observability import observability_agent_middleware
from ..prompts.clarify_agent import CLARIFY_AGENT
from ..schemas.clarify import ClarifyOutput
from ..utils.settings import get_azure_openai_settings


def create_clarify_agent() -> ChatAgent:
    """Create and return the Clarify agent for handling ambiguous requests."""
    settings = get_azure_openai_settings()

    chat_client = AzureOpenAIChatClient(
        api_key=settings.azure_openai_api_key,
        endpoint=settings.azure_openai_endpoint,
        deployment_name=CLARIFY_AGENT.deployment_name or settings.azure_openai_deployment_name,
    )

    return ChatAgent(
        name=CLARIFY_AGENT.name,
        description=CLARIFY_AGENT.description,
        instructions=CLARIFY_AGENT.instructions,
        chat_client=chat_client,
        response_format=ClarifyOutput,
        middleware=[observability_agent_middleware],
    )
