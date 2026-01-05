"""Pydantic schemas for SSE event types from middleware."""

from typing import Any, Dict, Literal

from pydantic import BaseModel, Field


class FunctionStartEvent(BaseModel):
    """Event emitted when a function/tool call starts."""

    type: Literal["function_start"] = Field(default="function_start")
    function: str = Field(..., description="Name of the function being called")
    arguments: Dict[str, Any] = Field(..., description="Function arguments")


class FunctionEndEvent(BaseModel):
    """Event emitted when a function/tool call completes."""

    type: Literal["function_end"] = Field(default="function_end")
    function: str = Field(..., description="Name of the function that completed")
    result: Any = Field(..., description="Function return value")


class AgentInvokedEvent(BaseModel):
    """Event emitted when an agent is invoked."""

    type: Literal["agent_invoked"] = Field(default="agent_invoked")
    agent: str = Field(..., description="Name of the agent being invoked")


class AgentFinishedEvent(BaseModel):
    """Event emitted when an agent finishes execution."""

    type: Literal["agent_finished"] = Field(default="agent_finished")
    agent: str = Field(..., description="Name of the agent that finished")
