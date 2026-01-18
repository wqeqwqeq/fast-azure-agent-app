"""Observability middleware for agent execution.

Provides real-time streaming of agent thinking events to the frontend.
Events are emitted via an async queue that feeds into the SSE response stream.
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Any

from agent_framework import AgentRunResponse, agent_middleware, function_middleware

from app.core.events import emit_event

logger = logging.getLogger(__name__)


def _extract_model_name(agent) -> str | None:
    """Extract model/deployment name from agent's chat client."""
    try:
        if hasattr(agent, "chat_client") and hasattr(agent.chat_client, "deployment_name"):
            return agent.chat_client.deployment_name
    except Exception:
        pass
    return None


def _extract_usage(result) -> dict | None:
    """Extract token usage from result's usage_details."""
    try:
        if hasattr(result, "usage_details") and result.usage_details:
            usage = result.usage_details
            return {
                "input_tokens": getattr(usage, "input_token_count", None),
                "output_tokens": getattr(usage, "output_token_count", None),
                "total_tokens": getattr(usage, "total_token_count", None),
            }
    except Exception:
        pass
    return None


@agent_middleware
async def observability_agent_middleware(context, next):  # type: ignore
    """Log agent invocation and completion.

    Emits events when an agent starts and finishes execution.
    For orchestration agents, also emits the structured output.
    Includes model name, token usage, and execution time.

    Note: The agent framework may return streaming generators even for non-streaming
    agents. We collect all updates and use AgentRunResponse.from_agent_run_response_updates()
    to get the final response with usage_details.
    """
    agent_name = context.agent.name
    model_name = _extract_model_name(context.agent)
    start_time = datetime.now(timezone.utc)

    await emit_event({
        "type": "agent_invoked",
        "agent": agent_name,
    })

    await next(context)

    # Lazy import to avoid circular dependency
    from app.config import get_settings
    original_result = context.result
    is_orchestration = agent_name in get_settings().orchestration_agents

    if hasattr(original_result, "__anext__"):
        # Streaming result - wrap generator to collect updates and emit final event
        async def wrapped_generator():
            collected_updates = []
            async for item in original_result:
                collected_updates.append(item)
                yield item

            # Calculate execution time
            end_time = datetime.now(timezone.utc)
            execution_time_ms = int((end_time - start_time).total_seconds() * 1000)

            # Convert updates to AgentRunResponse to get usage_details
            usage = None
            output = None
            if collected_updates:
                try:
                    final_response = AgentRunResponse.from_agent_run_response_updates(
                        collected_updates
                    )
                    usage = _extract_usage(final_response)
                    if is_orchestration and hasattr(final_response, "text"):
                        output = final_response.text
                except Exception as e:
                    logger.warning(f"Failed to convert updates to AgentRunResponse: {e}")

            await emit_event({
                "type": "agent_finished",
                "agent": agent_name,
                "model": model_name,
                "usage": usage,
                "execution_time_ms": execution_time_ms,
                **({"output": serialize_result(output)} if is_orchestration and output else {}),
            })

        context.result = wrapped_generator()
    else:
        # Non-streaming result - extract usage and timing directly
        end_time = datetime.now(timezone.utc)
        execution_time_ms = int((end_time - start_time).total_seconds() * 1000)
        usage = _extract_usage(original_result)

        output = None
        if is_orchestration and hasattr(original_result, "text") and original_result.text:
            output = original_result.text

        await emit_event({
            "type": "agent_finished",
            "agent": agent_name,
            "model": model_name,
            "usage": usage,
            "execution_time_ms": execution_time_ms,
            **({"output": serialize_result(output)} if is_orchestration and output else {}),
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
    - function_end: Contains function name, output result, and execution time
    """
    func_name = context.function.name
    start_time = time.perf_counter()

    await emit_event({
        "type": "function_start",
        "function": func_name,
        "arguments": context.arguments.model_dump(),
    })

    await next(context)

    execution_time_ms = int((time.perf_counter() - start_time) * 1000)

    await emit_event({
        "type": "function_end",
        "function": func_name,
        "result": serialize_result(context.result),
        "execution_time_ms": execution_time_ms,
    })


