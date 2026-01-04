"""Dynamic Triage Agent for multi-step execution planning.

This agent operates in two modes:
- User Mode: Analyzes user queries and creates execution plans
- Review Mode: Evaluates reviewer feedback and decides on retry strategy
"""

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from ..middleware.observability import observability_agent_middleware
from ..prompts.dynamic_triage_agent import DYNAMIC_TRIAGE_AGENT
from ..schemas.triage import UserModeOutput, ReviewModeOutput
from ..utils.settings import get_azure_openai_settings


def create_user_mode_triage_agent() -> ChatAgent:
    """Create triage agent for user mode with UserModeOutput response format."""
    settings = get_azure_openai_settings()

    chat_client = AzureOpenAIChatClient(
        api_key=settings.api_key,
        endpoint=settings.endpoint,
        deployment_name=settings.deployment_name,
    )

    return ChatAgent(
        name=f"{DYNAMIC_TRIAGE_AGENT.name}-user-mode",
        description=DYNAMIC_TRIAGE_AGENT.description,
        instructions=DYNAMIC_TRIAGE_AGENT.instructions,
        chat_client=chat_client,
        response_format=UserModeOutput,
        middleware=[observability_agent_middleware],
    )


def create_review_mode_triage_agent() -> ChatAgent:
    """Create triage agent for review mode with ReviewModeOutput response format."""
    settings = get_azure_openai_settings()

    chat_client = AzureOpenAIChatClient(
        api_key=settings.api_key,
        endpoint=settings.endpoint,
        deployment_name=settings.deployment_name,
    )

    return ChatAgent(
        name=f"{DYNAMIC_TRIAGE_AGENT.name}-review-mode",
        description=DYNAMIC_TRIAGE_AGENT.description,
        instructions=DYNAMIC_TRIAGE_AGENT.instructions,
        chat_client=chat_client,
        response_format=ReviewModeOutput,
        middleware=[observability_agent_middleware],
    )
