"""Replan Agent for handling review feedback.

This agent processes review feedback and decides on retry strategy.
The instructions template contains {placeholders} that should be filled by Claude
during /onboard skill execution. Claude can also modify any other text as needed.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ...factory import create_agent
from ...schemas.dynamic import create_triage_replan_output_schema

if TYPE_CHECKING:
    from agent_framework import ChatAgent
    from pydantic import BaseModel

    from ...model_registry import ModelName, ModelRegistry
    from ...subagent_registry import SubAgentRegistry


@dataclass(frozen=True)
class ReplanAgentConfig:
    """Configuration for Replan agent.

    The instructions field is a template with {placeholders}.
    When running /onboard, Claude should:
    1. Fill {placeholders} with domain-specific content
    2. Modify any other text as needed
    3. DO NOT modify the Output Format section (captured by schema)
    """

    name: str = "replan-agent"
    description: str = "Evaluates review feedback and decides on retry strategy"

    # Template with {placeholders} - Claude fills these during /onboard
    instructions: str = """You are a replan agent that evaluates review feedback and decides how to proceed.

## Your Task

You receive feedback from the review agent indicating that the current response is incomplete.
Decide which action to take:
- **retry**: Accept feedback and create a new plan to address the gaps
- **clarify**: The gap cannot be addressed without more information from the user
- **complete**: The current response is actually sufficient, proceed to summary

## Context You Receive

1. **Original User Query**: What the user originally asked
2. **Previous Execution Results**: What the agents already gathered
3. **Review Feedback**: What the reviewer thinks is missing

## Available Agents and Their Tools

{agent_tools_summary}

## Output Format (JSON):

```json
{
  "action": "retry|clarify|complete",
  "new_plan": [
    {"step": 1, "agent": "agent_key", "question": "..."}
  ],
  "clarification_reason": "",
  "completion_reason": ""
}
```

## Decision Guidelines

{when_to_retry_vs_complete}

## Retry Examples:

{retry_examples}

## Important Notes

- Be critical - don't blindly accept all feedback
- Only create plans for addressable gaps
- When completing, explain why the current answer is sufficient
- When requesting clarification, explain what information is needed from the user
"""

    def build_prompt(self) -> str:
        """Return the instructions (already filled by Claude during /onboard)."""
        return self.instructions

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
        instructions=CONFIG.build_prompt(),
        registry=model_registry,
        model_name=model_name,
        response_format=CONFIG.build_schema(sub_registry),
    )
