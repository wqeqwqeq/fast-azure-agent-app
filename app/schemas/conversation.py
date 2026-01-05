"""Pydantic schemas for conversation-related API endpoints."""

from typing import List, Optional

from pydantic import BaseModel, Field


class MessageSchema(BaseModel):
    """Schema for a single chat message."""

    role: str = Field(..., description="Message role: 'user' or 'assistant'")
    content: str = Field(..., description="Message content")
    time: Optional[str] = Field(None, description="ISO8601 timestamp")


class ConversationCreate(BaseModel):
    """Schema for creating a new conversation."""

    model: str = Field(default="gpt-4o-mini", description="LLM model to use")


class ConversationUpdate(BaseModel):
    """Schema for updating an existing conversation."""

    title: Optional[str] = Field(None, description="New conversation title")
    model: Optional[str] = Field(None, description="New LLM model")


class ConversationResponse(BaseModel):
    """Schema for a single conversation response."""

    id: str = Field(..., description="Conversation ID")
    title: str = Field(..., description="Conversation title")
    model: str = Field(..., description="LLM model")
    messages: List[MessageSchema] = Field(default_factory=list, description="Chat messages")
    created_at: str = Field(..., description="ISO8601 creation timestamp")
    last_modified: str = Field(..., description="ISO8601 last modification timestamp")


class ConversationListResponse(BaseModel):
    """Schema for listing conversations."""

    conversations: List[ConversationResponse] = Field(
        default_factory=list, description="List of conversations"
    )
