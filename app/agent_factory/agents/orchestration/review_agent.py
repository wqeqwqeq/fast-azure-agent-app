"""Review Agent for evaluating execution results.

This agent evaluates if responses are complete.
Prompt and schema are built dynamically from SubAgentRegistry.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ...factory import create_agent
from ...prompts.templates import REVIEW_TEMPLATE
from ...schemas.dynamic import create_review_output_schema

if TYPE_CHECKING:
    from agent_framework import ChatAgent
    from pydantic import BaseModel

    from ...model_registry import ModelName, ModelRegistry
    from ...subagent_registry import SubAgentRegistry


@dataclass(frozen=True)
class ReviewAgentConfig:
    """Configuration for Review agent with build methods."""

    name: str = "review-agent"
    description: str = "Reviews execution results for completeness"

    def build_prompt(self, registry: "SubAgentRegistry") -> str:
        """Build the review prompt from registry."""
        return REVIEW_TEMPLATE.format(
            agent_descriptions=registry.generate_descriptions(),
            additional_criteria="",
        )

    def build_schema(self, registry: "SubAgentRegistry") -> type["BaseModel"]:
        """Build the output schema (not registry-dependent)."""
        return create_review_output_schema()


CONFIG = ReviewAgentConfig()


def create_review_agent(
    sub_registry: "SubAgentRegistry",
    model_registry: Optional["ModelRegistry"] = None,
    model_name: Optional["ModelName"] = None,
) -> "ChatAgent":
    """Create the Review agent with dynamic prompt."""
    return create_agent(
        name=CONFIG.name,
        description=CONFIG.description,
        instructions=CONFIG.build_prompt(sub_registry),
        registry=model_registry,
        model_name=model_name,
        response_format=CONFIG.build_schema(sub_registry),
    )
