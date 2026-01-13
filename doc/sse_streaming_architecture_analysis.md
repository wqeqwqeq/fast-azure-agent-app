# SSE Streaming Architecture Analysis

This document provides a detailed analysis of the SSE streaming implementation, explaining how middleware events, ContextVar, and frontend handlers work together.

---

## 1. Middleware Events Flow

**Question:** Where do the middleware's function call and agent call streams go?

**Answer:** Through ContextVar to the request-level event_queue.

```
┌─────────────────────────────────────────────────────────────────────┐
│  messages.py (request handler)                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  event_queue = asyncio.Queue()                               │    │
│  │  set_current_queue(event_queue)  ← Store in ContextVar       │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼ (ContextVar propagation)
┌─────────────────────────────────────────────────────────────────────┐
│  observability.py (middleware)                                       │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  await emit_event({                                          │    │
│  │      "type": "function_start",                               │    │
│  │      "function": func_name,                                  │    │
│  │      ...                                                     │    │
│  │  })                                                          │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────────┐
│  events.py (emit_event function)                                     │
│  ┌─────────────────────────────────────────────────────────────┐    │
│  │  queue = get_current_queue()  ← Get from ContextVar          │    │
│  │  await queue.put(sse_event)   ← Put into queue               │    │
│  └─────────────────────────────────────────────────────────────┘    │
└─────────────────────────────────────────────────────────────────────┘
```

**Key code paths:**
- `observability.py:26-35` - middleware calls `emit_event()` to send agent/function events
- `events.py:62-77` - `emit_event()` gets queue from ContextVar and puts event
- `messages.py:126-127` - request handler sets queue to ContextVar

---

## 2. ContextVar and Queue Sharing

**Question:** Is the event_queue in messages.py the same as the one used by middleware?

**Answer:** Yes, they are the exact same queue!

### How ContextVar Works

```python
# events.py
_current_queue: ContextVar[Optional[asyncio.Queue]] = ContextVar("current_queue", default=None)
```

ContextVar is Python's **async-safe context variable**:
- Each async task has its own context copy
- Similar to thread-local, but designed for async/await
- When you set a value in a coroutine, that coroutine and its callees can see it

### Flow Diagram

```
Request Handler (messages.py)
│
├── event_queue = asyncio.Queue()      # Create queue
├── set_current_queue(event_queue)     # Store in ContextVar
│
├── asyncio.create_task(run_workflow())
│   │
│   └── workflow.run_stream()
│       │
│       └── agent.run()
│           │
│           └── observability_middleware
│               │
│               └── emit_event()
│                   │
│                   └── get_current_queue()  # Gets the SAME queue!
│                       └── queue.put(event) # Writes to the SAME queue!
│
└── while True:
    event = await event_queue.get()    # Reads from the SAME queue
    yield event                        # Sends to frontend
```

**Why this design?**
- Middleware is called inside the agent framework, can't pass parameters directly
- ContextVar allows middleware to "remotely" access the request-level queue
- Each request has its own queue, no cross-talk (user isolation)

---

## 3. Streaming Executor Detection

**Question:** How do we determine which executors should stream their output to the frontend?

### Problem: Hardcoded Executor IDs (Old Approach)

```python
# messages.py - OLD approach (hardcoded)
async for event in workflow.run_stream(input_data):
    if isinstance(event, AgentRunUpdateEvent):
        if event.executor_id == "summary_agent":  # Hardcoded!
            await event_queue.put(format_sse_event("stream", {...}))
    elif isinstance(event, WorkflowOutputEvent):
        final_output = event.data.text
```

**Problems with hardcoding:**
1. `executor_id == "summary_agent"` couples code to specific workflow
2. If workflow changes, or multiple agents need streaming, code needs modification
3. `WorkflowOutputEvent` part is **necessary** (for saving final result to database)

### Official Pattern (More Flexible)

