# Agent Factory: Skill-Driven Multi-Agent Onboarding

## 概述

本文档描述如何将 GenericAI 项目转化为一个通用的 Multi-Agent Starter Kit，通过 Claude Code Skill 驱动用户快速 onboard 自己的 agents。

**核心思路：**
- 保留 `opsagent/` 作为完整的 Demo 应用
- 创建 `agent_factory/` 作为用户的自定义应用
- 通过 `/onboard` Skill 交互式引导用户填充 Pydantic Schema
- Schema 中 Required 字段必须追问，Optional 字段可以推断

---

## 1. Schema 驱动 Skill

**Skill 的工作是填充 Pydantic Schema，不是直接写 YAML。**

```
Skill 读取 Schema 定义
    ↓
Required 字段 → 必须追问用户
Optional 字段 → Claude 决定追问或推断
    ↓
Schema 填充完成
    ↓
从 Schema 生成 agents.yaml + 代码
```

### 追问策略

| Schema 字段 | 追问？ | 说明 |
|------------|--------|------|
| `app_name` | ✅ 必须 | "你的应用叫什么名字？" |
| `domain.name` | ✅ 必须 | "这是什么领域的助手？" |
| `domain.description` | ✅ 必须 | "这个助手帮用户做什么？" |
| `domain.scope` | ❌ 推断 | 从 sub_agents 推断 |
| `sub_agent.key` | ✅ 必须 | "这个 agent 的标识符？" |
| `sub_agent.name` | ✅ 必须 | "显示名称？" |
| `sub_agent.description` | ✅ 必须 | "一句话描述？" |
| `sub_agent.capabilities` | ✅ 必须 | "详细列出能做什么？" |
| `sub_agent.tools` | ✅ 必须 | "需要哪些工具？每个工具做什么？" |
| `sub_agent.instructions` | ⚪ 可选 | 用户想自定义才问 |
| `tool.parameters` | ⚪ 可选 | 能从 description 推断 |
| `orchestration.*` | ❌ 自动 | 全部从 sub_agents 推断 |

---

## 2. Schema 设计

### `app/agent_factory/schemas/config.py`

