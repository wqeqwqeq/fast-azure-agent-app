"""
Observability module for agent middleware.

Provides real-time streaming of agent thinking events to the frontend.
Events are emitted via an async-safe EventStream that decouples
middleware execution from HTTP response handling.

This module uses contextvars for async-safe per-request stream management,
compatible with FastAPI's async execution model.
"""

import json
import logging
import os
from contextvars import ContextVar
from typing import Any, Optional, Protocol

from agent_framework import agent_middleware, function_middleware

logger = logging.getLogger(__name__)


def get_appinsights_connection_string() -> str:
    """Get Application Insights connection string from environment or Key Vault.

    Checks in order:
    1. Environment variable 'APPLICATIONINSIGHTS_CONNECTION_STRING'
    2. Key Vault secret 'APPLICATIONINSIGHTS-CONNECTION-STRING'

    Returns:
        Application Insights connection string

    Raises:
        ValueError: If connection string not found in either source
    """
    # Try environment variable first
    env_value = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
    if env_value:
        logger.info("Loaded App Insights connection string from environment")
        return env_value

    # Fall back to Key Vault
    RESOURCE_PREFIX = os.getenv('RESOURCE_PREFIX', 'stanley-dev-ui')
    vault_name = f"{RESOURCE_PREFIX.replace('-', '')}kv"
    if vault_name:
        try:
            from ..utils.keyvault import AKV
            akv = AKV(vault_name)
            secret_value = akv.get_secret("APPLICATIONINSIGHTS-CONNECTION-STRING")
            if secret_value:
                logger.info("Loaded App Insights connection string from Key Vault")
                return secret_value
        except Exception as e:
            logger.warning(f"Failed to get App Insights connection string from Key Vault: {e}")

    raise ValueError(
        "Application Insights connection string not found. "
        "Set APPLICATIONINSIGHTS_CONNECTION_STRING environment variable "
        "or set RESOURCE_PREFIX with Key Vault secret 'APPLICATIONINSIGHTS-CONNECTION-STRING'."
    )


class EventStreamProtocol(Protocol):
    """Protocol for event stream objects (sync or async)."""

    def emit(self, message: str) -> None:
        """Emit an event to the stream."""
        ...


# Context variable for per-request stream (async-safe, replaces threading.local)
_current_stream: ContextVar[Optional[EventStreamProtocol]] = ContextVar(
    "current_stream", default=None
)


def set_current_stream(stream: Optional[EventStreamProtocol]) -> None:
    """Set the current stream for this async context.

    Args:
        stream: The EventStream instance (sync or async), or None to clear
    """
    _current_stream.set(stream)


def get_current_stream() -> Optional[EventStreamProtocol]:
    """Get the current stream for this async context.

    Returns:
        The EventStream instance, or None if not set
    """
    return _current_stream.get()


@agent_middleware
async def observability_agent_middleware(context, next):  # type: ignore
    """Log agent invocation and completion.

    Emits events when an agent starts and finishes execution.
    Format: "[AgentName] agent invoked" and "[AgentName] agent finished"
    """
    stream = get_current_stream()
    agent_name = context.agent.name

    if stream:
        stream.emit(f"[{agent_name}] agent invoked\n")

    await next(context)

    if stream:
        stream.emit(f"[{agent_name}] agent finished\n")


def serialize_result(result: Any) -> Any:
    """Serialize function result to JSON-safe format.

    Args:
        result: The function result to serialize.

    Returns:
        JSON-serializable representation of the result.
    """
    if result is None:
        return None
    if isinstance(result, str):
        # Try to parse as JSON for pretty printing in frontend
        try:
            return json.loads(result)
        except json.JSONDecodeError:
            return result
    if hasattr(result, "model_dump"):  # Pydantic model
        return result.model_dump()
    return str(result)


@function_middleware
async def observability_function_middleware(context, next):  # type: ignore
    """Log function/tool calls with input arguments and output results.

    Emits structured JSON events when a tool is called and when it completes.
    Events include:
    - function_start: Contains function name and input arguments
    - function_end: Contains function name and output result
    """
    stream = get_current_stream()
    func_name = context.function.name

    if stream:
        event = {
            "type": "function_start",
            "function": func_name,
            "arguments": context.arguments.model_dump(),
        }
        stream.emit(json.dumps(event))

    await next(context)

    if stream:
        event = {
            "type": "function_end",
            "function": func_name,
            "result": serialize_result(context.result),
        }
        stream.emit(json.dumps(event))
