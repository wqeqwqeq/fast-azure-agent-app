# Dynamic Workflow 简化设计方案

## 概述

本文档描述了 Dynamic Workflow 的重构设计，将复杂的 `dynamic_triage_agent` 拆分为更清晰的 `plan_agent` 和 `replan_agent`，简化了整体架构。

## 用户需求

1. **Streaming**: 需要真正的 streaming 输出（接受额外 LLM 调用）
2. **Clarify**: 直接结束，是终止节点
3. **Review 时机**: 只有 initial 需要 review，retry 直接输出

## 核心设计思路

### 关于 "为什么要两次 LLM 调用"

如果不需要 streaming，review agent 的 `summary` 字段完全够用。

但既然需要真正的 streaming，就必须有一个 streaming 输出的 LLM 调用。原因：
- **Structured output** (JSON) 和 **streaming** 无法同时实现
- Review 需要 JSON 来做判断 (is_complete, missing_aspects 等)
- Streaming 需要 unstructured text output

### 架构选择

**选择: ReviewExecutor 做两件事 (两次调用)**
```
orchestrator → ReviewExecutor:
                 ├─ 调用 1: 判断 is_complete (可以用小模型/fast)
                 ├─ 如果 complete: 调用 2: streaming 输出
                 └─ 如果 incomplete: 返回 JSON 给 replan
```

优点：
1. 职责清晰：一个 executor 负责 "评估 + 输出"
2. 第一次调用可以用更小/更快的模型只做判断
3. 减少 workflow 的节点数量

## Workflow 流程图

```
store_query → TriageExecutor (plan_mode)
                    ↓
    ┌───────────────┼───────────────┐
    ↓               ↓               ↓
[clarify]      [orchestrator]   [reject]
    ↓               ↓               ↓
   END     ReviewExecutor          END
              ├─ 判断 complete?
              ├─ [complete] → streaming 输出 → END
              └─ [incomplete] → TriageExecutor (replan_mode)
                                     ↓
                               ┌─────┴─────┐
                               ↓           ↓
                        [accept]      [reject]
                            ↓             ↓
                       orchestrator    streaming_summary (现有结果)
                            ↓             ↓
                       streaming_summary  END
                            ↓
                           END
```

## 组件设计

### 1. Agents

| Agent | 文件 | 职责 | 输出格式 |
|-------|------|------|----------|
| Plan Agent | `agents/plan_agent.py` | 分析用户查询，生成执行计划 | `TriagePlanOutput` (JSON) |
| Replan Agent | `agents/replan_agent.py` | 处理 review 反馈，决定是否重试 | `TriageReplanOutput` (JSON) |
| Review Agent | `agents/review_agent.py` | 判断结果是否完整 | `ReviewOutput` (JSON) |
| Summary Agent | `agents/summary_agent.py` | streaming 输出最终答案 | 无 (streaming text) |

### 2. Schemas

```python
# schemas/triage_plan.py
class PlanStep(BaseModel):
    step: int  # 同 step = 并行执行
    agent: Literal["servicenow", "log_analytics", "service_health"]
    question: str

class TriagePlanOutput(BaseModel):
    action: Literal["plan", "clarify", "reject"]
    reject_reason: str = ""
    plan: list[PlanStep] = []
    plan_reason: str = ""

# schemas/triage_replan.py
class TriageReplanOutput(BaseModel):
    accept_review: bool
    new_plan: list[PlanStep] = []
    rejection_reason: str = ""

# schemas/review.py (简化版，无 summary)
class ReviewOutput(BaseModel):
    is_complete: bool
    missing_aspects: list[str] = []
    suggested_approach: str = ""
    confidence: float = 0.0
```

### 3. Executors

#### TriageExecutor
合并 plan 和 replan 两种模式，通过不同的 handler 处理不同的输入类型：

```python
class TriageExecutor(Executor):
    def __init__(self, plan_agent: ChatAgent, replan_agent: ChatAgent):
        self._plan_agent = plan_agent
        self._replan_agent = replan_agent

    @handler
    async def handle_plan(self, request: PlanRequest, ctx: WorkflowContext[TriagePlanOutput]):
        """处理初始用户查询"""
        ...

    @handler
    async def handle_replan(self, request: ReplanRequest, ctx: WorkflowContext[TriageReplanOutput]):
        """处理 review 反馈"""
        ...
```

#### ReviewExecutor
评估结果完整性，complete 时直接 streaming 输出：

