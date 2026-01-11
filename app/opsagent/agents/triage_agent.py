"""Triage Agent for routing user queries to specialized agents."""

from typing import Optional

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from ..middleware.observability import (
    observability_agent_middleware,
    observability_function_middleware,
)
from ..prompts.triage_agent import TRIAGE_AGENT
from ..schemas.triage import TriageOutput
from ..settings import ModelConfig, resolve_model_config


def create_triage_agent(model_config: Optional[ModelConfig] = None) -> ChatAgent:
    """Create and return the Triage agent.

    Args:
        model_config: Optional model configuration override. If None, uses
                     singleton settings. Partial overrides are supported.

    Returns:
        Configured ChatAgent instance
    """
    resolved = resolve_model_config(
        model_config=model_config,
        agent_config_deployment=TRIAGE_AGENT.deployment_name,
        agent_config_api_key=TRIAGE_AGENT.api_key,
        agent_config_endpoint=TRIAGE_AGENT.endpoint,
    )

    chat_client = AzureOpenAIChatClient(
        api_key=resolved.api_key,
        endpoint=resolved.endpoint,
        deployment_name=resolved.deployment_name,
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
