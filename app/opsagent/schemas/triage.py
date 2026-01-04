"""Triage agent output schemas."""

from typing import Literal

from pydantic import BaseModel, Field


class TaskAssignment(BaseModel):
    """A single task assignment to a specialized agent."""

    question: str
    agent: Literal["servicenow", "log_analytics", "service_health"]


class TriageOutput(BaseModel):
    """Structured output from the triage agent."""

    should_reject: bool
    reject_reason: str
    tasks: list[TaskAssignment]


class PlanStep(BaseModel):
    """A single step in the execution plan."""

    step: int = Field(description="Step number (1-based). Same step = parallel execution")
    agent: Literal["servicenow", "log_analytics", "service_health"] = Field(
        description="Target agent for this task"
    )
    question: str = Field(description="Clear, specific task for this agent")


class UserModeOutput(BaseModel):
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
    plan: list[PlanStep] = Field(
        default_factory=list, description="Execution plan with step numbers"
    )
    plan_reason: str = Field(
        default="", description="Explanation of why this plan was chosen"
    )


class ReviewModeOutput(BaseModel):
    """Output when triage processes REVIEWER feedback (after review agent)."""

    accept_review: bool = Field(
        description="True = accept feedback and execute new plan, False = reject feedback"
    )
    new_plan: list[PlanStep] = Field(
        default_factory=list,
        description="Additional/new plan if accepting review",
    )
    rejection_reason: str = Field(
        default="",
        description="Why current answer is sufficient (if rejecting review)",
    )
