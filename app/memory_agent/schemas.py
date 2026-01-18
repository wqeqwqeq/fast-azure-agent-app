"""Memory agent schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MemoryRecord(BaseModel):
    """Memory record from database."""

    memory_id: int
    conversation_id: str
    memory_text: str
    start_sequence: int
    end_sequence: int
    created_at: datetime
    generation_time_ms: Optional[int] = None


class MemorySummaryOutput(BaseModel):
    """Structured output from memory summarization agent."""

    summary: str = Field(description="Concise summary of the conversation segment")


class ConversationContext(BaseModel):
    """Context prepared for workflow with memory + recent messages."""

    memory_text: Optional[str] = None  # Summarized old context (None if no memory yet)
    recent_messages: list[dict]  # Recent messages within rolling window
