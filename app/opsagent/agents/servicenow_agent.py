"""ServiceNow Agent for ITSM operations."""

from dataclasses import dataclass
from typing import Optional

from ..factory import create_agent
from ..settings import ModelConfig
from ..tools.servicenow_tools import (
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
    deployment_name: str = ""
    api_key: str = ""
    endpoint: str = ""
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


def create_servicenow_agent(model_config: Optional[ModelConfig] = None):
    """Create and return the ServiceNow agent."""
    return create_agent(
        name=CONFIG.name,
        description=CONFIG.description,
        instructions=CONFIG.instructions,
        model_config=model_config,
        tools=[list_change_requests, get_change_request, list_incidents, get_incident],
        deployment_name=CONFIG.deployment_name,
        api_key=CONFIG.api_key,
        endpoint=CONFIG.endpoint,
    )
