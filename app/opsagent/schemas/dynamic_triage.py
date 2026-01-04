"""Dynamic triage agent output schemas.

This module contains schemas for the dynamic triage agent which operates in two modes:
- User Mode: Analyzes user queries and creates execution plans
- Review Mode: Evaluates reviewer feedback and decides on retry strategy
"""

from typing import Literal

from pydantic import BaseModel, Field


class DynamicTriagePlanStep(BaseModel):
    """A single step in the execution plan."""

    step: int = Field(description="Step number (1-based). Same step = parallel execution")
    agent: Literal["servicenow", "log_analytics", "service_health"] = Field(
        description="Target agent for this task"
    )
    question: str = Field(description="Clear, specific task for this agent")


class DynamicTriageUserModeOutput(BaseModel):
    """Output when triage processes USER query (initial request)."""

    should_reject: bool = Field(
        default=False, description="True if query should be rejected"
    )
    reject_reason: str = Field(
        default="", description="Reason for rejection if should_reject is True"
    )
    clarify: bool = Field(
        default=False,
        description="If True with should_reject=True, route to clarify agent",
    )
    plan: list[DynamicTriagePlanStep] = Field(
        default_factory=list, description="Execution plan with step numbers"
    )
    plan_reason: str = Field(
        default="", description="Explanation of why this plan was chosen"
    )


class DynamicTriageReviewModeOutput(BaseModel):
    """Output when triage processes REVIEWER feedback (after review agent)."""

    accept_review: bool = Field(
        description="True = accept feedback and execute new plan, False = reject feedback"
    )
    new_plan: list[DynamicTriagePlanStep] = Field(
        default_factory=list,
        description="Additional/new plan if accepting review",
    )
    rejection_reason: str = Field(
        default="",
        description="Why current answer is sufficient (if rejecting review)",
    )