```python
"""
Agent App Configuration Schema - 为 /onboard Skill 服务

Required 字段 = Skill 必须追问
Optional 字段 = Skill 可以推断或选择性追问
"""

from typing import Optional
from pydantic import BaseModel, Field


# =============================================================================
# SubAgentConfig - Skill 详细追问这些
# =============================================================================

class ToolConfig(BaseModel):
    """Tool 配置"""
    name: str = Field(description="Tool 函数名，如 'get_leave_balance'")  # Required: 追问
    description: str = Field(description="Tool 做什么，给 LLM 看")  # Required: 追问
    # Optional: 可以从 description 推断，不一定追问
    parameters: Optional[list[dict]] = Field(
        default=None,
        description="参数列表。None = Claude 从 description 推断"
    )


class SubAgentConfig(BaseModel):
    """
    Sub-Agent 配置 - SKILL 重点追问这些

    Required 字段 (Skill 必须问):
    - key: agent 标识符
    - name: 显示名称
    - description: 一句话描述
    - capabilities: 能力列表（越详细越好）
    - tools: 工具列表

    Optional 字段 (Skill 可以推断):
    - instructions: 自定义 prompt，None = 从 capabilities/tools 生成
    """
    # ===== REQUIRED: Skill 必须追问 =====
    key: str = Field(description="唯一标识符，如 'leave', 'payroll'")
    name: str = Field(description="显示名称，如 'leave-agent'")
    description: str = Field(description="一句话描述这个 agent 做什么")
    capabilities: list[str] = Field(description="详细能力列表，问用户要具体的")
    tools: list[ToolConfig] = Field(description="工具列表，每个都要问")

    # ===== OPTIONAL: Skill 可以推断 =====
    instructions: Optional[str] = Field(
        default=None,
        description="自定义 system prompt。None = Claude 根据 capabilities/tools 生成"
    )


# =============================================================================
# DomainConfig - 基础信息
# =============================================================================

class DomainConfig(BaseModel):
    """
    Domain 配置

    Required: name, description (必须问)
    Optional: scope (可以从 sub_agents 推断)
    """
    # ===== REQUIRED =====
    name: str = Field(description="Domain 名称，如 'HR Assistant'")
    description: str = Field(description="这个助手帮用户做什么")

    # ===== OPTIONAL =====
    scope: Optional[str] = Field(
        default=None,
        description="助手能帮什么。None = 从 sub_agents 推断"
    )


# =============================================================================
# OrchestrationConfig - Claude 自动推断，用户不需要关心
# =============================================================================

class OrchestrationConfig(BaseModel):
    """
    Orchestration Agent 配置 - SKILL 不问用户，全部自动推断

    这些是 triage/plan/review 等 control agents 的额外配置。
    Claude 根据 SubAgentConfig 信息反向填充这些。
    """
    # 全部 Optional - Claude 从 SubAgentConfig 推断
    triage_additional_instructions: Optional[str] = Field(
        default=None,
        description="Triage 额外指令。从 sub_agent descriptions 推断"
    )
    plan_additional_instructions: Optional[str] = Field(
        default=None,
        description="Plan 额外指令。从 sub_agent capabilities 推断"
    )
    review_criteria: Optional[str] = Field(
        default=None,
        description="Review 完整性标准。从 domain scope 推断"
    )
    clarify_examples: Optional[list[str]] = Field(
        default=None,
        description="Clarify 示例场景。从常见歧义推断"
    )
    summary_style: Optional[str] = Field(
        default=None,
        description="Summary 风格。默认: professional, concise"
    )
    rejection_message_template: Optional[str] = Field(
        default=None,
        description="拒绝消息模板。从 domain scope 推断"
    )


# =============================================================================
# AgentAppConfig - 完整配置（Skill 最终产出）
# =============================================================================

class AgentAppConfig(BaseModel):
    """
    完整的 Agent App 配置

    Skill 工作流:
    1. 追问 Required 字段填充 domain + sub_agents
    2. Claude 推断填充 orchestration
    3. 从这个 config 生成 agents.yaml + 代码
    """
    app_name: str = Field(description="应用目录名，如 'hr_assistant'")  # Required
    domain: DomainConfig  # Required
    sub_agents: list[SubAgentConfig] = Field(min_length=1)  # Required: 至少一个
    orchestration: OrchestrationConfig = Field(
        default_factory=OrchestrationConfig,
        description="Orchestration 配置。Skill 自动推断，不问用户"
    )
```

---

## 3. 目录结构

```
app/
├── opsagent/                    # Demo 应用 (完全不动)
│   └── (现有所有文件)
│
├── agent_factory/               # 用户应用 (skill 在这里生成)
│   ├── agents.yaml              # 从 AgentAppConfig 生成
│   ├── agent_registry.py        # 动态加载
│   ├── prompts/
│   │   ├── templates.py         # 通用 prompt 模板
│   │   └── builder.py           # 从 registry 构建 prompts
│   ├── schemas/
│   │   ├── config.py            # AgentAppConfig (skill schema)
│   │   └── dynamic.py           # 动态 schema 生成
│   ├── agents/
│   │   ├── triage_agent.py      # 使用 prompt builder
│   │   ├── plan_agent.py
│   │   ├── replan_agent.py
│   │   ├── review_agent.py
│   │   ├── clarify_agent.py
│   │   ├── summary_agent.py
│   │   └── sub_agents/          # 用户的 agents
│   │       ├── {agent}_agent.py
│   │       └── tools/
│   ├── workflows/
│   │   ├── triage_workflow.py
│   │   └── dynamic_workflow.py
│   ├── factory.py               # 复制自 opsagent
│   ├── model_registry.py        # 复制自 opsagent
│   └── middleware/              # 复制自 opsagent
│
├── config.py                    # USE_DEMO_OPSAGENT toggle
└── routes/messages.py           # 根据 config import

.claude/skills/
└── onboard.md                   # Onboarding skill
```

---

## 4. Config Toggle

### `app/config.py`

```python
class Settings(BaseSettings):
    # ... existing settings ...

    # Agent package toggle
    use_demo_opsagent: bool = Field(
        default=True,
        description="True: use opsagent demo, False: use agent_factory"
    )

    model_config = SettingsConfigDict(env_file=".env")
```

### `app/routes/messages.py`

```python
from ..dependencies import SettingsDep

# Dynamic import based on config
def get_workflow_factories(settings):
    if settings.use_demo_opsagent:
        from ..opsagent.workflows import create_triage_workflow, create_dynamic_workflow
    else:
        from ..agent_factory.workflows import create_triage_workflow, create_dynamic_workflow
    return create_triage_workflow, create_dynamic_workflow
```

