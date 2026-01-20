"""Plan Agent for creating execution plans.

This agent analyzes queries and creates multi-step execution plans.
Prompt and schema are built dynamically from SubAgentRegistry.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ...factory import create_agent
from ...prompts.templates import PLAN_TEMPLATE
from ...schemas.dynamic import create_triage_plan_output_schema

if TYPE_CHECKING:
    from agent_framework import ChatAgent
    from pydantic import BaseModel

    from ...model_registry import ModelName, ModelRegistry
    from ...subagent_registry import SubAgentRegistry


@dataclass(frozen=True)
class PlanAgentConfig:
    """Configuration for Plan agent with build methods."""

    name: str = "plan-agent"
    description: str = "Analyzes queries and creates execution plans"

    def build_prompt(self, registry: "SubAgentRegistry") -> str:
        """Build the plan prompt from registry."""
        return PLAN_TEMPLATE.format(
            domain_name=registry.domain_name,
            domain_description=registry.domain_description,
            agent_descriptions_with_tools=registry.generate_descriptions_with_tools(),
            additional_instructions="",
        )

    def build_schema(self, registry: "SubAgentRegistry") -> type["BaseModel"]:
        """Build the output schema from registry."""
        return create_triage_plan_output_schema(registry.agent_keys)


CONFIG = PlanAgentConfig()


def create_plan_agent(
    sub_registry: "SubAgentRegistry",
    model_registry: Optional["ModelRegistry"] = None,
    model_name: Optional["ModelName"] = None,
) -> "ChatAgent":
    """Create the Plan agent with dynamic prompt and schema."""
    return create_agent(
        name=CONFIG.name,
        description=f"Creates execution plans for {sub_registry.domain_name}",
        instructions=CONFIG.build_prompt(sub_registry),
        registry=model_registry,
        model_name=model_name,
        response_format=CONFIG.build_schema(sub_registry),
    )
