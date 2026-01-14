"""Triage agent output schemas.

This module contains schemas for the basic triage agent used in triage_workflow.
For dynamic workflow schemas, see triage_plan.py and triage_replan.py.
"""

from typing import Literal

from pydantic import BaseModel


class TaskAssignment(BaseModel):
    """A single task assignment to a specialized agent."""

    question: str
    agent: Literal["servicenow", "log_analytics", "service_health"]


class TriageOutput(BaseModel):
    """Structured output from the triage agent."""

    should_reject: bool
    reject_reason: str
    tasks: list[TaskAssignment]
