"""
Observability module for agent middleware.

Provides real-time streaming of agent thinking events to the frontend.
Events are emitted via an async queue that feeds into the SSE response stream.

This module uses contextvars for async-safe per-request state management,
compatible with FastAPI's async execution model.
"""

import asyncio
import json
import logging
import os
from contextvars import ContextVar
from typing import Any, Optional

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


# Context variable for per-request event queue (async-safe)
_current_queue: ContextVar[Optional[asyncio.Queue]] = ContextVar(
    "current_queue", default=None
)

# Context variable for current message sequence number
_current_message_seq: ContextVar[Optional[int]] = ContextVar(
    "current_message_seq", default=None
)


def set_current_queue(queue: Optional[asyncio.Queue]) -> None:
    """Set the current event queue for this async context.

    Args:
        queue: The asyncio.Queue instance, or None to clear
    """
    _current_queue.set(queue)


def get_current_queue() -> Optional[asyncio.Queue]:
    """Get the current event queue for this async context.

    Returns:
        The asyncio.Queue instance, or None if not set
    """
    return _current_queue.get()


def set_current_message_seq(seq: Optional[int]) -> None:
    """Set the current message sequence number for this async context.

    Args:
        seq: The message sequence number, or None to clear
    """
    _current_message_seq.set(seq)


def get_current_message_seq() -> Optional[int]:
    """Get the current message sequence number for this async context.

    Returns:
        The message sequence number, or None if not set
    """
    return _current_message_seq.get()


async def emit_event(event_data: dict) -> None:
    """Emit an event to the current queue if available.

    Args:
        event_data: Dictionary containing event data (will be JSON serialized)
    """
    queue = get_current_queue()
    if queue:
        # Add sequence number to event
        seq = get_current_message_seq()
        if seq is not None:
            event_data["seq"] = seq

        # Format as SSE event
        sse_event = f"event: thinking\ndata: {json.dumps(event_data)}\n\n"
        await queue.put(sse_event)


@agent_middleware
async def observability_agent_middleware(context, next):  # type: ignore
    """Log agent invocation and completion.

    Emits events when an agent starts and finishes execution.
    """
    agent_name = context.agent.name

    await emit_event({
        "type": "agent_invoked",
        "agent": agent_name,
    })

    await next(context)

    await emit_event({
        "type": "agent_finished",
        "agent": agent_name,
    })


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
    func_name = context.function.name

    await emit_event({
        "type": "function_start",
        "function": func_name,
        "arguments": context.arguments.model_dump(),
    })

    await next(context)

    await emit_event({
        "type": "function_end",
        "function": func_name,
        "result": serialize_result(context.result),
    })
