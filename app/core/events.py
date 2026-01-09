"""Event streaming utilities for SSE responses.

Provides async-safe per-request state management for streaming events
to the frontend via Server-Sent Events (SSE).

Uses contextvars for async-safe per-request state management,
compatible with FastAPI's async execution model.
"""

import asyncio
import json
from contextvars import ContextVar
from typing import Optional

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
