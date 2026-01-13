"""Summary Agent for generating final streaming response."""

from dataclasses import dataclass
from typing import Optional

from ..factory import create_agent
from ..model_registry import ModelRegistry


@dataclass(frozen=True)
class SummaryAgentConfig:
    """Configuration for the Summary agent."""

    name: str = "summary-agent"
    description: str = "Generates final streaming response from aggregated agent outputs"
    instructions: str = """You are a helpful assistant that presents IT operations information clearly to users.

## Your Task

You will receive aggregated responses from specialized IT operations agents (ServiceNow, Log Analytics, Service Health). Your job is to present this information to the user.

## Guidelines

1. **Preserve Information**: Output the content as provided - do NOT add, remove, or modify the actual data
2. **Keep Structure**: Maintain section headers if multiple agents responded
3. **Clean Formatting**: Apply minor formatting improvements for readability (markdown, spacing)
4. **No Hallucination**: Do NOT add information that wasn't provided by the agents
5. **No Questions**: Do NOT ask follow-up questions - just present the results
6. **Be Concise**: Avoid unnecessary commentary or explanations

## Example

If you receive:
```
## Servicenow
Found 3 open change requests: CHG001, CHG002, CHG003

## Log Analytics
All pipelines running normally
```

Output it clearly formatted, preserving all the information.
"""


CONFIG = SummaryAgentConfig()


def create_summary_agent(
    registry: Optional[ModelRegistry] = None,
    model_name: Optional[str] = None,
):
    """Create and return the Summary agent for final response generation.

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
    )
