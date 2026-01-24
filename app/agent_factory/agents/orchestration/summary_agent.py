"""Summary Agent for generating final response.

This agent synthesizes information and generates the final output.
The instructions template contains {placeholders} that should be filled by Claude
during /onboard skill execution. Claude can also modify any other text as needed.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ...factory import create_agent

if TYPE_CHECKING:
    from agent_framework import ChatAgent

    from ...model_registry import ModelName, ModelRegistry
    from ...subagent_registry import SubAgentRegistry


@dataclass(frozen=True)
class SummaryAgentConfig:
    """Configuration for Summary agent.

    The instructions field is a template with {placeholders}.
    When running /onboard, Claude should:
    1. Fill {placeholders} with domain-specific content
    2. Modify any other text as needed
    """

    name: str = "summary-agent"
    description: str = "Generates final streaming response"

    # Template with {placeholders} - Claude fills these during /onboard
    instructions: str = """You are a senior {domain_purpose} analyst who synthesizes information and provides actionable insights.

## Your Task

You receive data from specialized agents. Your job is to:
1. **Answer the user's question directly** with a high-level summary
2. **Include the detailed data** - preserve tables, lists, and specific information from agents
3. **Highlight key findings** and any issues that need attention

## Response Structure

1. **Opening summary** (1-2 sentences) - Direct answer to the question
2. **Detailed data** - Include tables and specifics from the agents
3. **Insights/Actions** (if relevant) - What needs attention or recommended next steps

## Formatting Guidelines

{formatting_guidelines}

## Response Examples

{response_examples}

## What NOT to do

- Don't start with "Based on the agent results..."
- Don't convert useful tables into plain text lists
- Don't omit important details from the original data
- Don't ask follow-up questions
"""

    def build_prompt(self) -> str:
        """Return the instructions (already filled by Claude during /onboard)."""
        return self.instructions


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
        instructions=CONFIG.build_prompt(),
        registry=model_registry,
        model_name=model_name,
        # No response_format - streams plain text
    )
