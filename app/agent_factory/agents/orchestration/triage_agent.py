"""Triage Agent for routing user queries to specialized agents.

This agent routes queries to appropriate sub-agents.
Prompt and schema are built dynamically from SubAgentRegistry.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ...factory import create_agent
from ...prompts.templates import TRIAGE_TEMPLATE
from ...schemas.dynamic import create_triage_output_schema

if TYPE_CHECKING:
    from agent_framework import ChatAgent
    from pydantic import BaseModel

    from ...model_registry import ModelName, ModelRegistry
    from ...subagent_registry import SubAgentRegistry


@dataclass(frozen=True)
class TriageAgentConfig:
    """Configuration for Triage agent with build methods."""

    name: str = "triage-agent"
    description: str = "Routes user queries to specialized agents"

    def build_prompt(self, registry: "SubAgentRegistry") -> str:
        """Build the triage prompt from registry.

        Args:
            registry: SubAgentRegistry with sub-agent configurations

        Returns:
            Complete prompt string with agent descriptions filled in
        """
        return TRIAGE_TEMPLATE.format(
            domain_name=registry.domain_name,
            domain_description=registry.domain_description,
            agent_descriptions=registry.generate_descriptions(),
            additional_instructions="",
        )

    def build_schema(self, registry: "SubAgentRegistry") -> type["BaseModel"]:
        """Build the output schema from registry.

        Args:
            registry: SubAgentRegistry with sub-agent configurations

        Returns:
            Pydantic model class with valid agent keys
        """
        return create_triage_output_schema(registry.agent_keys)


CONFIG = TriageAgentConfig()


def create_triage_agent(
    sub_registry: "SubAgentRegistry",
    model_registry: Optional["ModelRegistry"] = None,
    model_name: Optional["ModelName"] = None,
) -> "ChatAgent":
    """Create the Triage agent with dynamic prompt and schema.

    Args:
        sub_registry: SubAgentRegistry with sub-agent configurations
        model_registry: ModelRegistry for cloud mode, None for env settings
        model_name: Model to use (only when model_registry provided)

    Returns:
        Configured ChatAgent instance
    """
    return create_agent(
        name=CONFIG.name,
        description=f"Routes queries to {sub_registry.domain_name} agents",
        instructions=CONFIG.build_prompt(sub_registry),
        registry=model_registry,
        model_name=model_name,
        response_format=CONFIG.build_schema(sub_registry),
    )
