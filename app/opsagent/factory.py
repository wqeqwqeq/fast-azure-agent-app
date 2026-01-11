"""通用 Agent 工厂函数.

提供统一的 ChatAgent 创建逻辑，减少各 agent 文件的重复代码。
"""

from typing import Any, List, Optional, Type

from agent_framework import ChatAgent
from agent_framework.azure import AzureOpenAIChatClient

from .middleware.observability import (
    observability_agent_middleware,
    observability_function_middleware,
)
from .settings import ModelConfig, resolve_model_config


def create_agent(
    name: str,
    description: str,
    instructions: str,
    model_config: Optional[ModelConfig] = None,
    response_format: Optional[Type] = None,
    tools: Optional[List] = None,
    # Agent 级别的模型配置 (优先级最高)
    deployment_name: str = "",
    api_key: str = "",
    endpoint: str = "",
) -> ChatAgent:
    """创建 ChatAgent 的通用工厂函数.

    Args:
        name: Agent 名称
        description: Agent 描述
        instructions: System prompt
        model_config: 可选的模型配置覆盖 (优先级: 中)
        response_format: 可选的 Pydantic 输出 schema (用于无 tools 的 agent)
        tools: 可选的 tool 函数列表
        deployment_name: Agent 级别的 deployment 配置 (优先级: 最高)
        api_key: Agent 级别的 API key 配置 (优先级: 最高)
        endpoint: Agent 级别的 endpoint 配置 (优先级: 最高)

    Returns:
        配置好的 ChatAgent 实例

    Model Config Priority (highest to lowest):
        1. Agent config (deployment_name, api_key, endpoint)
        2. Injected ModelConfig
        3. Environment settings
    """
    resolved = resolve_model_config(
        model_config=model_config,
        agent_config_deployment=deployment_name,
        agent_config_api_key=api_key,
        agent_config_endpoint=endpoint,
    )

    chat_client = AzureOpenAIChatClient(
        api_key=resolved.api_key,
        endpoint=resolved.endpoint,
        deployment_name=resolved.deployment_name,
    )

    # 有 tools 的 agent 需要额外的 function middleware
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
