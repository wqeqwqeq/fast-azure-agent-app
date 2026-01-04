"""Clarify agent output schema."""

from pydantic import BaseModel, Field


class ClarifyOutput(BaseModel):
    """Structured output from clarify agent."""

    clarification_request: str = Field(
        description="Polite request for clarification"
    )
    possible_interpretations: list[str] = Field(
        default_factory=list,
        description="What user might have meant (2-4 options)",
    )