```python
last_executor_id = None
async for event in workflow.run_stream("..."):
    if isinstance(event, AgentRunUpdateEvent):
        if event.executor_id != last_executor_id:
            print(f"\n{event.executor_id}:", end=" ")
            last_executor_id = event.executor_id
        print(event.data.text, end="", flush=True)
```

**But your scenario is more complex:**
- triage_agent outputs JSON (routing info), shouldn't stream to user
- Only summary_agent output is natural language

### Solution: Auto-detect from `output_response=True`

**Discovery:** The `Workflow` object exposes all executors via `workflow.executors` dictionary. We can automatically detect which executors should stream by checking their `output_response` attribute.

```python
# Verify which executors have output_response=True
for executor_id, executor in workflow.executors.items():
    print(f'{executor_id}: output_response={getattr(executor, "output_response", False)}')

# Output:
# store_query: output_response=False
# triage_agent: output_response=False
# parse_triage_output: output_response=False
# ...
# summary_agent: output_response=True  ← Only this one!
```

**Implementation (messages.py):**

```python
# Create workflow
workflow = create_triage_workflow(registry, workflow_model, agent_model_mapping)

# Auto-detect streaming executors from workflow (those with output_response=True)
streaming_executor_ids = {
    executor_id
    for executor_id, executor in workflow.executors.items()
    if getattr(executor, 'output_response', False)
}

# Use in event loop
async for event in workflow.run_stream(input_data):
    if isinstance(event, AgentRunUpdateEvent):
        # Stream text updates only from executors with output_response=True
        if event.executor_id in streaming_executor_ids:
            await event_queue.put(format_sse_event("stream", {...}))
```

**Benefits:**
1. **Zero configuration** - No hardcoded executor IDs, no config files
2. **Self-consistent** - Reuses existing `output_response=True` marker
3. **Auto-sync** - Workflow changes automatically reflected in streaming behavior
4. **Multi-executor support** - If multiple executors have `output_response=True`, all will stream

**WorkflowOutputEvent part is NOT redundant**, it's used for:
1. Getting final complete text to save to database
2. Fallback when streaming fails

---

## 4. Executor Streaming Capability

**Question:** Can AggregateResponses stream? Or only agents can stream?

**Answer:** No, it cannot stream directly. Only `AgentExecutor`-wrapped `ChatAgent` supports streaming.

### Why Only Agents Can Stream?

```
┌─────────────────────────────────────────────────────────────────┐
│  AgentExecutor                                                   │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  ChatAgent                                                 │  │
│  │  ┌─────────────────────────────────────────────────────┐  │  │
│  │  │  OpenAI/Azure API                                    │  │  │
│  │  │  stream=True → Returns token by token                │  │  │
│  │  └─────────────────────────────────────────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
│                                                                  │
│  output_response=True → Framework exposes agent's stream as     │
│                         AgentRunUpdateEvent                      │
└─────────────────────────────────────────────────────────────────┘
```

```
┌─────────────────────────────────────────────────────────────────┐
│  Regular Executor (e.g., AggregateResponses)                     │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Pure Python code                                          │  │
│  │  No LLM call → No token stream                             │  │
│  │  ctx.send_message() → Sends complete data at once          │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### AggregateResponses Role

```python
# triage_workflow.py:178-193
class AggregateResponses(Executor):
    async def aggregate(self, results: list[AgentResponse], ctx):
        sections = []
        for r in results:
            if r.text:
                sections.append(f"## {agent_name}\n{r.text}")

        consolidated = "\n\n---\n\n".join(sections)
        await ctx.send_message(consolidated)  # Sends all at once to summary_agent
