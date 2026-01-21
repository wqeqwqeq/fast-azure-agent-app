"""Plan Agent for creating execution plans.

This agent analyzes queries and creates multi-step execution plans.
The instructions template contains {placeholders} that should be filled by Claude
during /onboard skill execution. Claude can also modify any other text as needed.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ...factory import create_agent
from ...schemas.dynamic import create_triage_plan_output_schema

if TYPE_CHECKING:
    from agent_framework import ChatAgent
    from pydantic import BaseModel

    from ...model_registry import ModelName, ModelRegistry
    from ...subagent_registry import SubAgentRegistry


@dataclass(frozen=True)
class PlanAgentConfig:
    """Configuration for Plan agent.

    The instructions field is a template with {placeholders}.
    When running /onboard, Claude should:
    1. Fill {placeholders} with domain-specific content
    2. Modify any other text as needed
    3. DO NOT modify the Output Format section (captured by schema)
    """

    name: str = "plan-agent"
    description: str = "Analyzes queries and creates execution plans"

    # Template with {placeholders} - Claude fills these during /onboard
    instructions: str = """You are a planning agent that analyzes user queries and creates execution plans for {domain_purpose}.

## Your Task

Given a user's query, decide the best course of action:
- **plan**: Create an execution plan if the query is clear and actionable
- **clarify**: Request clarification if the query is related but ambiguous
- **reject**: Reject if the query is completely outside your scope

## Available Agents and Their Tools

{agent_tools_summary}

## Planning Guidelines

When creating execution plans:
- **Same step number** = parallel execution (agents run simultaneously)
- **Different step numbers** = sequential execution (step 1 finishes before step 2 starts)
- Step N automatically receives ALL results from step N-1 as context
- You can call the same agent multiple times in different steps
- Each question should be clear and specific for the target agent

{parallel_vs_sequential_guidance}

## Output Format (JSON):

```json
{
  "action": "plan",
  "reject_reason": "",
  "clarification_reason": "",
  "plan": [
    {"step": 1, "agent": "agent_key", "question": "..."},
    {"step": 1, "agent": "agent_key2", "question": "..."},
    {"step": 2, "agent": "agent_key", "question": "..."}
  ],
  "plan_reason": "Explanation of why this plan was chosen"
}
```

## Planning Examples:

{planning_examples}

## Action Guidelines

- **plan**: Query is clear and can be answered by available agents
- **clarify**: Query is related but too vague or ambiguous
- **reject**: Query is completely unrelated to what this assistant can help with
"""

    def build_prompt(self) -> str:
        """Return the instructions (already filled by Claude during /onboard)."""
        return self.instructions

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
        instructions=CONFIG.build_prompt(),
        registry=model_registry,
        model_name=model_name,
        response_format=CONFIG.build_schema(sub_registry),
    )
