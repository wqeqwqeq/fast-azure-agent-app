"""Replan agent output schema.

This schema is used by the replan agent to process review feedback
and decide on retry strategy.
"""

from pydantic import BaseModel, Field

from .triage_plan import PlanStep


class TriageReplanOutput(BaseModel):
    """Output from replan agent - review feedback handling."""

    action: str = Field(
        default="reject",
        description="Action: 'retry' = execute new plan, 'clarify' = need user input, 'reject' = current answer sufficient",
    )
    new_plan: list[PlanStep] = Field(
        default_factory=list,
        description="Additional plan steps if action is 'retry'",
    )
    rejection_reason: str = Field(
        default="",
        description="Why current answer is sufficient (if action is 'reject')",
    )
    clarification_reason: str = Field(
        default="",
        description="Why clarification is needed from user (if action is 'clarify')",
    )
