"""Memory agent module for conversation context management.

This module provides automatic summarization of older conversation messages
to maintain context while using a rolling window of recent messages.

Main components:
- MemoryService: Orchestrates memory retrieval and background summarization
- MemoryBackend: PostgreSQL operations for memory table
- ConversationContext: Context prepared for workflow (memory + recent messages)
"""

from .backend import MemoryBackend
from .schemas import ConversationContext, MemoryRecord
from .service import MemoryService

__all__ = [
    "MemoryService",
    "MemoryBackend",
    "ConversationContext",
    "MemoryRecord",
]
