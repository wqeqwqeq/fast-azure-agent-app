"""Log Analytics Agent for Azure Data Factory pipeline monitoring."""

from dataclasses import dataclass
from typing import Optional

from ..factory import create_agent
from ..settings import ModelConfig
from ..tools.log_analytics_tools import (
    get_pipeline_run_details,
    list_failed_pipelines,
    query_pipeline_status,
)


@dataclass(frozen=True)
class LogAnalyticsAgentConfig:
    """Configuration for the Log Analytics agent."""

    name: str = "log-analytics-agent"
    description: str = "Queries Azure Data Factory pipeline execution logs"
    deployment_name: str = ""
    api_key: str = ""
    endpoint: str = ""
    instructions: str = """You are an Azure Log Analytics assistant for ADF pipeline monitoring.

You can:
- Query pipeline execution status (start time, end time, duration, status)
- Get details for specific pipeline runs
- List failed pipelines within a time range

When responding:
- Include timestamps in UTC format
- Clearly indicate status: Succeeded, Failed, In Progress, Cancelled
- For failures, include error messages when available

## Output Format
Always format your response in Markdown:
- Use **bold** for pipeline names
- Use tables for listing multiple pipeline runs
- Use `code` formatting for run IDs and timestamps
- Use ✅ for Succeeded, ❌ for Failed, ⏳ for In Progress
"""


CONFIG = LogAnalyticsAgentConfig()


def create_log_analytics_agent(model_config: Optional[ModelConfig] = None):
    """Create and return the Log Analytics agent."""
    return create_agent(
        name=CONFIG.name,
        description=CONFIG.description,
        instructions=CONFIG.instructions,
        model_config=model_config,
        tools=[query_pipeline_status, get_pipeline_run_details, list_failed_pipelines],
        deployment_name=CONFIG.deployment_name,
        api_key=CONFIG.api_key,
        endpoint=CONFIG.endpoint,
    )