---

## 5. Agent Registry 实现

### `app/agent_factory/agents.yaml`

```yaml
# =============================================================================
# Agent Factory Configuration
# =============================================================================
# Domain info is injected into orchestration agents (triage, plan, etc.)
# Sub-agents are dynamically loaded based on this config

domain:
  name: "HR Assistant"
  description: "帮助员工管理假期、查看工资和福利"
  scope: "假期管理、工资查询、福利咨询"

# Sub-agents registration
agents:
  leave:
    name: "leave-agent"
    description: "处理假期相关操作：查询余额、提交请假、查看历史"
    module: "app.agent_factory.agents.sub_agents.leave_agent"
    factory: "create_leave_agent"
    capabilities:
      - 查询剩余假期天数
      - 提交请假申请（需要开始日期、结束日期、原因）
      - 查看请假历史记录
    tools:
      - get_leave_balance
      - submit_leave_request
      - get_leave_history

  payroll:
    name: "payroll-agent"
    description: "处理工资相关查询：工资单、年度汇总"
    module: "app.agent_factory.agents.sub_agents.payroll_agent"
    factory: "create_payroll_agent"
    capabilities:
      - 查看月度工资单
      - 查看年度收入汇总
    tools:
      - get_payslip
      - get_ytd_summary

  benefits:
    name: "benefits-agent"
    description: "查询员工福利信息"
    module: "app.agent_factory.agents.sub_agents.benefits_agent"
    factory: "create_benefits_agent"
    capabilities:
      - 列出所有可用福利
      - 查看特定福利详情
    tools:
      - list_benefits
      - get_benefit_details
```

### `app/agent_factory/agent_registry.py`

