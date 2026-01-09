"""Core building blocks and cross-cutting concerns."""

from .events import (
    emit_event,
    get_current_message_seq,
    get_current_queue,
    set_current_message_seq,
    set_current_queue,
)

__all__ = [
    "emit_event",
    "get_current_message_seq",
    "get_current_queue",
    "set_current_message_seq",
    "set_current_queue",
]
