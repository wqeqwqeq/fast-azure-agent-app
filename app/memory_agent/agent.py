"""Memory summarization agent."""

from dataclasses import dataclass
from typing import Optional

from app.opsagent.factory import create_agent
from app.opsagent.model_registry import ModelName, ModelRegistry

from .schemas import MemorySummaryOutput


@dataclass(frozen=True)
class MemoryAgentConfig:
    """Configuration for the Memory agent."""

    name: str = "memory-agent"
    description: str = "Summarizes conversation history for context compression"
    instructions: str = """You are a conversation summarization assistant. Your task is to create a concise summary of a conversation segment.

## Your Task
Given a segment of conversation between a user and an assistant, create a brief summary that captures:
1. The main topics discussed
2. Key decisions or conclusions reached
3. Important context that would be relevant for future interactions

## Guidelines
- Be concise but comprehensive (aim for 2-4 sentences)
- Preserve important details like names, IDs, dates, or specific values mentioned
- Focus on information that would help understand future questions in context
- Use neutral, factual language
- Do NOT include phrases like "In this conversation..." or "The user asked..."

## Output Format
Provide your summary as a JSON object with a single "summary" field.

## Example
Input conversation:
User: "Check the status of change request CHG0012345"
Assistant: "CHG0012345 is approved and scheduled for deployment on Dec 15th. It's for upgrading the database server."
User: "What about the associated incidents?"
Assistant: "There are 2 incidents linked: INC001 (resolved) and INC002 (in progress)."

Output:
{
  "summary": "Discussed change request CHG0012345 (approved, scheduled Dec 15th for database server upgrade). Two linked incidents: INC001 (resolved) and INC002 (in progress)."
}
"""


CONFIG = MemoryAgentConfig()


def create_memory_agent(
    registry: Optional[ModelRegistry] = None,
    model_name: Optional[ModelName] = None,
):
    """Create and return the Memory agent.

    Args:
        registry: ModelRegistry for cloud mode, None for env settings
        model_name: Model to use (only when registry provided)
    """
    return create_agent(
        name=CONFIG.name,
        description=CONFIG.description,
        instructions=CONFIG.instructions,
        registry=registry,
        model_name=model_name,
        response_format=MemorySummaryOutput,
    )
