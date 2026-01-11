"""ServiceNow agent configuration."""

from dataclasses import dataclass


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


SERVICENOW_AGENT = ServiceNowAgentConfig()
