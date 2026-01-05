# SSE Streaming Architecture

## Overview

This document describes the unified SSE streaming architecture for the message API. The endpoint streams middleware events (function calls, agent lifecycle) in real-time and returns the final assistant response as part of the same stream.

## Why Unified Endpoint

| Aspect | Separate (old) | Merged (new) |
|--------|---------------|--------------|
| HTTP connections | 2 (GET SSE + POST) | 1 |
| Timing coordination | Required (100ms hack) | None |
| Event-message binding | By conversation_id | Implicit (same request) |
| Race condition | Possible | Impossible |
| Error handling | Partial | Atomic |
| User isolation | Shared dictionary | Per-request queue |

## Async Behavior

**AzureOpenAIChatClient is fully async and does NOT block:**
- Uses `AsyncAzureOpenAI` → `httpx.AsyncClient` (non-blocking HTTP)
- All methods are `async def` - true coroutines that yield to event loop
- `workflow.run_stream()` and `agent.run()` are properly async

**`asyncio.create_task` does NOT consume threadpool:**
- It's just another coroutine in the event loop
- FastAPI can handle thousands of concurrent async requests
- The task + queue pattern multiplexes two event sources:
  - Workflow events from `run_stream()`
  - Middleware events (function_start/end)

---

## Required Events (Emitted)

Only these events are emitted in the SSE stream:

| Event Type | Data Type | Source | Description |
|------------|-----------|--------|-------------|
| `message` | `user` | Before workflow | Confirms user message saved |
| `thinking` | `function_start` | Middleware | Tool call starting with arguments |
| `thinking` | `function_end` | Middleware | Tool call finished with result |
| `thinking` | `agent_invoked` | Middleware | Agent started |
| `thinking` | `agent_finished` | Middleware | Agent completed |
| `message` | `assistant` | After workflow | Final response from `WorkflowOutputEvent.data` |
| `done` | - | End | Stream complete signal |

## Optional Events (Not Emitted by Default)

These workflow events are available from `run_stream()` but NOT emitted:

| Event | Description | When to Enable |
|-------|-------------|----------------|
| `WorkflowStatusEvent` | State transitions (IN_PROGRESS, IDLE) | Debug/monitoring |
| `ExecutorInvokedEvent` | Executor started | Detailed workflow tracing |
| `ExecutorCompletedEvent` | Executor finished | Detailed workflow tracing |
| `ExecutorFailedEvent` | Executor error | Error handling |
| `WorkflowFailedEvent` | Workflow-level error | Error handling |

To enable, add to `messages.py` in the `run_workflow()` function:
```python
if isinstance(event, WorkflowStatusEvent):
    await event_queue.put(format_sse_event("thinking", {
        "type": "workflow_status",
        "state": event.state.value,
        "seq": seq,
    }))
```

---

## Event Protocol

```
POST /conversations/{id}/messages
Content-Type: application/json
{"message": "check ServiceNow incidents"}

Response (SSE stream):
event: message
data: {"type": "user", "content": "check ServiceNow incidents", "seq": 5, "time": "..."}

event: thinking
data: {"type": "agent_invoked", "agent": "triage_agent", "seq": 5}

event: thinking
data: {"type": "function_start", "function": "list_incidents", "arguments": {...}, "seq": 5}

event: thinking
data: {"type": "function_end", "function": "list_incidents", "result": [...], "seq": 5}

event: thinking
data: {"type": "agent_finished", "agent": "triage_agent", "seq": 5}

event: message
data: {"type": "assistant", "content": "Here are the recent incidents...", "seq": 6, "time": "...", "title": "..."}

event: done
data: {}
```

---

## Frontend Pattern

```javascript
async function sendMessage(conversationId, message) {
    const response = await fetch(`/api/conversations/${conversationId}/messages`, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({message})
    });

    const reader = response.body.getReader();
    const decoder = new TextDecoder();

    while (true) {
        const {done, value} = await reader.read();
        if (done) break;

        const text = decoder.decode(value);
        for (const line of text.split('\n')) {
            if (line.startsWith('data:')) {
                const event = JSON.parse(line.slice(5));

                if (event.type === 'function_start') {
                    appendThinkingEvent(`Calling ${event.function}...`);
                } else if (event.type === 'assistant') {
                    replaceThinkingWithResponse(event.content);
                }
            }
        }
    }
}
```

---

## Files Changed

| File | Action |
|------|--------|
| `app/utils/event_stream.py` | **DELETED** |
| `app/opsagent/middleware/observability.py` | Queue-based emission, seq tracking |
| `app/routes/messages.py` | Merged endpoint, `run_stream()`, SSE response |
| `app/opsagent/middleware/__init__.py` | Updated exports |
| `app/utils/__init__.py` | Removed old exports |

---

## Event Flow

```
Frontend                                    Backend
   │
   ├─ POST /messages (body: {message}) ───► Validate, save user message
   │                                        Create async queue
   │                                        set_current_queue(queue)
   │                                        set_current_message_seq(seq)
   │
   │  ◄─ SSE: message (user) ─────────────┤
   │
   │                                        async for event in workflow.run_stream():
   │  ◄─ SSE: thinking (agent_invoked) ───┤   (middleware emits here)
   │  ◄─ SSE: thinking (function_start) ──┤
   │  ◄─ SSE: thinking (function_end) ────┤
   │  ◄─ SSE: thinking (agent_finished) ──┤
   │                                        WorkflowOutputEvent → final_output
   │
   │  ◄─ SSE: message (assistant) ────────┤   save to DB
   │  ◄─ SSE: done ───────────────────────┤
   ▼
```

**No timing coordination, no race conditions, atomic operation.**
