"""Clarify Agent for handling ambiguous requests.

This agent helps users refine unclear queries.
Prompt and schema are built dynamically from SubAgentRegistry.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ...factory import create_agent
from ...prompts.templates import CLARIFY_TEMPLATE
from ...schemas.dynamic import create_clarify_output_schema

if TYPE_CHECKING:
    from agent_framework import ChatAgent
    from pydantic import BaseModel

    from ...model_registry import ModelName, ModelRegistry
    from ...subagent_registry import SubAgentRegistry


@dataclass(frozen=True)
class ClarifyAgentConfig:
    """Configuration for Clarify agent with build methods."""

    name: str = "clarify-agent"
    description: str = "Helps users refine unclear requests"

    def build_prompt(self, registry: "SubAgentRegistry") -> str:
        """Build the clarify prompt from registry."""
        return CLARIFY_TEMPLATE.format(
            domain_name=registry.domain_name,
            capabilities_summary=registry.generate_capabilities_summary(),
        )

    def build_schema(self, registry: "SubAgentRegistry") -> type["BaseModel"]:
        """Build the output schema (not registry-dependent)."""
        return create_clarify_output_schema()


CONFIG = ClarifyAgentConfig()


def create_clarify_agent(
    sub_registry: "SubAgentRegistry",
    model_registry: Optional["ModelRegistry"] = None,
    model_name: Optional["ModelName"] = None,
) -> "ChatAgent":
    """Create the Clarify agent with dynamic prompt."""
    return create_agent(
        name=CONFIG.name,
        description=f"Clarifies requests for {sub_registry.domain_name}",
        instructions=CONFIG.build_prompt(sub_registry),
        registry=model_registry,
        model_name=model_name,
        response_format=CONFIG.build_schema(sub_registry),
    )
