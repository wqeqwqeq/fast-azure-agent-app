"""Pydantic models for agent inputs and outputs."""

# Shared workflow types
from .common import MessageData, WorkflowInput

# Triage agent schemas (for triage_workflow)
from .triage import TaskAssignment, TriageOutput

# Plan agent schemas (for dynamic_workflow)
from .triage_plan import PlanStep, TriagePlanOutput

# Replan agent schemas (for dynamic_workflow)
from .triage_replan import TriageReplanOutput

# Review agent schemas
from .review import ReviewOutput

# Clarify agent schemas
from .clarify import ClarifyOutput

__all__ = [
    # Shared
    "MessageData",
    "WorkflowInput",
    # Triage agent (triage_workflow)
    "TaskAssignment",
    "TriageOutput",
    # Plan agent (dynamic_workflow)
    "PlanStep",
    "TriagePlanOutput",
    # Replan agent (dynamic_workflow)
    "TriageReplanOutput",
    # Review agent
    "ReviewOutput",
    # Clarify agent
    "ClarifyOutput",
]