```python
class ReviewExecutor(Executor):
    def __init__(self, review_agent: ChatAgent, summary_agent: ChatAgent):
        self._review_agent = review_agent
        self._summary_agent = summary_agent

    @handler
    async def review(self, request: ReviewRequest, ctx: WorkflowContext[ReplanRequest, str]):
        decision = await self._review_agent.run(...)  # JSON

        if decision.is_complete:
            async for chunk in self._summary_agent.run_stream(...):
                await ctx.yield_output(chunk)
        else:
            await ctx.send_message(ReplanRequest(...))
```

#### StreamingSummaryExecutor
retry 后直接 streaming 输出（不经过 review）：

```python
class StreamingSummaryExecutor(Executor):
    @handler
    async def stream_output(self, request: StreamingRequest, ctx: WorkflowContext[Never, str]):
        async for chunk in self._summary_agent.run_stream(...):
            await ctx.yield_output(chunk)

    @handler
    async def stream_existing(self, triage: TriageReplanOutput, ctx: WorkflowContext[Never, str]):
        """当 replan 被拒绝时，streaming 现有结果"""
        ...
```

### 4. Workflow Builder

```python
workflow = (
    WorkflowBuilder(
        name="Dynamic Ops Workflow",
        max_iterations=10,  # 允许合理的重试循环
    )
    .set_start_executor(store_query)
    .add_edge(store_query, triage)

    # 统一的 triage 路由（处理 TriagePlanOutput 和 TriageReplanOutput）
    .add_multi_selection_edge_group(
        triage,
        [clarify_executor, reject_query, orchestrator, streaming_summary],
        selection_func=select_triage_path,
    )

    # Orchestrator → Review 或 StreamingSummary
    .add_edge(orchestrator, review_executor)
    .add_edge(orchestrator, streaming_summary)

    # Review → Triage (replan mode)
    .add_edge(review_executor, triage)

    .build()
)
```

## 关键实现细节

### 1. 统一路由函数

由于 workflow 不允许重复边，使用统一的 selection 函数处理两种 triage 输出：

```python
def select_triage_path(
    triage: TriagePlanOutput | TriageReplanOutput, target_ids: list[str]
) -> list[str]:
    clarify_id, reject_id, orchestrator_id, streaming_id = target_ids

    if isinstance(triage, TriagePlanOutput):
        # Plan mode routing
        if triage.action == "clarify":
            return [clarify_id]
        elif triage.action == "reject":
            return [reject_id]
        else:
            return [orchestrator_id]
    else:
        # Replan mode routing
        if triage.accept_review and triage.new_plan:
            return [orchestrator_id]
        else:
            return [streaming_id]
```

### 2. 区分 initial vs retry 路径

Orchestrator 通过发送不同类型的消息来路由：
- Initial: `TriagePlanOutput` → 发送 `ReviewRequest` → 去 review_executor
- Retry: `TriageReplanOutput` → 发送 `StreamingRequest` → 去 streaming_summary

### 3. 迭代控制

使用 `WorkflowBuilder(max_iterations=10)` 控制最大循环次数，防止无限循环。

## 文件清单

### 新建文件
- `app/opsagent/agents/plan_agent.py`
- `app/opsagent/agents/replan_agent.py`
- `app/opsagent/schemas/triage_plan.py`
- `app/opsagent/schemas/triage_replan.py`

### 修改文件
- `app/opsagent/schemas/review.py` - 移除 summary 字段
- `app/opsagent/agents/review_agent.py` - 更新 prompt
- `app/opsagent/workflows/dynamic_workflow.py` - 重写
- `app/opsagent/__init__.py` - 更新 exports
- `app/opsagent/agents/__init__.py` - 更新 exports
- `app/opsagent/schemas/__init__.py` - 更新 exports
- `app/opsagent/model_registry.py` - 更新 AgentModelMapping
- `app/routes/models.py` - 更新 agent 列表

### 删除文件
- `app/opsagent/agents/dynamic_triage_agent.py`
- `app/opsagent/schemas/dynamic_triage.py`

## 验证计划

1. **Happy path**: plan → execute → review(complete) → streaming output
2. **Retry path**: plan → execute → review(incomplete) → replan(accept) → execute → streaming output
3. **Reject path**: plan → reject → END
4. **Clarify path**: plan → clarify → END
5. **Replan reject path**: plan → execute → review(incomplete) → replan(reject) → streaming existing → END
