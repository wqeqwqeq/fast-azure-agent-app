"""Plan agent output schema.

This schema is used by the plan agent to analyze user queries
and create execution plans.
"""

from typing import Literal

from pydantic import BaseModel, Field


class PlanStep(BaseModel):
    """A single step in the execution plan."""

    step: int = Field(description="Step number (1-based). Same step = parallel execution")
    agent: Literal["servicenow", "log_analytics", "service_health"] = Field(
        description="Target agent for this task"
    )
    question: str = Field(description="Clear, specific task for this agent")


class TriagePlanOutput(BaseModel):
    """Output from plan agent - initial query analysis."""

    action: Literal["plan", "clarify", "reject"] = Field(
        description="Action to take: plan (execute), clarify (need more info), reject (out of scope)"
    )
    reject_reason: str = Field(
        default="", description="Reason for rejection or clarification"
    )
    plan: list[PlanStep] = Field(
        default_factory=list, description="Execution plan with step numbers"
    )
    plan_reason: str = Field(
        default="", description="Explanation of why this plan was chosen"
    )
