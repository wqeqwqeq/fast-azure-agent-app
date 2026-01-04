"""Review Agent for evaluating execution results.

This agent reviews the output from specialized agents and determines
if the user's query has been fully answered.
"""

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from ..middleware.observability import observability_agent_middleware
from ..prompts.review_agent import REVIEW_AGENT
from ..schemas.review import ReviewOutput
from ..utils.settings import get_azure_openai_settings


def create_review_agent() -> ChatAgent:
    """Create and return the Review agent for result evaluation."""
    settings = get_azure_openai_settings()

    chat_client = AzureOpenAIChatClient(
        api_key=settings.azure_openai_api_key,
        endpoint=settings.azure_openai_endpoint,
        deployment_name=REVIEW_AGENT.deployment_name or settings.azure_openai_deployment_name,
    )

    return ChatAgent(
        name=REVIEW_AGENT.name,
        description=REVIEW_AGENT.description,
        instructions=REVIEW_AGENT.instructions,
        chat_client=chat_client,
        response_format=ReviewOutput,
        middleware=[observability_agent_middleware],
    )
