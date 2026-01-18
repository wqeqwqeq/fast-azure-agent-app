"""Observability middleware for agent execution.

Provides real-time streaming of agent thinking events to the frontend.
Events are emitted via an async queue that feeds into the SSE response stream.
"""

import json
import logging
from typing import Any

from agent_framework import agent_middleware, function_middleware

from app.core.events import emit_event

logger = logging.getLogger(__name__)


@agent_middleware
async def observability_agent_middleware(context, next):  # type: ignore
    """Log agent invocation and completion.

    Emits events when an agent starts and finishes execution.
    For orchestration agents, also emits the structured output.
    """
    agent_name = context.agent.name

    await emit_event({
        "type": "agent_invoked",
        "agent": agent_name,
    })

    await next(context)

    # For orchestration agents, wrap generator to collect output
    # Lazy import to avoid circular dependency
    from app.config import get_settings
    if agent_name in get_settings().orchestration_agents:
        original_result = context.result

        if hasattr(original_result, "__anext__"):
            # Wrap the async generator to emit agent_finished with output when done
            async def wrapped_generator():
                collected_text = []
                async for item in original_result:
                    if hasattr(item, "text") and item.text:
                        collected_text.append(item.text)
                    yield item

                # After generator exhausted, emit agent_finished with output
                final_output = "".join(collected_text) if collected_text else None
                await emit_event({
                    "type": "agent_finished",
                    "agent": agent_name,
                    "output": serialize_result(final_output) if final_output else None,
                })

            context.result = wrapped_generator()
        else:
            # Non-streaming result
            output = None
            if hasattr(original_result, "text") and original_result.text:
                output = original_result.text
            await emit_event({
                "type": "agent_finished",
                "agent": agent_name,
                "output": serialize_result(output) if output else None,
            })
    else:
        # Non-orchestration agents - emit without output
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


