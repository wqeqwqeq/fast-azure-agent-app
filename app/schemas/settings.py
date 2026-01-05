"""Pydantic schemas for settings-related API endpoints."""

from typing import List

from pydantic import BaseModel, Field


class SettingsResponse(BaseModel):
    """Schema for UI settings/feature flags."""

    show_func_result: bool = Field(..., description="Whether to show function results in UI")


class ModelsResponse(BaseModel):
    """Schema for available models list."""

    models: List[str] = Field(..., description="List of available LLM model identifiers")
