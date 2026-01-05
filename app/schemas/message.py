"""Pydantic schemas for message-related API endpoints."""

from pydantic import BaseModel, Field

from .conversation import MessageSchema


class SendMessageRequest(BaseModel):
    """Schema for sending a message to a conversation."""

    message: str = Field(..., min_length=1, description="User message content")


class SendMessageResponse(BaseModel):
    """Schema for the response after sending a message."""

    user_message: MessageSchema = Field(..., description="The user's message")
    assistant_message: MessageSchema = Field(..., description="The assistant's response")
    title: str = Field(..., description="Conversation title (may be auto-generated)")
