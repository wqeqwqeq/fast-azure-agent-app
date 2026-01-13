# Workflow 流式文本输出实现

## 问题描述

在 `messages.py` 中，workflow 的 chat response 不是以 stream 的形式返回，而是一次性返回所有 content。

## 问题分析

### 根本原因

1. **`FilteredAgentExecutor` 没有流式支持**：在 `triage_workflow.py` 中，`FilteredAgentExecutor` 直接调用 `self._agent.run()`，绕过了框架的自动流式检测机制。

2. **`messages.py` 没有监听 `AgentRunUpdateEvent`**：只捕获 `WorkflowOutputEvent` 作为最终输出，忽略了流式文本事件。

### Agent Framework 的流式机制

Agent Framework 的 `AgentExecutor` 实现（`_agent_executor.py`）：

```python
async def _run_agent_and_emit(self, ctx: WorkflowContext) -> None:
    if ctx.is_streaming():
        # 流式模式：调用 _run_agent_streaming
        response = await self._run_agent_streaming(ctx)
    else:
        # 非流式模式
        response = await self._run_agent(ctx)

async def _run_agent_streaming(self, ctx: WorkflowContext) -> AgentRunResponse:
    async for update in self._agent.run_stream(...):
        await ctx.add_event(AgentRunUpdateEvent(self.id, update))  # 发出流式事件
```

## 解决方案

### 方案选择

讨论了三种方案：

1. **修改所有中间 agent 支持流式** - 改动大，不必要
2. **在 aggregator 后添加 summary agent** - 选择此方案
3. **模拟分块发送** - 不是真正的流式

### 最终方案：Summary Agent

在 aggregator 后添加一个 **summary agent**，使用框架内置的 `AgentExecutor` 包装（自动支持流式），让最终输出流式返回。

**优点**：
- 中间 agent 不需要改动
- 利用框架内置的流式支持
- 最小化代码改动

**缺点**：
- 增加一次 LLM 调用（可以用 gpt-4.1-mini 减少成本）

## 实现详情

### 1. 新建 `summary_agent.py`

创建符合现有 agent 风格的 summary agent：

```python
@dataclass(frozen=True)
class SummaryAgentConfig:
    name: str = "summary-agent"
    description: str = "Generates final streaming response from aggregated agent outputs"
    instructions: str = """..."""

def create_summary_agent(registry=None, model_name=None):
    return create_agent(...)
```

### 2. 修改 `triage_workflow.py`

- 添加 `create_summary_agent` 导入
- 修改 `AggregateResponses` 的 `ctx.yield_output()` 改为 `ctx.send_message()`
- 添加 `summary_executor = AgentExecutor(summary, id="summary_agent", output_response=True)`
- 添加 `aggregator -> summary_executor` 边

### 3. 修改 `messages.py`

监听 `AgentRunUpdateEvent` 并转发为 SSE `stream` 事件（只转发 summary_agent 的事件）：

```python
from agent_framework._workflows._events import AgentRunUpdateEvent, WorkflowOutputEvent

async for event in workflow.run_stream(input_data):
    if isinstance(event, AgentRunUpdateEvent):
        # 只处理 summary_agent 的流式事件（忽略 triage_agent 的 JSON 输出）
        if event.executor_id == "summary_agent":
            update_text = event.data.text if event.data else ""
            if update_text:
                await event_queue.put(format_sse_event("stream", {
                    "type": "stream",
                    "executor_id": event.executor_id,
                    "text": update_text,
                    "seq": user_message_seq,
                }))
                # 可选：小延迟让流式效果更明显（非阻塞）
                await asyncio.sleep(0.005)
    elif isinstance(event, WorkflowOutputEvent):
        if hasattr(event.data, 'text'):
            final_output = event.data.text
        else:
            final_output = event.data
```

### 4. 修改 `model_registry.py`

在 `AgentModelMapping` 中添加 `summary` 字段：

```python
class AgentModelMapping(BaseModel):
    # ... 现有字段 ...
    summary: Optional[ModelName] = None
```

## Workflow 流程变化

**修改前**：
```
store_query → triage → dispatcher → [agents] → aggregator → yield_output
```

**修改后**：
```
store_query → triage → dispatcher → [agents] → aggregator → summary_agent → yield_output
                                                                    ↓
                                                        (流式 AgentRunUpdateEvent)
```

## 前端处理

### 事件流程

```
Backend                          Frontend
   │                                │
   ├── SSE: thinking ──────────────► appendThinkingEvent()
   │   (agent_invoked, etc.)        │
   │                                │
   ├── SSE: stream ────────────────► appendStreamingText()
   │   (incremental tokens)         │   └── 追加到 .streaming-content
   │                                │   └── 实时渲染 markdown
   │                                │
   ├── SSE: message ───────────────► replaceThinkingWithResponse()
   │   (final content)              │   └── 检测是否有已流式内容
   │                                │   └── 如有，保留流式内容
   │                                │
   └── SSE: done ──────────────────► 完成
```

