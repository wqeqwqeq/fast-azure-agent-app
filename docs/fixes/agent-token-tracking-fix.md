# Agent Token Tracking Fix

## Issue Description

Orchestration agents (triage-agent, plan-agent, replan-agent, review-agent) and streaming agents (summary-agent) were not recording token usage in the `call` table, while non-orchestration agents (servicenow-agent, log_analytics-agent, service_health-agent) worked correctly.

**Observed behavior:**
```json
// triage-agent - NO token data
{"type": "agent_finished", "agent": "triage-agent", "usage": null, ...}

// servicenow-agent - HAS token data
{"type": "agent_finished", "agent": "servicenow-agent", "usage": {"input_tokens": 563, ...}, ...}

// summary-agent - NO token data, execution_time_ms: 0
{"type": "agent_finished", "agent": "summary-agent", "usage": null, "execution_time_ms": 0, ...}
```

## Root Cause Analysis

### Investigation Process

1. Added debug logging to `_extract_usage()` function to trace what `context.result` contained
2. Discovered that `context.result` types differed by agent:

| Agent | `context.result` Type | Has `usage_details`? |
|-------|----------------------|---------------------|
| triage-agent (orchestration) | `async_generator` | No |
| servicenow-agent (non-orchestration) | `AgentRunResponse` | Yes |
| summary-agent (streaming) | `async_generator` | No |

### Root Cause

The **agent_framework** returns streaming async generators for all agents internally, even when we expect a direct `AgentRunResponse`.

- **`AgentRunResponse`**: Final aggregated response with `usage_details` (input/output/total tokens)
- **`AgentRunResponseUpdate`**: Individual streaming chunks **without** `usage_details`

The original middleware code tried to extract `usage_details` directly from:
1. Streaming items (`AgentRunResponseUpdate`) - which don't have usage
2. The generator itself - which also doesn't have usage

```python
# Original problematic code
async for item in original_result:
    item_usage = _extract_usage(item)  # AgentRunResponseUpdate has no usage_details!
    if item_usage:
        captured_usage = item_usage  # Never captured because items don't have usage
```

## Solution

### Key Discovery

`AgentRunResponse` has a class method `from_agent_run_response_updates()` that converts a list of streaming updates into a final response **with usage_details**.

```python
from agent_framework import AgentRunResponse

# Convert streaming updates to final response
final_response = AgentRunResponse.from_agent_run_response_updates(collected_updates)
usage = final_response.usage_details  # Now has token counts!
```

### Implementation

Updated `app/opsagent/middleware/observability.py`:

```python
@agent_middleware
async def observability_agent_middleware(context, next):
    agent_name = context.agent.name
    model_name = _extract_model_name(context.agent)
    start_time = datetime.now(timezone.utc)

    await emit_event({"type": "agent_invoked", "agent": agent_name})
    await next(context)

    original_result = context.result
    is_orchestration = agent_name in get_settings().orchestration_agents

    if hasattr(original_result, "__anext__"):
        # Streaming result - wrap generator to collect updates
        async def wrapped_generator():
            collected_updates = []
            async for item in original_result:
                collected_updates.append(item)
                yield item

            # Calculate execution time AFTER stream completes
            execution_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)

            # KEY FIX: Convert updates to AgentRunResponse to get usage_details
            usage = None
            output = None
            if collected_updates:
                try:
                    final_response = AgentRunResponse.from_agent_run_response_updates(
                        collected_updates
                    )
                    usage = _extract_usage(final_response)
                    if is_orchestration:
                        output = final_response.text
                except Exception as e:
                    logger.warning(f"Failed to convert updates: {e}")

            await emit_event({
                "type": "agent_finished",
                "agent": agent_name,
                "model": model_name,
                "usage": usage,
                "execution_time_ms": execution_time_ms,
                **({"output": serialize_result(output)} if is_orchestration and output else {}),
            })

        context.result = wrapped_generator()
    else:
        # Non-streaming result - extract directly
        execution_time_ms = int((datetime.now(timezone.utc) - start_time).total_seconds() * 1000)
        usage = _extract_usage(original_result)
        # ... emit event
```

### Changes Summary

| Before | After |
|--------|-------|
| Tried to get usage from individual `AgentRunResponseUpdate` items | Collect all updates, convert to `AgentRunResponse`, then extract usage |
| `execution_time_ms` calculated at wrong time for streaming | Calculate after stream completes |
| Separate code paths for orchestration vs non-orchestration | Unified streaming/non-streaming handling |

## Verification

After fix, all agents now report token usage:

```json
{
  "conversation_id": "886a1f9a",
  "calls": [
    {
      "agent_name": "triage-agent",
      "input_tokens": 671,
      "output_tokens": 29,
      "total_tokens": 700,
      "execution_time_ms": 955
    },
    {
      "agent_name": "servicenow-agent",
      "input_tokens": 563,
      "output_tokens": 122,
      "total_tokens": 685,
      "execution_time_ms": 1702
    },
    {
      "agent_name": "summary-agent",
      "input_tokens": 535,
      "output_tokens": 176,
      "total_tokens": 711,
      "execution_time_ms": 1786
    }
  ],
  "summary": {
    "total_calls": 4,
    "agent_calls": 3,
    "function_calls": 1,
    "total_tokens": 2096
  }
}
```

## Files Modified

- `app/opsagent/middleware/observability.py` - Fixed token extraction logic

## Lessons Learned

1. **Don't assume return types** - The agent framework abstracts streaming internally; always check actual runtime types
2. **Framework introspection** - Use `dir()` and type checking to understand what attributes are actually available
3. **Aggregation methods** - Frameworks often provide methods to convert streaming data to final responses (like `from_agent_run_response_updates()`)
