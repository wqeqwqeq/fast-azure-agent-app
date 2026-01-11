"""Review Agent for evaluating execution results.

This agent reviews the output from specialized agents and determines
if the user's query has been fully answered.
"""

from typing import Optional

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from ..middleware.observability import observability_agent_middleware
from ..prompts.review_agent import REVIEW_AGENT
from ..schemas.review import ReviewOutput
from ..settings import ModelConfig, resolve_model_config


def create_review_agent(model_config: Optional[ModelConfig] = None) -> ChatAgent:
    """Create and return the Review agent for result evaluation.

    Args:
        model_config: Optional model configuration override. If None, uses
                     singleton settings. Partial overrides are supported.

    Returns:
        Configured ChatAgent instance
    """
    resolved = resolve_model_config(
        model_config=model_config,
        agent_config_deployment=REVIEW_AGENT.deployment_name,
        agent_config_api_key=REVIEW_AGENT.api_key,
        agent_config_endpoint=REVIEW_AGENT.endpoint,
    )

    chat_client = AzureOpenAIChatClient(
        api_key=resolved.api_key,
        endpoint=resolved.endpoint,
        deployment_name=resolved.deployment_name,
    )

    return ChatAgent(
        name=REVIEW_AGENT.name,
        description=REVIEW_AGENT.description,
        instructions=REVIEW_AGENT.instructions,
        chat_client=chat_client,
        response_format=ReviewOutput,
        middleware=[observability_agent_middleware],
    )