```python
"""
Agent Registry - 从 YAML 动态加载 agents

核心功能:
1. 从 agents.yaml 加载配置
2. 动态 import agent factory 函数
3. 生成 agent descriptions 供 orchestration agents 使用
4. 提供 agent keys 供 schema 验证
"""

import importlib
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Callable, Optional

import yaml


@dataclass(frozen=True)
class AgentDefinition:
    """单个 agent 的定义"""
    key: str
    name: str
    description: str
    module: str
    factory: str
    capabilities: list[str]
    tools: list[str]


@dataclass(frozen=True)
class DomainConfig:
    """Domain 配置 - 注入到 orchestration agents"""
    name: str
    description: str
    scope: str


class AgentRegistry:
    """
    Agent 注册表

    Usage:
        registry = get_agent_registry()

        # 获取所有 agent keys (用于 schema 验证)
        keys = registry.agent_keys  # ["leave", "payroll", "benefits"]

        # 创建 agent 实例
        agent = registry.create_agent("leave", model_registry, model_name)

        # 生成 agent 描述 (用于 triage/plan prompts)
        descriptions = registry.generate_agent_descriptions()

        # 获取 domain 信息
        domain = registry.domain
    """

    def __init__(self, config_path: Optional[Path] = None):
        if config_path is None:
            config_path = Path(__file__).parent / "agents.yaml"

        with open(config_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # Load domain config
        domain_data = config.get("domain", {})
        self._domain = DomainConfig(
            name=domain_data.get("name", "Assistant"),
            description=domain_data.get("description", ""),
            scope=domain_data.get("scope", ""),
        )

        # Load agent definitions
        self._agents: dict[str, AgentDefinition] = {}
        for key, agent_data in config.get("agents", {}).items():
            self._agents[key] = AgentDefinition(
                key=key,
                name=agent_data["name"],
                description=agent_data["description"],
                module=agent_data["module"],
                factory=agent_data["factory"],
                capabilities=agent_data.get("capabilities", []),
                tools=agent_data.get("tools", []),
            )

        # Cache for loaded factory functions
        self._factories: dict[str, Callable] = {}

    @property
    def domain(self) -> DomainConfig:
        """获取 domain 配置"""
        return self._domain

    @property
    def agent_keys(self) -> list[str]:
        """获取所有注册的 agent keys"""
        return list(self._agents.keys())

    def get_agent(self, key: str) -> AgentDefinition:
        """获取指定 agent 的定义"""
        if key not in self._agents:
            raise KeyError(f"Agent '{key}' not found. Available: {self.agent_keys}")
        return self._agents[key]

    def get_factory(self, key: str) -> Callable:
        """获取 agent factory 函数，懒加载"""
        if key not in self._factories:
            agent_def = self.get_agent(key)
            module = importlib.import_module(agent_def.module)
            self._factories[key] = getattr(module, agent_def.factory)
        return self._factories[key]

    def create_agent(
        self,
        key: str,
        registry: Optional[Any] = None,
        model_name: Optional[str] = None,
    ) -> Any:
        """创建 agent 实例"""
        factory = self.get_factory(key)
        return factory(registry, model_name)

    def create_all_agents(
        self,
        registry: Optional[Any] = None,
        model_resolver: Optional[Callable[[str], str]] = None,
    ) -> dict[str, Any]:
        """创建所有注册的 agents"""
        agents = {}
        for key in self.agent_keys:
            model_name = model_resolver(key) if model_resolver else None
            agents[key] = self.create_agent(key, registry, model_name)
        return agents

    def generate_agent_descriptions(self) -> str:
        """
        生成 agent 描述 markdown，用于 triage/plan prompts

        Returns:
            Markdown formatted agent descriptions
        """
        lines = ["## Available Agents\n"]
        for key, agent in self._agents.items():
            lines.append(f"### {key}")
            lines.append(f"**{agent.name}**: {agent.description}\n")
            if agent.capabilities:
                lines.append("Capabilities:")
                for cap in agent.capabilities:
                    lines.append(f"  - {cap}")
            if agent.tools:
                lines.append(f"Tools: {', '.join(agent.tools)}")
            lines.append("")
        return "\n".join(lines)

    def generate_capabilities_summary(self) -> str:
        """生成简短的能力摘要，用于 rejection message"""
        items = []
        for agent in self._agents.values():
            items.append(f"- **{agent.name}**: {agent.description}")
        return "\n".join(items)

    def generate_scope_from_agents(self) -> str:
        """从 agents 推断 scope（如果 domain.scope 为空）"""
        if self._domain.scope:
            return self._domain.scope
        descriptions = [a.description for a in self._agents.values()]
        return "、".join(descriptions)


# =============================================================================
# Global singleton
# =============================================================================

_registry: Optional[AgentRegistry] = None


def get_agent_registry() -> AgentRegistry:
    """获取全局 AgentRegistry 单例"""
    global _registry
    if _registry is None:
        _registry = AgentRegistry()
    return _registry


def reload_agent_registry() -> AgentRegistry:
    """重新加载 registry（开发时用）"""
    global _registry
    _registry = AgentRegistry()
    return _registry
```

---

## 6. Prompt Builder 实现

### `app/agent_factory/prompts/templates.py`

```python
"""
Prompt Templates for Orchestration Agents

使用 {placeholders} 由 PromptBuilder 填充:
- {domain_name}: Domain 名称
- {domain_description}: Domain 描述
- {domain_scope}: Domain 范围
- {agent_descriptions}: Agent 描述 markdown
- {capabilities_summary}: 能力摘要
"""

TRIAGE_AGENT_TEMPLATE = """You are a triage agent for {domain_name}.

{domain_description}

Your job is to analyze the user's LATEST question and route it to the appropriate specialized agent(s).

{agent_descriptions}

## Your Task:
1. Identify what the user is asking in their LATEST message
2. If UNRELATED to any agent's capabilities, set should_reject=true
3. If related, create task(s) for appropriate agent(s)

## Output Format (JSON):
{{
  "should_reject": false,
  "reject_reason": "",
  "tasks": [
    {{"question": "Clear, specific task question", "agent": "agent_key"}}
  ]
}}
"""

PLAN_AGENT_TEMPLATE = """You are a planning agent for {domain_name}.

{domain_description}

{agent_descriptions}

## Your Task
Analyze the user's query and decide:
- **plan**: Create execution plan if clear and actionable
- **clarify**: Request clarification if ambiguous
- **reject**: Reject if completely out of scope

## Planning Guidelines
- Same step number = parallel execution
- Different step numbers = sequential execution
- Step N receives results from step N-1 as context

## Output Format (JSON):
{{
  "action": "plan",
  "reject_reason": "",
  "plan": [
    {{"step": 1, "agent": "agent_key", "question": "..."}}
  ],
  "plan_reason": "..."
}}
"""

REPLAN_AGENT_TEMPLATE = """You are a replan agent for {domain_name}.

You receive feedback from the review agent indicating the response is incomplete.
Decide how to proceed: retry with new plan, request clarification, or reject feedback.

{agent_descriptions}

## Output Format (JSON):
{{
  "action": "retry|clarify|reject",
  "new_plan": [...],
  "rejection_reason": "",
  "clarification_reason": ""
}}
"""

REVIEW_AGENT_TEMPLATE = """You are a review agent for {domain_name}.

Evaluate whether execution results adequately answer the user's query.
Default to COMPLETE unless there's a critical gap.

## Output Format (JSON):
{{
  "is_complete": true,
  "missing_aspects": [],
  "suggested_approach": "",
  "confidence": 0.95
}}
"""

CLARIFY_AGENT_TEMPLATE = """You are a clarification agent for {domain_name}.

When a query is ambiguous, provide a polite clarification request.

{capabilities_summary}

## Output Format (JSON):
{{
  "clarification_request": "...",
  "possible_interpretations": ["...", "..."]
}}
"""

SUMMARY_AGENT_TEMPLATE = """You are a senior analyst synthesizing information.

1. Lead with a direct answer (1-2 sentences)
2. Include detailed data - preserve tables and specifics
3. Add insights or recommended actions if relevant

Do NOT:
- Start with "Based on the agent results..."
- Convert tables to plain text
- Omit important details
"""

REJECT_MESSAGE_TEMPLATE = """I can't help with that topic. {reject_reason}

I can help with:
{capabilities_summary}
"""
```

