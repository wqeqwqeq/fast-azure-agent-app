"""Clarify Agent for handling ambiguous user requests.

This agent helps users refine unclear queries by providing
polite clarification requests and possible interpretations.
"""

from typing import Optional

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from ..middleware.observability import observability_agent_middleware
from ..prompts.clarify_agent import CLARIFY_AGENT
from ..schemas.clarify import ClarifyOutput
from ..settings import ModelConfig, resolve_model_config


def create_clarify_agent(model_config: Optional[ModelConfig] = None) -> ChatAgent:
    """Create and return the Clarify agent for handling ambiguous requests.

    Args:
        model_config: Optional model configuration override. If None, uses
                     singleton settings. Partial overrides are supported.

    Returns:
        Configured ChatAgent instance
    """
    resolved = resolve_model_config(
        model_config=model_config,
        agent_config_deployment=CLARIFY_AGENT.deployment_name,
        agent_config_api_key=CLARIFY_AGENT.api_key,
        agent_config_endpoint=CLARIFY_AGENT.endpoint,
    )

    chat_client = AzureOpenAIChatClient(
        api_key=resolved.api_key,
        endpoint=resolved.endpoint,
        deployment_name=resolved.deployment_name,
    )

    return ChatAgent(
        name=CLARIFY_AGENT.name,
        description=CLARIFY_AGENT.description,
        instructions=CLARIFY_AGENT.instructions,
        chat_client=chat_client,
        response_format=ClarifyOutput,
        middleware=[observability_agent_middleware],
    )
