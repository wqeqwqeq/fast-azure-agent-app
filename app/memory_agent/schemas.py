"""Memory agent schemas."""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class MemoryRecord(BaseModel):
    """Memory record from database."""

    memory_id: int
    conversation_id: str
    memory_text: str  # JSON string of StructuredMemory
    start_sequence: int
    end_sequence: int
    base_memory_id: Optional[int] = None  # Previous memory this was based on (version chain)
    status: str = "completed"  # 'processing' | 'completed' | 'failed'
    created_at: datetime
    generation_time_ms: Optional[int] = None


class ImportantEntity(BaseModel):
    """Important entity mentioned in conversation."""

    name: str = Field(description="Entity identifier (person, system, ticket ID, etc.)")
    aliases: list[str] = Field(default_factory=list, description="Alternative names")
    notes: Optional[str] = Field(default=None, description="Key info about this entity")


class StructuredMemory(BaseModel):
    """Structured memory output - all fields optional."""

    facts: Optional[list[str]] = Field(default=None, description="Confirmed information")
    decisions: Optional[list[str]] = Field(default=None, description="Conclusions reached")
    user_preferences: Optional[list[str]] = Field(default=None, description="User requirements expressed")
    open_questions: Optional[list[str]] = Field(default=None, description="Unresolved items")
    entities: Optional[list[ImportantEntity]] = Field(default=None, description="Important identifiers")


class ConversationContext(BaseModel):
    """Context prepared for workflow with memory + gap messages."""

    memory: Optional[StructuredMemory] = None  # Parsed structured memory (None if no memory yet)
    gap_messages: list[dict]  # Messages after memory but before current user message
