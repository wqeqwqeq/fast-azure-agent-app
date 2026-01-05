"""AsyncEventStream for SSE streaming of middleware events.

This module provides async-safe event streaming for FastAPI SSE endpoints.
Events are emitted by middleware during workflow execution and consumed
by the SSE endpoint.
"""

import asyncio
from contextvars import ContextVar
from typing import AsyncIterator, Optional

# Context variable for per-request stream access (replaces threading.local)
_current_stream: ContextVar[Optional["AsyncEventStream"]] = ContextVar(
    "current_stream", default=None
)


def set_current_stream(stream: Optional["AsyncEventStream"]) -> None:
    """Set the current stream for this async context.

    Args:
        stream: The AsyncEventStream instance, or None to clear
    """
    _current_stream.set(stream)


def get_current_stream() -> Optional["AsyncEventStream"]:
    """Get the current stream for this async context.

    Returns:
        The AsyncEventStream instance, or None if not set
    """
    return _current_stream.get()


class AsyncEventStream:
    """Async event stream for middleware to push thinking events.

    This class provides a bridge between async middleware (running inside
    the workflow) and the FastAPI SSE endpoint. Events are pushed to
    an asyncio.Queue and consumed by the SSE generator.

    Usage:
        # In SSE endpoint:
        stream = AsyncEventStream()
        await stream.start()

        # In middleware (called via set_current_stream):
        stream.emit(json.dumps({"type": "function_start", ...}))

        # In SSE generator:
        async for event in stream.iter_events():
            yield f"data: {event}\\n\\n"
    """

    def __init__(self) -> None:
        """Initialize the event stream."""
        self._queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        self._active = False

    async def start(self) -> None:
        """Start accepting events."""
        self._active = True
        # Clear any old events
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    def emit(self, message: str) -> None:
        """Emit an event to the stream.

        This is a sync method that can be called from middleware.
        Uses put_nowait for non-blocking operation.

        Args:
            message: The event message (typically JSON string)
        """
        if self._active:
            try:
                self._queue.put_nowait(message)
            except asyncio.QueueFull:
                # Queue is full, drop the message (shouldn't happen with unbounded queue)
                pass

    async def stop(self) -> None:
        """Stop the stream and signal completion."""
        self._active = False
        await self._queue.put(None)  # Sentinel to signal end

    async def iter_events(self) -> AsyncIterator[str]:
        """Iterate over events asynchronously.

        Yields events until None sentinel is received.

        Yields:
            Event messages (strings)
        """
        while True:
            event = await self._queue.get()
            if event is None:
                break
            yield event

    @property
    def is_active(self) -> bool:
        """Check if the stream is currently active."""
        return self._active