### `app/agent_factory/prompts/builder.py`

```python
"""
Prompt Builder - 从 AgentRegistry 构建 prompts
"""

from ..agent_registry import get_agent_registry
from .templates import (
    TRIAGE_AGENT_TEMPLATE,
    PLAN_AGENT_TEMPLATE,
    REPLAN_AGENT_TEMPLATE,
    REVIEW_AGENT_TEMPLATE,
    CLARIFY_AGENT_TEMPLATE,
    SUMMARY_AGENT_TEMPLATE,
    REJECT_MESSAGE_TEMPLATE,
)


class PromptBuilder:
    """构建 orchestration agent prompts"""

    def __init__(self):
        self._registry = get_agent_registry()

    def build_triage_prompt(self) -> str:
        return TRIAGE_AGENT_TEMPLATE.format(
            domain_name=self._registry.domain.name,
            domain_description=self._registry.domain.description,
            domain_scope=self._registry.generate_scope_from_agents(),
            agent_descriptions=self._registry.generate_agent_descriptions(),
        )

    def build_plan_prompt(self) -> str:
        return PLAN_AGENT_TEMPLATE.format(
            domain_name=self._registry.domain.name,
            domain_description=self._registry.domain.description,
            agent_descriptions=self._registry.generate_agent_descriptions(),
        )

    def build_replan_prompt(self) -> str:
        return REPLAN_AGENT_TEMPLATE.format(
            domain_name=self._registry.domain.name,
            agent_descriptions=self._registry.generate_agent_descriptions(),
        )

    def build_review_prompt(self) -> str:
        return REVIEW_AGENT_TEMPLATE.format(
            domain_name=self._registry.domain.name,
        )

    def build_clarify_prompt(self) -> str:
        return CLARIFY_AGENT_TEMPLATE.format(
            domain_name=self._registry.domain.name,
            capabilities_summary=self._registry.generate_capabilities_summary(),
        )

    def build_summary_prompt(self) -> str:
        return SUMMARY_AGENT_TEMPLATE

    def build_reject_message(self, reject_reason: str) -> str:
        return REJECT_MESSAGE_TEMPLATE.format(
            reject_reason=reject_reason,
            capabilities_summary=self._registry.generate_capabilities_summary(),
        )


_builder: PromptBuilder | None = None


def get_prompt_builder() -> PromptBuilder:
    global _builder
    if _builder is None:
        _builder = PromptBuilder()
    return _builder
```

---

## 7. Dynamic Schema 实现

### `app/agent_factory/schemas/dynamic.py`

