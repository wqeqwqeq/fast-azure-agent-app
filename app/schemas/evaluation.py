"""Pydantic schemas for message evaluation (thumb up/down)."""

from typing import Optional

from pydantic import BaseModel, Field


class EvaluationUpdate(BaseModel):
    """Request schema for setting message evaluation."""

    is_satisfy: bool = Field(
        ...,
        description="Satisfaction: true=thumb up, false=thumb down",
    )
    comment: Optional[str] = Field(
        None,
        max_length=2000,
        description="Optional feedback comment (max 2000 characters)",
    )


class EvaluationResponse(BaseModel):
    """Response schema for message evaluation."""

    conversation_id: str
    sequence_number: int
    is_satisfy: Optional[bool]
    comment: Optional[str]
