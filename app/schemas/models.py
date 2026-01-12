"""Pydantic schemas for model and agent configuration API endpoints."""

from typing import List

from pydantic import BaseModel, Field


class ModelsResponse(BaseModel):
    """Schema for available models list."""

    models: List[str] = Field(..., description="List of available LLM model identifiers")


class AgentsResponse(BaseModel):
    """Schema for agent keys that can have custom models."""

    agents: List[str] = Field(..., description="List of agent keys for per-agent model override")
