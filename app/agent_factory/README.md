# Agent Factory Documentation

## Overview

Agent Factory is a schema-driven multi-agent system that separates **AI-generated** configuration from **framework code**.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            /onboard Skill                                   │
│                    (Interactive configuration collection)                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                    subagent_config.py (AI Generated)                        │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ DOMAIN_NAME = "HR Assistant"                                         │   │
│  │ DOMAIN_DESCRIPTION = "Helps employees with HR tasks"                 │   │
│  │ SUB_AGENTS = [SubAgentConfig(key="leave", ...), ...]                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        SubAgentRegistry (Framework)                         │
│  ┌─────────────────────────────────────────────────────────────────────┐   │
│  │ • agent_keys: ["leave", "payroll"]                                   │   │
│  │ • generate_descriptions() → "- **leave** (leave-agent): ..."        │   │
│  │ • generate_descriptions_with_tools() → includes tool info           │   │
│  │ • create_all_agents() → dict[str, ChatAgent]                        │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
┌───────────────────────────────┐   ┌───────────────────────────────────────┐
│   Orchestration Agents        │   │         Sub-Agents                    │
│   (Framework Code)            │   │         (AI Generated)                │
│ ┌───────────────────────────┐ │   │ ┌───────────────────────────────────┐ │
│ │ TriageAgentConfig         │ │   │ │ leave_agent.py                    │ │
│ │  • build_prompt(registry) │ │   │ │  • create_leave_agent()           │ │
│ │  • build_schema(registry) │ │   │ │  • tools: get_leave_balance, ...  │ │
│ └───────────────────────────┘ │   │ └───────────────────────────────────┘ │
└───────────────────────────────┘   └───────────────────────────────────────┘
```

---

## File Structure

```
app/agent_factory/
├── __init__.py                 # Module exports (SubAgentRegistry, get_registry)
├── subagent_config.py          # [AI GENERATED] Domain config + SUB_AGENTS list
├── subagent_registry.py        # [FRAMEWORK] Registry that reads subagent_config
├── factory.py                  # [FRAMEWORK] create_agent() function
├── model_registry.py           # [FRAMEWORK] Model definitions + ModelRegistry
│
├── middleware/
│   ├── __init__.py
│   └── observability.py        # [FRAMEWORK] Agent/function tracking middleware
│
├── prompts/
│   ├── __init__.py
│   └── templates.py            # [FRAMEWORK] Prompt templates with {placeholders}
│
├── schemas/
│   ├── __init__.py
│   ├── config.py               # [FRAMEWORK] SubAgentConfig, ToolConfig definitions
│   └── dynamic.py              # [FRAMEWORK] Runtime schema generation functions
│
├── agents/
│   ├── orchestration/          # [FRAMEWORK] Orchestration agent configs
│   │   ├── triage_agent.py     #   TriageAgentConfig.build_prompt/build_schema
│   │   ├── plan_agent.py       #   PlanAgentConfig.build_prompt/build_schema
│   │   ├── replan_agent.py     #   ReplanAgentConfig.build_prompt/build_schema
│   │   ├── review_agent.py     #   ReviewAgentConfig.build_prompt/build_schema
│   │   ├── clarify_agent.py    #   ClarifyAgentConfig.build_prompt/build_schema
│   │   └── summary_agent.py    #   SummaryAgentConfig.build_prompt (no schema)
│   │
│   └── sub_agents/             # [AI GENERATED] Sub-agent implementations
│       ├── {key}_agent.py      #   create_{key}_agent() factory function
│       └── tools/
│           └── {key}_tools.py  #   Tool function implementations
│
└── workflows/
    ├── __init__.py
    └── dynamic_workflow.py     # [FRAMEWORK] Workflow that connects everything
