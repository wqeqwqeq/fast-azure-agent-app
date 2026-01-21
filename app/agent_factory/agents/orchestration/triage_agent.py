"""Triage Agent for routing user queries to specialized agents.

This agent routes queries to appropriate sub-agents.
The instructions template contains {placeholders} that should be filled by Claude
during /onboard skill execution. Claude can also modify any other text as needed.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ...factory import create_agent
from ...schemas.dynamic import create_triage_output_schema

if TYPE_CHECKING:
    from agent_framework import ChatAgent
    from pydantic import BaseModel

    from ...model_registry import ModelName, ModelRegistry
    from ...subagent_registry import SubAgentRegistry


@dataclass(frozen=True)
class TriageAgentConfig:
    """Configuration for Triage agent.

    The instructions field is a template with {placeholders}.
    When running /onboard, Claude should:
    1. Fill {placeholders} with domain-specific content
    2. Modify any other text as needed
    3. DO NOT modify the Output Format section (captured by schema)
    """

    name: str = "triage-agent"
    description: str = "Routes user queries to specialized agents"

    # Template with {placeholders} - Claude fills these during /onboard
    instructions: str = """You are a triage agent for {domain_purpose}. Your job is to analyze the user's **LATEST question** and route it to the appropriate specialized agent(s).

## IMPORTANT: Focus on the Latest Question
- **Primary focus**: The user's most recent message (the last user message in the conversation)
- **Conversation history**: Use previous messages ONLY as context to resolve references (e.g., {reference_examples})
- Do NOT re-process or re-route previous questions - only handle the current one

## Specialized Agents Available:
{agent_summaries}

## Your Task:
1. Identify what the user is asking in their LATEST message
2. If UNRELATED to any specialized agent, set should_reject=true
3. If related, create task(s) for appropriate agent(s)
4. When the latest question references something from history, resolve the reference into a clear, specific, self-contained task question

## Output Format (JSON):
{
  "should_reject": false,
  "reject_reason": "",
  "tasks": [
    {"question": "Clear, specific task question", "agent": "agent_key"}
  ]
}

## Routing Examples:
{routing_examples}

## Decision Guidelines:
{decision_guidelines}
"""

    def build_prompt(self) -> str:
        """Return the instructions (already filled by Claude during /onboard)."""
        return self.instructions

    def build_schema(self, registry: "SubAgentRegistry") -> type["BaseModel"]:
        """Build the output schema from registry."""
        return create_triage_output_schema(registry.agent_keys)


CONFIG = TriageAgentConfig()


def create_triage_agent(
    sub_registry: "SubAgentRegistry",
    model_registry: Optional["ModelRegistry"] = None,
    model_name: Optional["ModelName"] = None,
) -> "ChatAgent":
    """Create the Triage agent.

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
        instructions=CONFIG.build_prompt(),
        registry=model_registry,
        model_name=model_name,
        response_format=CONFIG.build_schema(sub_registry),
    )
