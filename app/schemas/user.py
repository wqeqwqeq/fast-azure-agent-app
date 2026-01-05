"""Pydantic schemas for user-related API endpoints."""

from typing import Optional

from pydantic import BaseModel, Field


class UserInfo(BaseModel):
    """Schema for user information from Azure Easy Auth SSO."""

    user_id: str = Field(..., description="User client ID (Azure Entra ID)")
    user_name: str = Field(..., description="User display name")
    first_name: Optional[str] = Field(None, description="User's first name")
    principal_name: Optional[str] = Field(None, description="User principal name (email)")
    is_authenticated: bool = Field(..., description="Whether user is authenticated via SSO")
    mode: str = Field(..., description="Authentication mode (postgres, redis, etc.)")
