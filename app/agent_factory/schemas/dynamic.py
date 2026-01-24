"""Dynamic schema generation for Agent Factory.

This module generates Pydantic schemas at runtime based on the configured agents.
These schemas are used for structured output from orchestration agents.
"""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


def create_task_assignment_schema(valid_agents: list[str]) -> type[BaseModel]:
    """Create a TaskAssignment schema with validated agent field.

    Args:
        valid_agents: List of valid agent keys (e.g., ["leave", "payroll"])

    Returns:
        A Pydantic model class with agent validation
    """
    valid_set = frozenset(valid_agents)

    class TaskAssignment(BaseModel):
        """A single task assignment to a specialized agent."""

        question: str = Field(..., description="The specific question or task for the agent")
        agent: str = Field(..., description=f"Target agent. Must be one of: {valid_agents}")

        @field_validator("agent")
        @classmethod
        def validate_agent(cls, v: str) -> str:
            if v not in valid_set:
                raise ValueError(f"Invalid agent '{v}'. Must be one of: {list(valid_set)}")
            return v

    TaskAssignment.__name__ = "TaskAssignment"
    TaskAssignment.__qualname__ = "TaskAssignment"
    return TaskAssignment


def create_triage_output_schema(valid_agents: list[str]) -> type[BaseModel]:
    """Create a TriageOutput schema for triage workflow.

    Args:
        valid_agents: List of valid agent keys

    Returns:
        A Pydantic model class for triage output
    """
    TaskAssignment = create_task_assignment_schema(valid_agents)

    class TriageOutput(BaseModel):
        """Output schema for triage agent in triage workflow."""

        should_reject: bool = Field(
            default=False,
            description="True if the query is outside the assistant's scope",
        )
        reject_reason: str = Field(
            default="",
            description="Reason for rejection if should_reject is True",
        )
        tasks: list[TaskAssignment] = Field(
            default_factory=list,
            description="List of task assignments to specialized agents",
        )

    TriageOutput.__name__ = "TriageOutput"
    TriageOutput.__qualname__ = "TriageOutput"
    return TriageOutput


def create_plan_step_schema(valid_agents: list[str]) -> type[BaseModel]:
    """Create a PlanStep schema for dynamic workflow planning.

    Args:
        valid_agents: List of valid agent keys

    Returns:
        A Pydantic model class for plan steps
    """
    valid_set = frozenset(valid_agents)

    class PlanStep(BaseModel):
        """A single step in the execution plan.

        Steps with the same step number run in parallel.
        Steps with different numbers run sequentially.
        """

        step: int = Field(
            ...,
            description="Step number (1-indexed). Same step = parallel, different = sequential",
        )
        agent: str = Field(..., description=f"Target agent. Must be one of: {valid_agents}")
        question: str = Field(..., description="The specific question or task for this step")

        @field_validator("agent")
        @classmethod
        def validate_agent(cls, v: str) -> str:
            if v not in valid_set:
                raise ValueError(f"Invalid agent '{v}'. Must be one of: {list(valid_set)}")
            return v

    PlanStep.__name__ = "PlanStep"
    PlanStep.__qualname__ = "PlanStep"
    return PlanStep


def create_triage_plan_output_schema(valid_agents: list[str]) -> type[BaseModel]:
    """Create a TriagePlanOutput schema for dynamic workflow initial triage.

    Args:
        valid_agents: List of valid agent keys

    Returns:
        A Pydantic model class for triage plan output
    """
    PlanStep = create_plan_step_schema(valid_agents)

    class TriagePlanOutput(BaseModel):
        """Output schema for triage agent in plan mode (dynamic workflow)."""

        action: Literal["plan", "clarify", "reject"] = Field(
            ...,
            description="Action to take: 'plan' to execute, 'clarify' to ask user, 'reject' if out of scope",
        )
        reject_reason: str = Field(
            default="",
            description="Reason for rejection if action is 'reject'",
        )
        clarification_reason: str = Field(
            default="",
            description="Why clarification is needed if action is 'clarify'",
        )
        plan: list[PlanStep] = Field(
            default_factory=list,
            description="Execution plan if action is 'plan'",
        )
        plan_reason: str = Field(
            default="",
            description="Brief explanation of the plan approach",
        )

    TriagePlanOutput.__name__ = "TriagePlanOutput"
    TriagePlanOutput.__qualname__ = "TriagePlanOutput"
    return TriagePlanOutput


def create_triage_replan_output_schema(valid_agents: list[str]) -> type[BaseModel]:
    """Create a TriageReplanOutput schema for dynamic workflow replanning.

    Args:
        valid_agents: List of valid agent keys

    Returns:
        A Pydantic model class for replan output
    """
    PlanStep = create_plan_step_schema(valid_agents)

    class TriageReplanOutput(BaseModel):
        """Output schema for triage agent in replan mode (dynamic workflow)."""

        action: Literal["retry", "clarify", "complete"] = Field(
            ...,
            description="Action: 'retry' with new plan, 'clarify' to ask user, 'complete' to finish with current results",
        )
        new_plan: list[PlanStep] = Field(
            default_factory=list,
            description="New execution plan if action is 'retry'",
        )
        clarification_reason: str = Field(
            default="",
            description="Why clarification is needed if action is 'clarify'",
        )
        completion_reason: str = Field(
            default="",
            description="Why we should complete despite missing aspects if action is 'complete'",
        )

    TriageReplanOutput.__name__ = "TriageReplanOutput"
    TriageReplanOutput.__qualname__ = "TriageReplanOutput"
    return TriageReplanOutput


def create_review_output_schema() -> type[BaseModel]:
    """Create a ReviewOutput schema (not agent-dependent)."""

    class ReviewOutput(BaseModel):
        """Output schema for review agent."""

        is_complete: bool = Field(
            ...,
            description="True if the response adequately addresses the query",
        )
        missing_aspects: list[str] = Field(
            default_factory=list,
            description="List of aspects that are missing or incomplete",
        )
        suggested_approach: str = Field(
            default="",
            description="Suggested approach to address missing aspects",
        )
        confidence: float = Field(
            default=0.0,
            ge=0.0,
            le=1.0,
            description="Confidence score (0-1) in the completeness assessment",
        )

    ReviewOutput.__name__ = "ReviewOutput"
    ReviewOutput.__qualname__ = "ReviewOutput"
    return ReviewOutput


def create_clarify_output_schema() -> type[BaseModel]:
    """Create a ClarifyOutput schema (not agent-dependent)."""

    class ClarifyOutput(BaseModel):
        """Output schema for clarify agent."""

        clarification_request: str = Field(
            ...,
            description="The clarification question to ask the user",
        )
        possible_interpretations: list[str] = Field(
            default_factory=list,
            description="Possible interpretations of the ambiguous query",
        )

    ClarifyOutput.__name__ = "ClarifyOutput"
    ClarifyOutput.__qualname__ = "ClarifyOutput"
    return ClarifyOutput
