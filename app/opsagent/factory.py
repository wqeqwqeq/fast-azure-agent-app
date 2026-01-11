"""Agent factory supporting both env settings and registry modes.

Mode 1 (registry=None): Use env settings (AzOpenAIEnvSettings) for local dev
Mode 2/3 (registry provided): Use ModelRegistry for cloud deployment
"""

from typing import Any, List, Optional, Type

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from .middleware.observability import (
    observability_agent_middleware,
    observability_function_middleware,
)
from .model_registry import AzOpenAIEnvSettings, ModelName, ModelRegistry


def create_agent(
    name: str,
    description: str,
    instructions: str,
    registry: Optional[ModelRegistry] = None,
    model_name: Optional[ModelName] = None,
    response_format: Optional[Type] = None,
    tools: Optional[List] = None,
) -> ChatAgent:
    """Create ChatAgent with model configuration.

    Args:
        name: Agent name
        description: Agent description
        instructions: System prompt
        registry: ModelRegistry for cloud mode, None for env settings
        model_name: Model to use (required when registry provided)
        response_format: Optional Pydantic output schema
        tools: Optional list of tool functions

    Returns:
        Configured ChatAgent instance

    Raises:
        ValueError: If registry is provided but model_name is None
    """
    if registry is None:
        # Mode 1: env settings for local dev
        env = AzOpenAIEnvSettings()
        api_key = env.azure_openai_api_key
        endpoint = env.azure_openai_endpoint
        deployment_name = env.azure_openai_deployment_name
    else:
        # Mode 2/3: registry (model_name required)
        if model_name is None:
            raise ValueError("model_name is required when registry is provided")
        resolved = registry.get(model_name)
        api_key = resolved.api_key
        endpoint = resolved.endpoint
        deployment_name = resolved.deployment_name

    chat_client = AzureOpenAIChatClient(
        api_key=api_key,
        endpoint=endpoint,
        deployment_name=deployment_name,
    )

    middleware: List[Any] = [observability_agent_middleware]
    if tools:
        middleware.append(observability_function_middleware)

    return ChatAgent(
        name=name,
        description=description,
        instructions=instructions,
        chat_client=chat_client,
        response_format=response_format,
        tools=tools or [],
        middleware=middleware,
    )
