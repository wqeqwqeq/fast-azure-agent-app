"""Pydantic schemas for message-related API endpoints."""

from pydantic import BaseModel, Field, field_validator


class SendMessageRequest(BaseModel):
    """Schema for sending a message to a conversation."""

    message: str = Field(..., min_length=1, description="User message content")

    @field_validator("message", mode="before")
    @classmethod
    def strip_message(cls, v: str) -> str:
        """Strip whitespace before validation."""
        return v.strip() if isinstance(v, str) else v


