"""Dynamic Triage Agent for multi-step execution planning.

This agent operates in two modes:
- User Mode: Analyzes user queries and creates execution plans
- Review Mode: Evaluates reviewer feedback and decides on retry strategy
"""

from typing import Optional

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from ..middleware.observability import observability_agent_middleware
from ..prompts.dynamic_triage_agent import DYNAMIC_TRIAGE_AGENT
from ..schemas.dynamic_triage import (
    DynamicTriageReviewModeOutput,
    DynamicTriageUserModeOutput,
)
from ..settings import ModelConfig, resolve_model_config


def create_user_mode_triage_agent(model_config: Optional[ModelConfig] = None) -> ChatAgent:
    """Create triage agent for user mode with DynamicTriageUserModeOutput response format.

    Args:
        model_config: Optional model configuration override. If None, uses
                     singleton settings. Partial overrides are supported.

    Returns:
        Configured ChatAgent instance for user mode
    """
    resolved = resolve_model_config(
        model_config=model_config,
        agent_config_deployment=DYNAMIC_TRIAGE_AGENT.deployment_name,
        agent_config_api_key=DYNAMIC_TRIAGE_AGENT.api_key,
        agent_config_endpoint=DYNAMIC_TRIAGE_AGENT.endpoint,
    )

    chat_client = AzureOpenAIChatClient(
        api_key=resolved.api_key,
        endpoint=resolved.endpoint,
        deployment_name=resolved.deployment_name,
    )

    return ChatAgent(
        name=f"{DYNAMIC_TRIAGE_AGENT.name}-user-mode",
        description=DYNAMIC_TRIAGE_AGENT.description,
        instructions=DYNAMIC_TRIAGE_AGENT.instructions,
        chat_client=chat_client,
        response_format=DynamicTriageUserModeOutput,
        middleware=[observability_agent_middleware],
    )


def create_review_mode_triage_agent(model_config: Optional[ModelConfig] = None) -> ChatAgent:
    """Create triage agent for review mode with DynamicTriageReviewModeOutput response format.

    Args:
        model_config: Optional model configuration override. If None, uses
                     singleton settings. Partial overrides are supported.

    Returns:
        Configured ChatAgent instance for review mode
    """
    resolved = resolve_model_config(
        model_config=model_config,
        agent_config_deployment=DYNAMIC_TRIAGE_AGENT.deployment_name,
        agent_config_api_key=DYNAMIC_TRIAGE_AGENT.api_key,
        agent_config_endpoint=DYNAMIC_TRIAGE_AGENT.endpoint,
    )

    chat_client = AzureOpenAIChatClient(
        api_key=resolved.api_key,
        endpoint=resolved.endpoint,
        deployment_name=resolved.deployment_name,
    )

    return ChatAgent(
        name=f"{DYNAMIC_TRIAGE_AGENT.name}-review-mode",
        description=DYNAMIC_TRIAGE_AGENT.description,
        instructions=DYNAMIC_TRIAGE_AGENT.instructions,
        chat_client=chat_client,
        response_format=DynamicTriageReviewModeOutput,
        middleware=[observability_agent_middleware],
    )
