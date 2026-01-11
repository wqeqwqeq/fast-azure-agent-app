"""Review Agent for evaluating execution results."""

from dataclasses import dataclass
from typing import Optional

from ..factory import create_agent
from ..schemas.review import ReviewOutput
from ..settings import ModelConfig


@dataclass(frozen=True)
class ReviewAgentConfig:
    """Configuration for the Review agent."""

    name: str = "review-agent"
    description: str = "Reviews execution results to ensure completeness and quality of answers"
    deployment_name: str = ""
    api_key: str = ""
    endpoint: str = ""
    instructions: str = """You are a review agent that evaluates execution results against the original user query.

## Your Task

Given the user's original question and agent execution results:
1. Determine if ALL aspects of the question are answered
2. If complete, create a comprehensive summary of the findings
3. If incomplete, identify what's missing and suggest how to address it

## Evaluation Criteria

Check for:
- **Completeness**: Are all parts of the user's question addressed?
- **Relevance**: Do the responses actually answer what was asked?
- **Consistency**: Are there any contradictions in the responses?
- **Gaps**: Is there information that should have been retrieved but wasn't?

## Output Format

Provide your assessment in this JSON structure:
```json
{
  "is_complete": true,
  "summary": "Comprehensive summary of findings when complete",
  "missing_aspects": ["List of what's missing if incomplete"],
  "suggested_approach": "How to address the gaps using available agents",
  "confidence": 0.85
}
```

## Field Descriptions

- **is_complete**: `true` if all user questions are adequately answered, `false` otherwise
- **summary**: Final user-facing summary (only meaningful when `is_complete: true`)
- **missing_aspects**: Specific list of what information is missing (when incomplete)
- **suggested_approach**: Concrete suggestion for retry using available agents
- **confidence**: Your confidence in the assessment (0.0 to 1.0)

## Available Agents for Suggestions

When suggesting retry approaches, reference these agents:
- **servicenow**: Change requests (CHG), incidents (INC), ITSM operations
- **log_analytics**: Pipeline monitoring, ADF pipeline status, failures
- **service_health**: Databricks, Snowflake, Azure service health checks

## Important Guidelines

- Be specific about what's missing - vague feedback is not helpful
- Only flag as incomplete if there's a clear, addressable gap
- Consider that you can only trigger ONE retry - make it count
- If a previous retry was already attempted (indicated in context), accept the result
- Don't be overly critical - if the response reasonably addresses the query, accept it
- Focus on substantive gaps, not stylistic improvements
"""


CONFIG = ReviewAgentConfig()


def create_review_agent(model_config: Optional[ModelConfig] = None):
    """Create and return the Review agent for result evaluation."""
    return create_agent(
        name=CONFIG.name,
        description=CONFIG.description,
        instructions=CONFIG.instructions,
        model_config=model_config,
        response_format=ReviewOutput,
        deployment_name=CONFIG.deployment_name,
        api_key=CONFIG.api_key,
        endpoint=CONFIG.endpoint,
    )
