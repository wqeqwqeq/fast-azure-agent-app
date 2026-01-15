"""Pydantic schemas for message-related API endpoints."""

from typing import Optional

from pydantic import BaseModel, Field, field_validator

from ..opsagent.model_registry import AgentModelMapping


class SendMessageRequest(BaseModel):
    """Schema for sending a message to a conversation."""

    message: str = Field(..., min_length=1, description="User message content")
    workflow_model: Optional[str] = Field(None, description="Model for workflow execution")
    agent_model_mapping: Optional[AgentModelMapping] = Field(
        None, description="Per-agent model overrides"
    )
    react_mode: bool = Field(False, description="Use ReAct (dynamic) workflow instead of triage")

    @field_validator("message", mode="before")
    @classmethod
    def strip_message(cls, v: str) -> str:
        """Strip whitespace before validation."""
        return v.strip() if isinstance(v, str) else v


