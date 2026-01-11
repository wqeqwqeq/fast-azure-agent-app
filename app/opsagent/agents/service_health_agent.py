"""Service Health Agent for monitoring data services."""

from dataclasses import dataclass
from typing import Optional

from ..factory import create_agent
from ..model_registry import ModelRegistry
from ..tools.service_health_tools import (
    check_azure_service_health,
    check_databricks_health,
    check_snowflake_health,
)


@dataclass(frozen=True)
class ServiceHealthAgentConfig:
    """Configuration for the Service Health agent."""

    name: str = "service-health-agent"
    description: str = "Monitors health status of Databricks, Snowflake, and Azure services"
    instructions: str = """You are a service health monitoring assistant. You check the status of:
- Databricks (workspace and clusters)
- Snowflake (warehouses)
- Azure services (ADF)

Health status is either HEALTHY or UNHEALTHY.

When responding:
- State the service name clearly
- Provide HEALTHY or UNHEALTHY status
- Include timestamp of the check
- If unhealthy, provide brief reason

## Output Format
Always format your response in Markdown:
- Use **bold** for service names
- Use 🟢 HEALTHY or 🔴 UNHEALTHY status indicators
- Use tables when reporting multiple services
- Use `code` formatting for timestamps
"""


CONFIG = ServiceHealthAgentConfig()


def create_service_health_agent(
    registry: Optional[ModelRegistry] = None,
    model_name: Optional[str] = None,
):
    """Create and return the Service Health agent.

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
        tools=[check_databricks_health, check_snowflake_health, check_azure_service_health],
    )
