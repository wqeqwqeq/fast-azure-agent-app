# Lean Structure Evolution

This document records the refactoring journey from a verbose, over-engineered structure to a lean, pragmatic design for model configuration injection.

## TL;DR

| Phase | Commit | Key Decision | Files Changed |
|-------|--------|--------------|---------------|
| 1 | e9311b7 | Add ModelConfig injection with 3-level priority | +settings.py, +plan.md |
| 2 | 60ce009 | Inline prompt configs into agent files | -7 prompt files, +factory.py |
| 3 | 8bf7691 | Replace ModelConfig with ModelRegistry | -settings.py, +model_registry.py |
| 4 | 8479a63 | Remove empty utils/ directories | -2 dirs |
| 5 | (current) | Factory function for model resolver | refactor |

**Net result**: Deleted `prompts/`, `utils/`, `settings.py`. Added `model_registry.py`, `factory.py`.

---

## Phase 1: ModelConfig Injection (e9311b7)

### Original Plan (`model_config_injection_plan.md`)

Goal: Inject API credentials from Key Vault without global singleton.

```
Priority: agent_config > model_config > env
```

**Structure:**
```
app/opsagent/
├── prompts/           # 7 files - agent configs with deployment_name, api_key, endpoint
├── agents/            # 7 files - factories calling resolve_model_config()
├── settings.py        # ModelConfig, ResolvedModelConfig, resolve_model_config()
└── utils/settings.py  # AzOpenAIEnvSettings
```

**Problem identified:**
- `prompts/` and `agents/` are tightly coupled but in separate directories
- Each prompt config defines `deployment_name`, `api_key`, `endpoint` (redundant)
- 3-level priority resolution is over-engineered for actual use case

---

## Phase 2: Remove Prompt Directory (60ce009)

### Decision: Inline configs into agent files

**Rationale:**
- Agent config (name, description, instructions) and agent factory are always used together
- Separate files create unnecessary indirection
- "A file per concept" > "a directory per layer"

**Before:**
```
prompts/servicenow_agent.py  → ServiceNowAgentConfig
agents/servicenow_agent.py   → create_servicenow_agent() imports from prompts/
```

**After:**
```
agents/servicenow_agent.py   → ServiceNowAgentConfig + create_servicenow_agent()
```

**Also added:** `factory.py` with `create_agent()` - shared logic for ChatAgent creation.

**Result:** -7 prompt files, -1 prompts/__init__.py

---

## Phase 3: ModelRegistry (8bf7691)

### Decision: Replace ModelConfig with ModelRegistry

**Rationale:**
- Original design assumed per-agent model customization via prompt config
- Actual need: workflow-level model selection, occasional per-agent override
- ModelConfig's 3-level priority was never used in practice

**New design (`model_registry_refactor_plan.md`):**

```python
# 3 Modes
create_workflow()                                    # Mode 1: env settings (local dev)
create_workflow(registry, workflow_model)           # Mode 2: same model for all agents
create_workflow(registry, workflow_model, mapping)  # Mode 3: per-agent override
```

**Key components:**
```python
# model_registry.py
ModelName = Literal["gpt-4.1", "gpt-4.1-mini"]  # Type-safe model names
ModelRegistry        # Loads secrets at startup, resolves model → credentials
AgentModelMapping    # Optional per-agent overrides
```

**Result:** -settings.py, +model_registry.py

---

## Phase 4: Remove Empty Utils (8479a63)

After previous refactors, `utils/` directories were empty.

**Result:** -app/opsagent/utils/, -app/utils/

---

## Phase 5: Factory Function for Model Resolver (current)

### Decision: Use closure factory instead of method

**Problem:**
```python
# Every agent creation repeats the same 3 arguments
servicenow_agent = create_servicenow_agent(
    registry,
    registry.resolve_agent_model("servicenow", workflow_model, agent_mapping),
)
log_analytics_agent = create_log_analytics_agent(
    registry,
    registry.resolve_agent_model("log_analytics", workflow_model, agent_mapping),
)
```

**Issues:**
1. `resolve_agent_model()` doesn't use registry state - wrong location
2. Repetitive: `workflow_model` and `agent_mapping` passed every time
3. Verbose: 4 lines per agent

**Solution:** Factory function returning closure
```python
# model_registry.py
def create_model_resolver(
    workflow_model: ModelName,
    agent_mapping: Optional[AgentModelMapping] = None,
) -> Callable[[str], ModelName]:
    def resolve(agent_key: str) -> ModelName:
        if agent_mapping and (model := agent_mapping.get(agent_key)):
            return model
        return workflow_model
    return resolve
```

**After:**
```python
model_for = create_model_resolver(workflow_model, agent_mapping)

servicenow_agent = create_servicenow_agent(registry, model_for("servicenow"))
log_analytics_agent = create_log_analytics_agent(registry, model_for("log_analytics"))
service_health_agent = create_service_health_agent(registry, model_for("service_health"))
```

**Benefits:**
- Centralized logic in `model_registry.py`
- Concise call: `model_for("servicenow")`
- Closure captures `workflow_model` and `agent_mapping` once

---

## Final Structure

```
app/opsagent/
├── __init__.py
├── factory.py              # create_agent() - shared ChatAgent creation
├── model_registry.py       # ModelRegistry, ModelName, AgentModelMapping, create_model_resolver()
├── agents/
│   ├── __init__.py
│   ├── clarify_agent.py         # ClarifyAgentConfig + create_clarify_agent()
│   ├── dynamic_triage_agent.py
│   ├── log_analytics_agent.py
│   ├── review_agent.py
│   ├── service_health_agent.py
│   ├── servicenow_agent.py
│   └── triage_agent.py
├── middleware/
│   └── observability.py
├── schemas/                # Pydantic models for structured output
├── tools/                  # Tool functions for agents
└── workflows/
    ├── dynamic_workflow.py
    └── triage_workflow.py
```

**Deleted:**
- `prompts/` (7 files) - inlined into agents
- `settings.py` - replaced by model_registry.py
- `utils/` - empty after cleanup

---

## Key Design Principles

### 1. Colocation over separation
Agent config belongs with agent factory, not in separate `prompts/` directory.

### 2. YAGNI for priority chains
3-level priority (agent > workflow > env) was over-engineered. Actual need: workflow default + optional override.

### 3. Functions over methods when no state needed
`resolve_agent_model()` didn't use `self` - it was a pure function pretending to be a method.

### 4. Closures for repetitive parameters
When multiple calls share the same context, capture it in a closure.

### 5. Type safety with Literal
`ModelName = Literal["gpt-4.1", "gpt-4.1-mini"]` catches typos at type-check time.

---

## Usage Examples

```python
# Mode 1: Local dev (uses .env)
workflow = create_triage_workflow()

# Mode 2: All agents use same model
registry = app.state.model_registry
workflow = create_triage_workflow(registry, "gpt-4.1-mini")

# Mode 3: Per-agent customization
workflow = create_triage_workflow(
    registry,
    "gpt-4.1",  # default
    AgentModelMapping(servicenow="gpt-4.1-mini"),  # override
)
```

---

## Lessons Learned

1. **Start simple, add complexity when needed** - The original ModelConfig with 3-level priority was designed for flexibility that was never used.

2. **Directory structure should reflect actual dependencies** - `prompts/` and `agents/` were always changed together, so they should be together.

3. **Delete code aggressively** - Every deleted file is one less thing to maintain. The lean structure is easier to understand and modify.

4. **Type hints as documentation** - `ModelName` literal type makes valid values obvious without reading docs.