```

**Flow:**
```
servicenow_executor ──┐
log_analytics_executor─┼─► AggregateResponses ──► summary_agent (streams!)
service_health_executor┘      (no stream)         (streams final response)
```

---

## 5. Frontend SSE Handling

### `replaceThinkingWithResponse()` Purpose

This is the **key UI state transition function** — transforms the "thinking" temporary UI into the final response.

### UI State Transitions

```
User sends message
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│  showThinkingIndicator()                                         │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  <div class="thinking-message">                            │  │
│  │      <div class="message-role">Assistant</div>             │  │
│  │      <div class="thinking-indicator">                      │  │
│  │          <span>Thinking</span>                             │  │
│  │          <span class="thinking-dots">...</span>            │  │
│  │          ← thinking events appended here                   │  │
│  │      </div>                                                │  │
│  │  </div>                                                    │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ SSE events arrive
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  appendThinkingEvent() — Append each event                       │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Agent: triage_agent                                       │  │
│  │  Calling list_incidents...                                 │  │
│  │  list_incidents finished                                   │  │
│  │  Agent triage_agent finished                               │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ stream events (summary_agent token output)
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  appendStreamingText() — Append text token by token              │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  <div class="streaming-content">                           │  │
│  │      Here are the recent...  ← Real-time update, Markdown  │  │
│  │  </div>                                                    │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ message (assistant) — Final completion
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  replaceThinkingWithResponse() — Final replacement               │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  <div class="message assistant">  ← Remove thinking-message│  │
│  │      <div class="message-role">Assistant</div>             │  │
│  │      <div class="thinking-collapsed">                      │  │
│  │          Thinking finished  ← Clickable to expand flyout   │  │
│  │      </div>                                                │  │
│  │      <div class="message-content">                         │  │
│  │          Here are the recent incidents...  ← Full content  │  │
│  │      </div>                                                │  │
│  │      [thumbs up] [thumbs down]  ← Evaluation buttons       │  │
│  │  </div>                                                    │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### SSE Parsing (utils.js)

```javascript
async function streamSSE(response, callbacks) {
    const reader = response.body.getReader();  // ReadableStream
    const decoder = new TextDecoder();
    let buffer = '';

    while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop();  // Keep incomplete line

        let eventType = 'message';
        for (const line of lines) {
            if (line.startsWith('event:')) {
                eventType = line.slice(6).trim();  // Parse event type
            } else if (line.startsWith('data:')) {
                const data = JSON.parse(line.slice(5).trim());
                callbacks[eventType](data);  // Call corresponding callback
            }
        }
    }
}
```

### Event Dispatch (handlers.js)

```javascript
await streamSSE(response, {
    // 1. message event — user message confirmation & final assistant response
    message: (data) => {
        if (data.type === 'assistant') {
            replaceThinkingWithResponse(data.content, data.seq);
            if (data.title) {
                updateConversationTitle(data.title);
            }
        }
    },

    // 2. thinking event — agent/function status
    thinking: (data) => {
        appendThinkingEvent(data);
    },

    // 3. stream event — summary_agent token output
    stream: (data) => {
        if (data.text) {
            appendStreamingText(data.text);
        }
    },

    // 4. done event — stream complete
    done: () => {
        // Stream complete
    }
});
```

### Function Responsibilities

| Function | Trigger | Responsibility |
|----------|---------|----------------|
| `showThinkingIndicator()` | Before sending message | Display "Thinking..." placeholder |
| `appendThinkingEvent()` | `event: thinking` | Append agent/function events to indicator |
| `appendStreamingText()` | `event: stream` | Append LLM output token by token, render Markdown |
| `replaceThinkingWithResponse()` | `event: message (assistant)` | Final replacement: remove thinking style, add eval buttons |

### `replaceThinkingWithResponse()` Details

Handles two scenarios:

**Scenario A: Has streaming (normal flow)**
```javascript
if (hasStreamedContent) {
    // Use already streamed content (not data.content)
    const streamedText = streamingContent.getAttribute('data-raw-text');
    // ... render with streamedText
}
```

**Scenario B: No streaming (fallback)**
```javascript
else {
    // No stream events (error or old version)
    // Use final data.content directly
    // ... render with content
}
```

