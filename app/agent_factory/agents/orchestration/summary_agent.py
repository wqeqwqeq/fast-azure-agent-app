"""Summary Agent for generating final response.

This agent synthesizes information and generates the final output.
Prompt is built dynamically from SubAgentRegistry.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ...factory import create_agent
from ...prompts.templates import SUMMARY_TEMPLATE

if TYPE_CHECKING:
    from agent_framework import ChatAgent

    from ...model_registry import ModelName, ModelRegistry
    from ...subagent_registry import SubAgentRegistry


@dataclass(frozen=True)
class SummaryAgentConfig:
    """Configuration for Summary agent with build methods."""

    name: str = "summary-agent"
    description: str = "Generates final streaming response"

    def build_prompt(self, registry: "SubAgentRegistry") -> str:
        """Build the summary prompt from registry."""
        return SUMMARY_TEMPLATE.format(
            domain_name=registry.domain_name,
        )


CONFIG = SummaryAgentConfig()


def create_summary_agent(
    sub_registry: "SubAgentRegistry",
    model_registry: Optional["ModelRegistry"] = None,
    model_name: Optional["ModelName"] = None,
) -> "ChatAgent":
    """Create the Summary agent with dynamic prompt."""
    return create_agent(
        name=CONFIG.name,
        description=f"Generates summary for {sub_registry.domain_name}",
        instructions=CONFIG.build_prompt(sub_registry),
        registry=model_registry,
        model_name=model_name,
        # No response_format - streams plain text
    )
