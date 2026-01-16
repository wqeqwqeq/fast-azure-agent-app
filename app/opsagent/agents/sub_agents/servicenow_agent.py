"""ServiceNow Agent for ITSM operations."""

from dataclasses import dataclass
from typing import Optional

from ...factory import create_agent
from ...model_registry import ModelRegistry
from .tools.servicenow_tools import (
    get_change_request,
    get_incident,
    list_change_requests,
    list_incidents,
)


@dataclass(frozen=True)
class ServiceNowAgentConfig:
    """Configuration for the ServiceNow agent."""

    name: str = "servicenow-agent"
    description: str = "Handles ServiceNow operations: change requests and incidents"
    instructions: str = """You are a ServiceNow ITSM assistant. You help users with:
- Change Request management (CHG tickets)
- Incident management (INC tickets)

You can LIST multiple records or GET a single record by ticket number.

When responding:
- Present data clearly with ticket numbers prominent
- Include status and priority information
- If no results, explain possible reasons

## Output Format
Always format your response in Markdown:
- Use **bold** for ticket numbers (e.g., **CHG0012345**)
- Use tables for listing multiple records
- Use bullet points for details
- Use `code` formatting for technical IDs
"""


CONFIG = ServiceNowAgentConfig()


def create_servicenow_agent(
    registry: Optional[ModelRegistry] = None,
    model_name: Optional[str] = None,
):
    """Create and return the ServiceNow agent.

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
        tools=[list_change_requests, get_change_request, list_incidents, get_incident],
    )