### 关键修复：保留流式内容

**问题**：原本 `replaceThinkingWithResponse()` 会用最终内容替换所有 HTML，导致已流式的内容被覆盖。

**解决**：检测 `.streaming-content` 的 `data-raw-text` 属性，如果有流式内容则保留：

```javascript
function replaceThinkingWithResponse(content, seq) {
    const thinkingMsg = document.querySelector('.thinking-message');
    if (thinkingMsg) {
        // 检查是否有已流式内容
        const streamingContent = thinkingMsg.querySelector('.streaming-content');
        const hasStreamedContent = streamingContent && streamingContent.getAttribute('data-raw-text');

        if (hasStreamedContent) {
            // 使用已流式的内容
            const streamedText = streamingContent.getAttribute('data-raw-text');
            thinkingMsg.innerHTML = `...${marked.parse(streamedText)}...`;
        } else {
            // 使用最终内容（fallback）
            thinkingMsg.innerHTML = `...${marked.parse(content)}...`;
        }
    }
}
```

### 流式文本追加函数

**`app/static/js/thinking.js`**：

```javascript
function appendStreamingText(text) {
    const thinkingMsg = document.querySelector('.thinking-message');
    if (!thinkingMsg) return;

    let streamingContent = thinkingMsg.querySelector('.streaming-content');
    if (!streamingContent) {
        // 隐藏 thinking dots，更新文本为 "Responding"
        const thinkingDots = thinkingMsg.querySelector('.thinking-dots');
        if (thinkingDots) thinkingDots.style.display = 'none';
        const thinkingText = thinkingMsg.querySelector('.thinking-text');
        if (thinkingText) thinkingText.textContent = 'Responding';

        streamingContent = document.createElement('div');
        streamingContent.className = 'streaming-content message-content';
        thinkingMsg.appendChild(streamingContent);
    }

    // 追加文本并重新渲染 markdown
    const currentText = streamingContent.getAttribute('data-raw-text') || '';
    const newText = currentText + text;
    streamingContent.setAttribute('data-raw-text', newText);
    streamingContent.innerHTML = DOMPurify.sanitize(marked.parse(newText));
}
```

## 性能说明

### asyncio.sleep() 的影响

`asyncio.sleep()` 是**非阻塞**的：

```python
await asyncio.sleep(0.005)  # 5ms 延迟
```

- **不会锁住 event loop**：sleep 期间让出控制权，其他协程可以执行
- **不影响其他 agent**：summary_agent 运行在最后的 superstep，此时其他 agent 已完成
- **目的**：让流式效果更明显，避免 token 太快导致看起来像一次性输出

### 可调参数

| 参数 | 当前值 | 说明 |
|------|--------|------|
| `asyncio.sleep()` | 0.005s | 可以设为 0 去掉延迟，或增大让效果更明显 |

## 文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `app/opsagent/agents/summary_agent.py` | 新建 | Summary agent 定义 |
| `app/opsagent/agents/__init__.py` | 修改 | 导出 create_summary_agent |
| `app/opsagent/workflows/triage_workflow.py` | 修改 | 添加 summary_executor，修改 aggregator |
| `app/opsagent/model_registry.py` | 修改 | AgentModelMapping 添加 summary 字段 |
| `app/routes/messages.py` | 修改 | 监听 AgentRunUpdateEvent，过滤 summary_agent |
| `app/static/js/thinking.js` | 修改 | 添加 appendStreamingText()，修复 replaceThinkingWithResponse() |
| `app/static/js/handlers.js` | 修改 | 添加 stream 事件回调 |

## 注意事项

1. **reject_query 分支**：当 triage 拒绝查询时，不经过 summary agent，直接 yield_output。保留这个行为。

2. **dynamic_workflow**：如果启用了 `DYNAMIC_PLAN=true`，需要对 `dynamic_workflow.py` 做类似修改。

3. **模型成本**：新增一个 LLM 调用（summary agent），会增加延迟和成本。建议使用 `gpt-4.1-mini`。

4. **只转发 summary_agent**：`messages.py` 只转发 `summary_agent` 的 `AgentRunUpdateEvent`，忽略 `triage_agent` 的 JSON 输出。

## 验证步骤

1. 启动开发服务器：`uv run uvicorn app.main:app --reload`
2. 发送消息
3. 检查 SSE 流：
   - 应该看到 `thinking` 事件（agent_invoked, function_start 等）
   - 应该看到多个 `stream` 事件（增量文本）
   - 最后是 `message` 和 `done` 事件
4. 前端应该能逐字显示 summary agent 的输出
5. 最终内容应该保留流式输出的内容，不会被替换