```python
"""
Dynamic Schema Generation

根据 AgentRegistry 中注册的 agents 动态生成 Pydantic schemas，
替代硬编码的 Literal["servicenow", "log_analytics", "service_health"]
"""

from pydantic import BaseModel, Field, field_validator

from ..agent_registry import get_agent_registry


def create_task_assignment_schema() -> type[BaseModel]:
    """动态创建 TaskAssignment schema"""
    registry = get_agent_registry()
    valid_agents = registry.agent_keys

    class TaskAssignment(BaseModel):
        """A single task assignment to a specialized agent."""
        question: str = Field(description="The specific question for this agent")
        agent: str = Field(description=f"Target agent. Valid: {valid_agents}")

        @field_validator("agent")
        @classmethod
        def validate_agent(cls, v: str) -> str:
            if v not in valid_agents:
                raise ValueError(
                    f"Invalid agent '{v}'. Must be one of: {valid_agents}"
                )
            return v

    return TaskAssignment


def create_triage_output_schema() -> type[BaseModel]:
    """动态创建 TriageOutput schema"""
    TaskAssignment = create_task_assignment_schema()

    class TriageOutput(BaseModel):
        """Structured output from the triage agent."""
        should_reject: bool = Field(description="Whether to reject this query")
        reject_reason: str = Field(default="", description="Reason for rejection")
        tasks: list[TaskAssignment] = Field(
            default_factory=list,
            description="Task assignments to specialized agents"
        )

    return TriageOutput


def create_plan_step_schema() -> type[BaseModel]:
    """动态创建 PlanStep schema"""
    registry = get_agent_registry()
    valid_agents = registry.agent_keys

    class PlanStep(BaseModel):
        """A single step in the execution plan."""
        step: int = Field(description="Step number. Same step = parallel")
        agent: str = Field(description=f"Target agent. Valid: {valid_agents}")
        question: str = Field(description="Clear, specific task for this agent")

        @field_validator("agent")
        @classmethod
        def validate_agent(cls, v: str) -> str:
            if v not in valid_agents:
                raise ValueError(
                    f"Invalid agent '{v}'. Must be one of: {valid_agents}"
                )
            return v

    return PlanStep


def create_triage_plan_output_schema() -> type[BaseModel]:
    """动态创建 TriagePlanOutput schema"""
    PlanStep = create_plan_step_schema()

    class TriagePlanOutput(BaseModel):
        """Output from plan agent."""
        action: str = Field(description="plan | clarify | reject")
        reject_reason: str = Field(default="")
        plan: list[PlanStep] = Field(default_factory=list)
        plan_reason: str = Field(default="")

        @field_validator("action")
        @classmethod
        def validate_action(cls, v: str) -> str:
            if v not in ("plan", "clarify", "reject"):
                raise ValueError(f"Invalid action '{v}'")
            return v

    return TriagePlanOutput
```

---

## 8. Workflow 修改

### `app/agent_factory/workflows/dynamic_workflow.py` (关键部分)

```python
# 移除硬编码 imports:
# from ..agents.sub_agents import create_servicenow_agent, ...

# 改为:
from ..agent_registry import get_agent_registry
from ..prompts.builder import get_prompt_builder


def create_dynamic_workflow(registry=None, workflow_model=None, agent_mapping=None):
    """Create dynamic workflow with agents from registry."""

    agent_registry = get_agent_registry()

    # Control agents (unchanged creation, but use prompt builder)
    plan_agent = create_plan_agent(registry, model_for("plan"))
    # ... other control agents ...

    # Dynamic sub_agent creation from registry
    sub_agents = agent_registry.create_all_agents(
        registry=registry,
        model_resolver=model_for if agent_mapping else lambda k: workflow_model,
    )

    # Orchestrator with dynamic agents
    orchestrator = DynamicOrchestrator(agents=sub_agents)

    # ... rest of workflow building unchanged ...


# Reject query with dynamic message
@executor(id="reject_query")
async def reject_query(triage: TriagePlanOutput, ctx: WorkflowContext[Never, str]) -> None:
    builder = get_prompt_builder()
    await ctx.yield_output(builder.build_reject_message(triage.reject_reason))
```

---

## 9. Skill 设计

### `.claude/skills/onboard.md`