```

---

## File Descriptions

### Core Files

| File | Type | Description |
|------|------|-------------|
| `subagent_config.py` | AI Generated | Contains `DOMAIN_NAME`, `DOMAIN_DESCRIPTION`, and `SUB_AGENTS` list. This is the ONLY file `/onboard` modifies. |
| `subagent_registry.py` | Framework | `SubAgentRegistry` class that reads from `subagent_config.py` and provides methods for generating agent descriptions. |
| `factory.py` | Framework | `create_agent()` function that creates `ChatAgent` instances with proper middleware. |
| `model_registry.py` | Framework | Model definitions (`GPT41`, `GPT41_MINI`), `ModelRegistry` for cloud deployment, `AzOpenAIEnvSettings` for local dev. |

### Middleware

| File | Type | Description |
|------|------|-------------|
| `middleware/observability.py` | Framework | `observability_agent_middleware` - Emits SSE events for agent start/finish. Uses `get_settings().orchestration_agents` to determine which agents should output their structured response. |

### Prompts

| File | Type | Description |
|------|------|-------------|
| `prompts/templates.py` | Framework | Template strings with `{placeholders}` for dynamic content: `TRIAGE_TEMPLATE`, `PLAN_TEMPLATE`, `REPLAN_TEMPLATE`, `REVIEW_TEMPLATE`, `CLARIFY_TEMPLATE`, `SUMMARY_TEMPLATE`, `REJECTION_MESSAGE_TEMPLATE`. |

### Schemas

| File | Type | Description |
|------|------|-------------|
| `schemas/config.py` | Framework | Pydantic models for configuration: `SubAgentConfig`, `ToolConfig`, `ToolParameterConfig`. |
| `schemas/dynamic.py` | Framework | Functions that generate Pydantic schemas at runtime based on valid agent keys: `create_triage_output_schema()`, `create_plan_step_schema()`, `create_triage_plan_output_schema()`, etc. |

### Agents

| File | Type | Description |
|------|------|-------------|
| `agents/orchestration/*.py` | Framework | Each orchestration agent has a `Config` dataclass with `build_prompt()` and `build_schema()` methods, plus a `create_*_agent()` factory function. |
| `agents/sub_agents/*.py` | AI Generated | Sub-agent implementations with `create_{key}_agent()` factory functions and tool imports. |

### Workflows

| File | Type | Description |
|------|------|-------------|
| `workflows/dynamic_workflow.py` | Framework | `create_dynamic_workflow()` function that wires together all agents into a workflow with triage → orchestrate → review → summary flow. |

---

## Data Flow: Orchestration Agent (Triage)

This section documents how `triage-agent`'s prompt and schema are dynamically generated.

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. subagent_config.py (AI Generated)                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ DOMAIN_NAME = "HR Assistant"                                                │
│ DOMAIN_DESCRIPTION = "Helps employees with HR tasks"                        │
│ SUB_AGENTS = [                                                              │
│     SubAgentConfig(key="leave", name="leave-agent", capabilities=[...]),   │
│     SubAgentConfig(key="payroll", name="payroll-agent", capabilities=[...])│
│ ]                                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. SubAgentRegistry                                                         │
├─────────────────────────────────────────────────────────────────────────────┤
│ registry = SubAgentRegistry()  # Reads from subagent_config.py              │
│                                                                             │
│ registry.domain_name          → "HR Assistant"                              │
│ registry.domain_description   → "Helps employees with HR tasks"             │
│ registry.agent_keys           → ["leave", "payroll"]                        │
│ registry.generate_descriptions() →                                          │
│     "- **leave** (leave-agent): Handles vacation and leave requests         │
│        - Check leave balance                                                │
│        - Submit leave requests                                              │
│      - **payroll** (payroll-agent): Handles payroll queries                 │
│        - View pay stubs"                                                    │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                    ┌─────────────────┴─────────────────┐
                    ▼                                   ▼
┌───────────────────────────────────┐   ┌───────────────────────────────────┐
│ 3a. Prompt Generation             │   │ 3b. Schema Generation             │
├───────────────────────────────────┤   ├───────────────────────────────────┤
│ TriageAgentConfig.build_prompt()  │   │ TriageAgentConfig.build_schema()  │
│                                   │   │                                   │
│ TRIAGE_TEMPLATE.format(           │   │ create_triage_output_schema(      │
│   domain_name=                    │   │     registry.agent_keys           │
│     registry.domain_name,         │   │ )                                 │
│   domain_description=             │   │                                   │
│     registry.domain_description,  │   │ Returns dynamically created:      │
│   agent_descriptions=             │   │ class TriageOutput(BaseModel):    │
│     registry.generate_descriptions()│   │   should_reject: bool           │
│ )                                 │   │   reject_reason: str              │
│                                   │   │   tasks: list[TaskAssignment]     │
│ Returns complete prompt string    │   │     # TaskAssignment.agent has    │
│ with all placeholders filled      │   │     # @field_validator checking   │
│                                   │   │     # agent in ["leave","payroll"]│
└───────────────────────────────────┘   └───────────────────────────────────┘
                    │                                   │
                    └─────────────────┬─────────────────┘
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. create_triage_agent()                                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│ def create_triage_agent(sub_registry, model_registry, model_name):          │
│     return create_agent(                                                    │
│         name="triage-agent",                                                │
│         description="Routes queries to HR Assistant agents",                │
│         instructions=CONFIG.build_prompt(sub_registry),    # ← Dynamic     │
│         response_format=CONFIG.build_schema(sub_registry), # ← Dynamic     │
│         registry=model_registry,                                            │
│         model_name=model_name,                                              │
│     )                                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. ChatAgent Instance                                                       │
├─────────────────────────────────────────────────────────────────────────────┤
│ ChatAgent(                                                                  │
│     name="triage-agent",                                                    │
│     instructions="You are a triage agent for HR Assistant...",              │
│     response_format=TriageOutput,  # Pydantic schema with agent validation │
│     middleware=[observability_agent_middleware],                            │
│ )                                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Code Walkthrough

**Step 1: Configuration (AI Generated)**

```python
# subagent_config.py
DOMAIN_NAME = "HR Assistant"
DOMAIN_DESCRIPTION = "Helps employees with HR tasks"
SUB_AGENTS = [
    SubAgentConfig(
        key="leave",
        name="leave-agent",
        description="Handles vacation and leave requests",
        capabilities=["Check leave balance", "Submit leave requests"],
    ),
    SubAgentConfig(
        key="payroll",
        name="payroll-agent",
        description="Handles payroll queries",
        capabilities=["View pay stubs"],
    ),
]
```

**Step 2: Registry reads configuration**

```python
# subagent_registry.py
from .subagent_config import DOMAIN_NAME, DOMAIN_DESCRIPTION, SUB_AGENTS

class SubAgentRegistry:
    def __init__(self):
        self._sub_agents = SUB_AGENTS
        self._domain_name = DOMAIN_NAME

    def generate_descriptions(self) -> str:
        """Used by orchestration agents to build their prompts."""
        lines = []
        for agent in self._sub_agents:
            lines.append(f"- **{agent.key}** ({agent.name}): {agent.description}")
            for cap in agent.capabilities:
                lines.append(f"  - {cap}")
        return "\n".join(lines)
```

**Step 3a: Prompt Generation**

```python
# agents/orchestration/triage_agent.py
@dataclass(frozen=True)
class TriageAgentConfig:
    name: str = "triage-agent"

    def build_prompt(self, registry: SubAgentRegistry) -> str:
        return TRIAGE_TEMPLATE.format(
            domain_name=registry.domain_name,           # "HR Assistant"
            domain_description=registry.domain_description,
            agent_descriptions=registry.generate_descriptions(),  # Dynamic!
            additional_instructions="",
        )
```

**Step 3b: Schema Generation**

```python
# schemas/dynamic.py
def create_triage_output_schema(valid_agents: list[str]) -> type[BaseModel]:
    """Create schema with agent validation."""
    valid_set = frozenset(valid_agents)  # {"leave", "payroll"}

    class TaskAssignment(BaseModel):
        question: str
        agent: str

        @field_validator("agent")
        @classmethod
        def validate_agent(cls, v: str) -> str:
            if v not in valid_set:
                raise ValueError(f"Invalid agent '{v}'. Must be one of: {list(valid_set)}")
            return v

    class TriageOutput(BaseModel):
        should_reject: bool = False
        reject_reason: str = ""
        tasks: list[TaskAssignment] = []

    return TriageOutput
```

**Step 4: Create Agent**

```python
# agents/orchestration/triage_agent.py
def create_triage_agent(sub_registry, model_registry=None, model_name=None):
    return create_agent(
        name=CONFIG.name,
        instructions=CONFIG.build_prompt(sub_registry),   # ← Filled prompt
        response_format=CONFIG.build_schema(sub_registry), # ← Dynamic schema
    )
```

---

## Data Flow: Sub-Agent (Leave)

This section documents how a sub-agent is created and invoked.

### Flow Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. subagent_config.py (AI Generated)                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ SUB_AGENTS = [                                                              │
│     SubAgentConfig(                                                         │
│         key="leave",                                                        │
│         name="leave-agent",                                                 │
│         description="Handles vacation and leave requests",                  │
│         capabilities=["Check leave balance", "Submit leave requests"],      │
│         tools=[                                                             │
│             ToolConfig(name="get_leave_balance", description="..."),        │
│             ToolConfig(name="submit_leave", description="..."),             │
│         ],                                                                  │
│     ),                                                                      │
│ ]                                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 2. /onboard generates sub-agent file                                        │
├─────────────────────────────────────────────────────────────────────────────┤
│ # agents/sub_agents/leave_agent.py                                          │
│                                                                             │
│ from .tools.leave_tools import get_leave_balance, submit_leave              │
│                                                                             │
│ @dataclass(frozen=True)                                                     │
│ class LeaveAgentConfig:                                                     │
│     name: str = "leave-agent"                                               │
│     description: str = "Handles vacation and leave requests"                │
│     instructions: str = """You are a leave agent...                         │
│                                                                             │
│         ## Your Capabilities                                                │
│         - Check leave balance                                               │
│         - Submit leave requests                                             │
│         ..."""                                                              │
│                                                                             │
│ def create_leave_agent(registry=None, model_name=None):                     │
│     return create_agent(                                                    │
│         name=CONFIG.name,                                                   │
│         instructions=CONFIG.instructions,  # ← Static (AI generated once)  │
│         tools=[get_leave_balance, submit_leave],                            │
│     )                                                                       │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 3. /onboard generates tools file                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ # agents/sub_agents/tools/leave_tools.py                                    │
│                                                                             │
│ def get_leave_balance(                                                      │
│     employee_id: Annotated[str, "Employee ID"],                             │
│ ) -> str:                                                                   │
│     """Get remaining leave days for an employee."""                         │
│     # TODO: Implement with actual API call                                  │
│     raise NotImplementedError()                                             │
│                                                                             │
│ def submit_leave(                                                           │
│     employee_id: Annotated[str, "Employee ID"],                             │
│     start_date: Annotated[str, "Start date"],                               │
│     end_date: Annotated[str, "End date"],                                   │
│     reason: Annotated[str, "Reason for leave"],                             │
│ ) -> str:                                                                   │
│     """Submit a leave request."""                                           │
│     # TODO: Implement with actual API call                                  │
│     raise NotImplementedError()                                             │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 4. SubAgentRegistry.create_agent()                                          │
├─────────────────────────────────────────────────────────────────────────────┤
│ def create_agent(self, key: str, model_registry, model_name):               │
│     # Dynamic import: app.agent_factory.agents.sub_agents.leave_agent       │
│     module = importlib.import_module(f"...sub_agents.{key}_agent")          │
│                                                                             │
│     # Call factory function: create_leave_agent()                           │
│     factory_func = getattr(module, f"create_{key}_agent")                   │
│     return factory_func(registry=model_registry, model_name=model_name)     │
└─────────────────────────────────────────────────────────────────────────────┘
                                      │
                                      ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│ 5. ChatAgent Instance with Tools                                            │
├─────────────────────────────────────────────────────────────────────────────┤
│ ChatAgent(                                                                  │
│     name="leave-agent",                                                     │
│     instructions="You are a leave agent that handles vacation...",          │
│     tools=[get_leave_balance, submit_leave],  # ← Function references      │
│     middleware=[                                                            │
│         observability_agent_middleware,                                     │
│         observability_function_middleware,  # ← Added because tools exist  │
│     ],                                                                      │
│ )                                                                           │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Key Differences: Orchestration vs Sub-Agents

| Aspect | Orchestration Agent | Sub-Agent |
|--------|---------------------|-----------|
| Prompt | **Dynamic** - built at runtime from registry | **Static** - AI generated once by /onboard |
| Schema | **Dynamic** - includes agent validation | **None** - uses plain text output |
| Tools | **None** - orchestration only | **Has tools** - actual business logic |
| Source | Framework code (not modified) | AI generated (by /onboard) |
| Middleware | `observability_agent_middleware` | `observability_agent_middleware` + `observability_function_middleware` |

---

## Middleware: Orchestration Agent Output

The middleware uses `get_settings().orchestration_agents` to determine which agents should output their structured response:

```python
# app/config.py
orchestration_agents: set[str] = {
    "triage-agent",
    "plan-agent",
    "replan-agent",
    "review-agent",
}
```

```python
# middleware/observability.py
@agent_middleware
async def observability_agent_middleware(context, next):
    agent_name = context.agent.name  # e.g., "triage-agent"

    # Check if this is an orchestration agent
    from app.config import get_settings
    is_orchestration = agent_name in get_settings().orchestration_agents

    await next(context)

    # If orchestration agent, include output in event
    if is_orchestration:
        output = context.result.text  # JSON structured output
        await emit_event({
            "type": "agent_finished",
            "agent": agent_name,
            "output": serialize_result(output),  # ← Shown in thinking flyout
        })
```

This allows the frontend to display the structured decision-making of orchestration agents (triage decisions, plans, reviews) while sub-agents only show their function calls.

---

## Usage

### Creating the Workflow

```python
from app.agent_factory.subagent_registry import get_registry
from app.agent_factory.workflows import create_dynamic_workflow

# Get registry (reads from subagent_config.py)
registry = get_registry()

# Create workflow with all agents wired together
workflow = create_dynamic_workflow(sub_registry=registry)

# Run workflow
result = await workflow.run(input=WorkflowInput(query="What's my leave balance?"))
```

### Adding a New Sub-Agent

1. Run `/onboard` to update `subagent_config.py`
2. `/onboard` generates `agents/sub_agents/{key}_agent.py` and `tools/{key}_tools.py`
3. Implement the tool functions in the tools file
4. Workflow automatically picks up the new agent

### Testing

```bash
# Verify registry loads correctly
uv run python -c "
from app.agent_factory.subagent_registry import get_registry
r = get_registry()
print('Domain:', r.domain_name)
print('Agents:', r.agent_keys)
print('Descriptions:', r.generate_descriptions())
"

# Verify orchestration agent config
uv run python -c "
from app.agent_factory.subagent_registry import get_registry
from app.agent_factory.agents.orchestration.triage_agent import TriageAgentConfig

r = get_registry()
config = TriageAgentConfig()
print('Prompt preview:')
print(config.build_prompt(r)[:500])
print()
print('Schema:', config.build_schema(r).__name__)
"
```