---

## 6. Complete Sequence Diagram

```
Frontend                              Backend
   │
   ├─ POST /messages ─────────────────►│
   │                                    │ save user message
   │  ◄── event: message (user) ───────│
   │                                    │
   │                                    │ set_current_queue(queue)
   │                                    │ workflow.run_stream()
   │                                    │
   │  ◄── event: thinking ─────────────│ middleware: agent_invoked
   │      appendThinkingEvent()         │
   │                                    │
   │  ◄── event: thinking ─────────────│ middleware: function_start
   │      appendThinkingEvent()         │
   │                                    │
   │  ◄── event: thinking ─────────────│ middleware: function_end
   │      appendThinkingEvent()         │
   │                                    │
   │  ◄── event: thinking ─────────────│ middleware: agent_finished
   │      appendThinkingEvent()         │
   │                                    │
   │  ◄── event: stream ───────────────│ AgentRunUpdateEvent (summary)
   │      appendStreamingText("Here")   │
   │  ◄── event: stream ───────────────│
   │      appendStreamingText(" are")   │
   │  ◄── event: stream ───────────────│
   │      appendStreamingText(" the")   │
   │         ...                        │
   │                                    │
   │                                    │ WorkflowOutputEvent
   │                                    │ save assistant message
   │  ◄── event: message (assistant) ──│
   │      replaceThinkingWithResponse() │
   │                                    │
   │  ◄── event: done ─────────────────│
   ▼
```

---

## 7. Architecture Summary

```
┌────────────────────────────────────────────────────────────────────────┐
│  Frontend (fetch + ReadableStream)                                      │
└────────────────────────────────────────────────────────────────────────┘
                              ▲
                              │ SSE events
                              │
┌────────────────────────────────────────────────────────────────────────┐
│  messages.py                                                            │
│  ┌──────────────────────────────────────────────────────────────────┐  │
│  │  async def event_generator():                                     │  │
│  │      event_queue = asyncio.Queue()                                │  │
│  │      set_current_queue(event_queue)  ← ContextVar                 │  │
│  │                                                                   │  │
│  │      asyncio.create_task(run_workflow())                          │  │
│  │                                                                   │  │
│  │      # Two event sources merge into the same queue:               │  │
│  │      # 1. Middleware events (via ContextVar)                      │  │
│  │      # 2. AgentRunUpdateEvent (handled directly here)             │  │
│  │                                                                   │  │
│  │      while True:                                                  │  │
│  │          event = await event_queue.get()                          │  │
│  │          yield event                                              │  │
│  └──────────────────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────────────────┘
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
┌────────────────────┐              ┌────────────────────────────────────┐
│  Middleware        │              │  workflow.run_stream()              │
│  (observability.py)│              │  ┌────────────────────────────────┐│
│                    │              │  │ AgentRunUpdateEvent            ││
│  emit_event() ─────┼──► queue     │  │ (summary_agent token stream)   ││
│  - agent_invoked   │              │  │                                ││
│  - function_start  │              │  │ → await event_queue.put()      ││
│  - function_end    │              │  └────────────────────────────────┘│
│  - agent_finished  │              │  ┌────────────────────────────────┐│
└────────────────────┘              │  │ WorkflowOutputEvent            ││
                                    │  │ (final complete text)          ││
                                    │  │                                ││
                                    │  │ → final_output = event.data    ││
                                    │  └────────────────────────────────┘│
                                    └────────────────────────────────────┘
```

---

## Key Takeaways

1. **Middleware and messages.py use the SAME queue**, passed via ContextVar
2. **WorkflowOutputEvent handling is NOT redundant**, used for saving final result
3. **Only `AgentExecutor`-wrapped `ChatAgent` can truly stream**
4. **Official pattern is more generic**, but your scenario needs filtering (only summary_agent streams)
5. **`replaceThinkingWithResponse()` is the UI state transition** — transforms temporary UI into final message card
