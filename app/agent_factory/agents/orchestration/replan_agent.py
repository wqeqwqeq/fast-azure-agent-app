"""Replan Agent for handling review feedback.

This agent processes review feedback and decides on retry strategy.
Prompt and schema are built dynamically from SubAgentRegistry.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ...factory import create_agent
from ...prompts.templates import REPLAN_TEMPLATE
from ...schemas.dynamic import create_triage_replan_output_schema

if TYPE_CHECKING:
    from agent_framework import ChatAgent
    from pydantic import BaseModel

    from ...model_registry import ModelName, ModelRegistry
    from ...subagent_registry import SubAgentRegistry


@dataclass(frozen=True)
class ReplanAgentConfig:
    """Configuration for Replan agent with build methods."""

    name: str = "replan-agent"
    description: str = "Evaluates review feedback and decides on retry strategy"

    def build_prompt(self, registry: "SubAgentRegistry") -> str:
        """Build the replan prompt from registry."""
        return REPLAN_TEMPLATE.format(
            agent_descriptions_with_tools=registry.generate_descriptions_with_tools(),
        )

    def build_schema(self, registry: "SubAgentRegistry") -> type["BaseModel"]:
        """Build the output schema from registry."""
        return create_triage_replan_output_schema(registry.agent_keys)


CONFIG = ReplanAgentConfig()


def create_replan_agent(
    sub_registry: "SubAgentRegistry",
    model_registry: Optional["ModelRegistry"] = None,
    model_name: Optional["ModelName"] = None,
) -> "ChatAgent":
    """Create the Replan agent with dynamic prompt and schema."""
    return create_agent(
        name=CONFIG.name,
        description=CONFIG.description,
        instructions=CONFIG.build_prompt(sub_registry),
        registry=model_registry,
        model_name=model_name,
        response_format=CONFIG.build_schema(sub_registry),
    )
