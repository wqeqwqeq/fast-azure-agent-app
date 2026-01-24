"""Clarify Agent for handling ambiguous requests.

This agent helps users refine unclear queries.
The instructions template contains {placeholders} that should be filled by Claude
during /onboard skill execution. Claude can also modify any other text as needed.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ...factory import create_agent
from ...schemas.dynamic import create_clarify_output_schema

if TYPE_CHECKING:
    from agent_framework import ChatAgent
    from pydantic import BaseModel

    from ...model_registry import ModelName, ModelRegistry
    from ...subagent_registry import SubAgentRegistry


@dataclass(frozen=True)
class ClarifyAgentConfig:
    """Configuration for Clarify agent.

    The instructions field is a template with {placeholders}.
    When running /onboard, Claude should:
    1. Fill {placeholders} with domain-specific content
    2. Modify any other text as needed
    3. DO NOT modify the Output Format section (captured by schema)
    """

    name: str = "clarify-agent"
    description: str = "Helps users refine unclear requests"

    # Template with {placeholders} - Claude fills these during /onboard
    instructions: str = """You are a clarification agent that helps users refine their requests when queries are ambiguous or unclear.

## Your Task

When a query is related to {domain_purpose} but unclear:
1. Acknowledge what you understood from the query
2. Politely ask for specific clarification
3. Offer possible interpretations to guide the user

## Output Format (JSON):

```json
{
  "clarification_request": "A polite, helpful request for clarification",
  "possible_interpretations": [
    "First possible meaning of the query",
    "Second possible meaning of the query"
  ]
}
```

## Tone and Style

- Be friendly and helpful, never dismissive
- Show that you understood part of their request
- Guide users toward valid queries they can make
- Keep clarification requests concise but informative

## Available Capabilities (for context)

{capabilities_summary}

## Clarification Examples

{clarification_examples}

## Guidelines

- Always offer 2-4 possible interpretations
- Make interpretations actionable (things the system can actually do)
- Don't make assumptions - ask for clarification
- Be encouraging - help users succeed in getting what they need
"""

    def build_prompt(self) -> str:
        """Return the instructions (already filled by Claude during /onboard)."""
        return self.instructions

    def build_schema(self, _registry: "SubAgentRegistry") -> type["BaseModel"]:
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
        instructions=CONFIG.build_prompt(),
        registry=model_registry,
        model_name=model_name,
        response_format=CONFIG.build_schema(sub_registry),
    )
