"""Memory agent module for conversation context management.

This module provides automatic summarization of conversation history using a
sliding window approach with database-based concurrency control.

Main components:
- MemoryService: Orchestrates memory retrieval and background summarization
- MemoryBackend: PostgreSQL operations for memory table (with status field)
- ConversationContext: Context prepared for workflow (memory + gap messages)
"""

from .backend import MemoryBackend
from .schemas import ConversationContext, MemoryRecord, StructuredMemory
from .service import MemoryService

__all__ = [
    "MemoryService",
    "MemoryBackend",
    "ConversationContext",
    "MemoryRecord",
    "StructuredMemory",
]