```markdown
# Agent Onboarding Skill

通过交互式问答填充 `AgentAppConfig` schema，然后生成代码。

## 核心原则

1. **读取 Schema 定义** - 参考 `app/agent_factory/schemas/config.py`
2. **Required 字段必须追问** - 不能跳过
3. **Optional 字段灵活处理** - 能推断就不问，不确定就问
4. **OrchestrationConfig 完全自动** - 从 SubAgentConfig 推断，不问用户

## 工作流程

### Step 1: 收集基础信息 (Required)

Claude: 你的应用叫什么名字？
User: hr_assistant

Claude: 这是什么领域的助手？帮用户做什么？
User: HR 助手，帮员工查假期、工资、福利

### Step 2: 收集 Sub-Agents (Required，重点！)

Claude: 基于你的描述，我建议这些 agents:
1. leave - 假期管理
2. payroll - 工资查询
3. benefits - 福利咨询

需要调整吗？

User: 可以

Claude: 让我详细了解 leave agent。它能做哪些事情？（请详细列出）

User: 查剩余假期、提交请假（要日期和原因）、看请假历史

Claude: 好的！leave agent 需要这些 tools:
- get_leave_balance - 查剩余假期
- submit_leave_request - 提交请假
- get_leave_history - 查历史

参数我会自动推断。还有要补充的吗？

User: 够了

[继续 payroll, benefits...]

### Step 3: 推断 OrchestrationConfig (自动，不问用户)

Claude 内部推断:
- triage: Route to leave/payroll/benefits based on descriptions
- plan: Consider all capabilities for parallel/sequential planning
- review: Check completeness against domain scope
- rejection: Use domain scope for message

### Step 4: 生成代码

Claude: 信息收集完成！生成中...

✅ 生成完成:
- app/agent_factory/agents.yaml
- app/agent_factory/agents/sub_agents/leave_agent.py
- app/agent_factory/agents/sub_agents/tools/leave_tools.py
- ...

下一步: 实现 tools 中的 TODO

## 推断函数示例

def infer_orchestration(config: AgentAppConfig) -> OrchestrationConfig:
    """从 sub_agents 推断 orchestration 配置"""

    # 收集所有 agent 信息
    agent_descriptions = "\n".join(
        f"- {a.key}: {a.description}" for a in config.sub_agents
    )
    all_capabilities = []
    for agent in config.sub_agents:
        all_capabilities.extend(agent.capabilities)

    # 推断 scope（如果没提供）
    scope = config.domain.scope or "、".join(
        a.description for a in config.sub_agents
    )

    return OrchestrationConfig(
        triage_additional_instructions=f"Available agents:\n{agent_descriptions}",
        plan_additional_instructions=f"Capabilities:\n{chr(10).join(f'- {c}' for c in all_capabilities)}",
        review_criteria=f"Ensure the response covers: {scope}",
        rejection_message_template=f"I can only help with: {scope}",
    )
```

---

## 10. 文件清单

| 操作 | 文件路径 |
|------|----------|
| **保持不变** | `app/opsagent/*` |
| CREATE | `app/agent_factory/` (复制 opsagent 后修改) |
| CREATE | `app/agent_factory/agents.yaml` |
| CREATE | `app/agent_factory/agent_registry.py` |
| CREATE | `app/agent_factory/schemas/config.py` |
| CREATE | `app/agent_factory/schemas/dynamic.py` |
| CREATE | `app/agent_factory/prompts/templates.py` |
| CREATE | `app/agent_factory/prompts/builder.py` |
| CREATE | `.claude/skills/onboard.md` |
| MODIFY | `app/agent_factory/schemas/triage.py` (use dynamic) |
| MODIFY | `app/agent_factory/schemas/triage_plan.py` (use dynamic) |
| MODIFY | `app/agent_factory/agents/*.py` (use prompt builder) |
| MODIFY | `app/agent_factory/workflows/*.py` (use registry) |
| MODIFY | `app/config.py` (add USE_DEMO_OPSAGENT) |
| MODIFY | `app/routes/messages.py` (dynamic import) |
| DELETE | `app/agent_factory/agents/sub_agents/servicenow_agent.py` 等 |

---

## 11. 验证计划

```bash
# 1. 测试 opsagent demo (默认)
USE_DEMO_OPSAGENT=true uv run uvicorn app.main:app --reload

# 2. 测试 agent_factory
USE_DEMO_OPSAGENT=false uv run uvicorn app.main:app --reload

# 3. 验证 registry
uv run python -c "
from app.agent_factory.agent_registry import get_agent_registry
r = get_agent_registry()
print('Domain:', r.domain.name)
print('Agents:', r.agent_keys)
print(r.generate_agent_descriptions())
"
```
