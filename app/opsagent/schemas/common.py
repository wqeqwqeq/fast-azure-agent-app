"""Shared types for workflow input processing."""

from pydantic import BaseModel


class MessageData(BaseModel):
    """Raw message data for Flask/DevUI compatibility."""

    role: str
    text: str


class WorkflowInput(BaseModel):
    """Standard input for all workflows."""

    query: str = ""  # Simple string input for DevUI
    messages: list[MessageData] = []  # Full message history for Flask
