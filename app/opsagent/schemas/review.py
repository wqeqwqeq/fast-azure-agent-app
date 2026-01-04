"""Review agent output schema."""

from pydantic import BaseModel, Field


class ReviewOutput(BaseModel):
    """Structured output from review agent."""

    is_complete: bool = Field(
        description="Whether all user questions are adequately answered"
    )
    summary: str = Field(
        default="", description="Final summary of findings (if complete)"
    )
    missing_aspects: list[str] = Field(
        default_factory=list,
        description="What information is missing (if incomplete)",
    )
    suggested_approach: str = Field(
        default="",
        description="Suggestion for how to address gaps using available agents",
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence in assessment (0.0 to 1.0)",
    )
