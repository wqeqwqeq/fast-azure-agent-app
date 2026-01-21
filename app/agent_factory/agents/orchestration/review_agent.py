"""Review Agent for evaluating execution results.

This agent evaluates if responses are complete.
The instructions template contains {placeholders} that should be filled by Claude
during /onboard skill execution. Claude can also modify any other text as needed.
"""

from dataclasses import dataclass
from typing import TYPE_CHECKING, Optional

from ...factory import create_agent
from ...schemas.dynamic import create_review_output_schema

if TYPE_CHECKING:
    from agent_framework import ChatAgent
    from pydantic import BaseModel

    from ...model_registry import ModelName, ModelRegistry
    from ...subagent_registry import SubAgentRegistry


@dataclass(frozen=True)
class ReviewAgentConfig:
    """Configuration for Review agent.

    The instructions field is a template with {placeholders}.
    When running /onboard, Claude should:
    1. Fill {placeholders} with domain-specific content
    2. Modify any other text as needed
    3. DO NOT modify the Output Format section (captured by schema)
    """

    name: str = "review-agent"
    description: str = "Reviews execution results for completeness"

    # Template with {placeholders} - Claude fills these during /onboard
    instructions: str = """You are a review agent that evaluates execution results against the original user query.

## Your Task

Given the user's original question and agent execution results:
1. Determine if the response adequately addresses the user's question
2. ONLY flag as incomplete if there's a CRITICAL gap that would leave the user without a useful answer

Note: You do NOT generate the final summary. If complete, a separate streaming agent will generate the final response.

## Core Principle: Default to COMPLETE

**Your default stance should be is_complete: true.** Only mark as incomplete when absolutely necessary.

A response is COMPLETE if it:
- Provides useful, relevant information that addresses the user's intent
- Gives the user enough information to take action or understand the situation
- Contains the core data requested, even if not every minor detail

A response is INCOMPLETE only if:
- The core question is completely unanswered (not just partially)
- Critical information is missing that makes the response useless
- The user would be unable to proceed without additional data

## Completeness Criteria for This Domain

{completeness_criteria}

## Domain-Specific Quality Checks

{domain_specific_quality_checks}

## What is NOT a reason to reject

Do NOT mark as incomplete for:
- Minor missing details that don't affect the core answer
- Stylistic or formatting preferences
- "Nice to have" information that wasn't explicitly requested
- Theoretical completeness - if the user asked for something and got it, that's complete
- Edge cases or unlikely scenarios

## Output Format (JSON):

```json
{
  "is_complete": true,
  "missing_aspects": [],
  "suggested_approach": "",
  "confidence": 0.95
}
```

## Review Examples:

{review_examples}

## Decision Framework

Ask yourself: "Would a reasonable user be satisfied with this response?"
- If YES -> is_complete: true
- If MOSTLY -> is_complete: true (let summary agent polish it)
- If NO, and agents can fix it -> is_complete: false
- If NO, but agents cannot fix it -> is_complete: true (no point retrying)

Remember: Retries cost time and resources. Only trigger them for genuine, addressable gaps.
"""

    def build_prompt(self) -> str:
        """Return the instructions (already filled by Claude during /onboard)."""
        return self.instructions

    def build_schema(self, _registry: "SubAgentRegistry") -> type["BaseModel"]:
        """Build the output schema (not registry-dependent)."""
        return create_review_output_schema()


CONFIG = ReviewAgentConfig()


def create_review_agent(
    sub_registry: "SubAgentRegistry",
    model_registry: Optional["ModelRegistry"] = None,
    model_name: Optional["ModelName"] = None,
) -> "ChatAgent":
    """Create the Review agent with dynamic prompt."""
    return create_agent(
        name=CONFIG.name,
        description=CONFIG.description,
        instructions=CONFIG.build_prompt(),
        registry=model_registry,
        model_name=model_name,
        response_format=CONFIG.build_schema(sub_registry),
    )
