"""Shared types for workflow input processing."""

from pydantic import BaseModel


class MessageData(BaseModel):
    """Raw message data for UI compatibility."""

    role: str
    text: str


class WorkflowInput(BaseModel):
    """Standard input for all workflows."""

    query: str = ""
    messages: list[MessageData] = []
