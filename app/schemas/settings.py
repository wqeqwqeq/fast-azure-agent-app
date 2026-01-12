"""Pydantic schemas for settings-related API endpoints."""

from pydantic import BaseModel, Field


class SettingsResponse(BaseModel):
    """Schema for UI settings/feature flags."""

    show_func_result: bool = Field(..., description="Whether to show function results in UI")
