# Workflow Output Event 问题修复记录

## 问题现象

在多轮对话中，UI 能看到流式响应，但数据库存储的却是 "No response from workflow"。

```
UI 显示: "There are 2 failed pipelines in the last 24 hours..."
DB 存储: "No response from workflow"
```

## 根本原因

`dynamic_workflow` 没有 emit `WorkflowOutputEvent`，导致 `messages.py` 中的 `final_output` 始终为 `None`。

### 代码流程 (messages.py)

```python
async for event in workflow.run_stream(input_data):
    if isinstance(event, AgentRunUpdateEvent):
        # 流式文本 → 发送到 UI ✓
        await event_queue.put(format_sse_event("stream", {...}))
    elif isinstance(event, WorkflowOutputEvent):
        # 最终输出 → 用于保存到 DB
        final_output = event.data  # ← dynamic_workflow 从未触发这里！

# 保存结果
if final_output:
    reply = final_output
else:
    reply = "No response from workflow"  # ← 所以总是走这里
```

## Triage Workflow vs Dynamic Workflow

### Triage Workflow - 使用框架内置 AgentExecutor

```python
# triage_workflow.py
from agent_framework import AgentExecutor

summary_executor = AgentExecutor(summary_agent, id="summary_agent", output_response=True)
```

`AgentExecutor` 是框架提供的执行器，当设置 `output_response=True` 时，框架**自动**：
1. 发送 `AgentRunUpdateEvent` 用于流式显示
2. 发送 `WorkflowOutputEvent` 用于最终输出

### Dynamic Workflow - 使用自定义 Executor

```python
# dynamic_workflow.py (修复前)
class ReviewExecutor(Executor):
    async def _stream_summary(self, results, original_query, ctx):
        async for event in self._summary_agent.run_stream(...):
            if event.text:
                await ctx.add_event(AgentRunUpdateEvent(self.id, event))
        # ← 缺失：没有调用 ctx.yield_output()！

class StreamingSummaryExecutor(Executor):
    async def stream_output(self, request, ctx):
        async for event in self._summary_agent.run_stream(...):
            if event.text:
                await ctx.add_event(AgentRunUpdateEvent(self.id, event))
        # ← 缺失：没有调用 ctx.yield_output()！
```

自定义 Executor 需要**手动**调用 `ctx.yield_output()` 来 emit `WorkflowOutputEvent`。

## 修复方案

在 `dynamic_workflow.py` 的三个流式方法中添加 `ctx.yield_output()`：

```python
# 修复后
async def _stream_summary(self, results, original_query, ctx):
    full_response_parts: list[str] = []
    async for event in self._summary_agent.run_stream(...):
        if event.text:
            full_response_parts.append(event.text)
            await ctx.add_event(AgentRunUpdateEvent(self.id, event))

    # 新增：emit WorkflowOutputEvent
    full_response = "".join(full_response_parts)
    if full_response:
        await ctx.yield_output(full_response)
```

修复的方法：
1. `ReviewExecutor._stream_summary()`
2. `StreamingSummaryExecutor.stream_output()`
3. `StreamingSummaryExecutor.stream_existing()`

## 关于 Race Condition

### 理论上存在的场景

Race condition 在以下条件下可能发生：

```
同一个 conversation_id + 同时两个请求
```

触发方式：
1. 双击发送按钮
2. 前端网络重试
3. 绕过 UI 直接调用 API

### 为什么实际很难触发

1. **前端防护** (`handlers.js:177,244`)
   ```javascript
   input.disabled = true;   // 发送后立即禁用
   // ... 等待响应 ...
   input.disabled = false;  // 完成后才启用
   ```

2. **不同对话互不影响**
   - 每个对话有唯一的 `conversation_id`
   - 两个浏览器窗口通常创建不同的对话

3. **PostgreSQL 保存机制**
   ```python
   # postgresql.py:211-235
   DELETE FROM messages WHERE conversation_id = $1  # 删除所有
   INSERT INTO messages ...  # 插入所有
   ```
   - 虽然是 "DELETE all + INSERT all" 模式
   - 但前端锁定 + 不同对话 ID 使并发几乎不可能

### 如果需要后端防护

可选方案（低优先级）：
1. **Redis 分布式锁** - 同一对话同时只允许一个请求
2. **乐观锁 + 版本号** - 检测并发修改
3. **仅追加消息** - 不删除重写，只追加新消息

## 总结

| 问题 | 原因 | 状态 |
|------|------|------|
| 所有响应都是 "No response" | dynamic_workflow 不 emit WorkflowOutputEvent | ✅ 已修复 |
| Race condition 覆盖数据 | 并发请求 + DELETE/INSERT 模式 | ⚠️ 理论存在，实际被前端防护 |

## 关键代码位置

| 文件 | 行号 | 说明 |
|------|------|------|
| `app/routes/messages.py` | 171-176 | 监听 WorkflowOutputEvent |
| `app/opsagent/workflows/dynamic_workflow.py` | 517-530 | ReviewExecutor._stream_summary (已修复) |
| `app/opsagent/workflows/dynamic_workflow.py` | 577-590 | StreamingSummaryExecutor.stream_output (已修复) |
| `app/opsagent/workflows/dynamic_workflow.py` | 614-627 | StreamingSummaryExecutor.stream_existing (已修复) |
| `app/opsagent/workflows/triage_workflow.py` | 273 | AgentExecutor with output_response=True |
| `app/static/js/handlers.js` | 177, 244 | 前端输入锁定 |
| `app/infrastructure/postgresql.py` | 211-235 | DELETE all + INSERT all 保存模式 |
