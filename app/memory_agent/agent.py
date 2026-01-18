"""Memory summarization agent."""

from dataclasses import dataclass
from typing import Optional

from app.opsagent.factory import create_agent
from app.opsagent.model_registry import ModelName, ModelRegistry

from .schemas import StructuredMemory


@dataclass(frozen=True)
class MemoryAgentConfig:
    """Configuration for the Memory agent."""

    name: str = "memory-agent"
    description: str = "Extracts structured information from conversations"
    instructions: str = """You are a conversation memory assistant. Extract key information from conversations.

## Extract These (all optional, only include if present):

- **facts**: Confirmed information (e.g., "Server upgrade scheduled Dec 15", "Budget is $50k")
- **decisions**: Conclusions reached (e.g., "Using Redis for caching", "Will deploy next week")
- **user_preferences**: User requirements expressed (e.g., "Prefers Python", "Needs daily reports")
- **open_questions**: Unresolved items needing follow-up (e.g., "Waiting for approval", "Need to confirm timeline")
- **entities**: Important identifiers with context
  - name: The identifier (e.g., "CHG0012345", "John Smith")
  - aliases: Alternative names (optional)
  - notes: Key info about this entity (optional)

## Guidelines

- Only include fields that have content (omit empty fields)
- Keep entries concise and factual
- Focus on information useful for future interactions
- For entities, capture IDs, names, systems mentioned with relevant context

## When given previous memory + new messages

- Merge new information with existing
- Update entity notes with new info
- Remove resolved items from open_questions
- Keep the most relevant and recent information
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
        response_format=StructuredMemory,
    )
