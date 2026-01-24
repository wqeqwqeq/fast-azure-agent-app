"""Orchestration agents for Agent Factory.

These agents handle workflow orchestration:
- triage: Routes queries to specialized agents (triage workflow)
- plan: Creates execution plans (dynamic workflow)
- replan: Handles review feedback (dynamic workflow)
- review: Evaluates execution results (dynamic workflow)
- clarify: Handles ambiguous requests (both workflows)
- summary: Generates final streaming response (both workflows)

All orchestration agents receive their prompts from the PromptBuilder,
which injects dynamic content based on the configured sub-agents.
"""

from .clarify_agent import create_clarify_agent
from .plan_agent import create_plan_agent
from .replan_agent import create_replan_agent
from .review_agent import create_review_agent
from .summary_agent import create_summary_agent
from .triage_agent import create_triage_agent

__all__ = [
    "create_triage_agent",
    "create_plan_agent",
    "create_replan_agent",
    "create_review_agent",
    "create_clarify_agent",
    "create_summary_agent",
]
