# Model Selection Feature

Two-level model selection allowing workflow-level and per-agent model configuration.

## Overview

The model dropdown in the top-left corner provides:
1. **Workflow Model**: Default model for all agents (GPT-4.1 or GPT-4.1-mini)
2. **Agent Overrides**: Optional per-agent model overrides

## User Interaction

1. Click model dropdown to open
2. Click a workflow model row to select it and expand agent list
3. Click again on selected model to collapse
4. Click agent's model button to see options (GPT-4.1 / GPT-4.1-mini)
5. Select agent model - submenu stays open for multiple selections
6. Badge shows count of active overrides

**Behavior:**
- Switching workflow model clears all agent overrides
- Switching ReAct mode clears all agent overrides and refreshes agent list

## Architecture

### Data Flow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  UI Dropdown    │────▶│  API Request    │────▶│  Backend        │
│                 │     │                 │     │                 │
│ selectedModel   │     │ workflow_model  │     │ create_workflow │
│ agentModelMapping│    │ agent_model_    │     │ (model_for())   │
│                 │     │ mapping         │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

### API Caching

Models and agents cached at startup to minimize API calls:

| Event | Models API | Agents API |
|-------|-----------|------------|
| Page load | 1x | 1x |
| Select model | 0x | 0x |
| Switch conversation | 0x | 0x |
| Toggle ReAct mode | 0x | 1x |

## Backend

### Model Registry (`app/opsagent/model_registry.py`)

```python
# Available models
AVAILABLE_MODELS = [GPT41, GPT41_MINI]
ModelName = Literal["gpt-4.1", "gpt-4.1-mini"]

# Agent lists by workflow type
TRIAGE_AGENTS = ["triage", "servicenow", "log_analytics", "service_health", "summary"]
DYNAMIC_AGENTS = ["triage", "servicenow", "log_analytics", "review", "clarify",
                  "plan", "service_health", "replan", "summary"]
```

### API Endpoints (`app/routes/models.py`)

```
GET /api/models
    Returns: {"models": ["gpt-4.1", "gpt-4.1-mini"]}

GET /api/agents?react_mode=false
    Returns: {"agents": [...]}  // 5 agents for triage

GET /api/agents?react_mode=true
    Returns: {"agents": [...]}  // 9 agents for dynamic
```

### Message Request (`app/routes/messages.py`)

```json
{
    "message": "User message",
    "react_mode": false,
    "workflow_model": "gpt-4.1",
    "agent_model_mapping": {
        "triage": "gpt-4.1-mini"
    }
}
```

## Frontend

### State (`app/static/js/state.js`)

```javascript
let selectedModel = 'gpt-4.1-mini';      // Current workflow model
let availableModels = [];                 // Cached from /api/models
let availableAgents = [];                 // Cached from /api/agents
let agentModelMapping = {};               // {"triage": "gpt-4.1-mini", ...}
```

### API (`app/static/js/api.js`)

- `fetchModels()` - Get available models
- `fetchAgents(reactMode)` - Get agents for workflow type
- `sendMessageStream()` - Includes `workflow_model` and `agent_model_mapping`

### UI (`app/static/js/ui.js`)

`renderModelSelector()` creates two-level dropdown:
- Workflow models with expand/collapse
- Agent rows with model selection buttons
- Inline updates without full re-render

### Handlers (`app/static/js/handlers.js`)

- Click outside closes all dropdowns
- ReAct toggle refreshes agents and clears overrides

### CSS (`app/static/css/main.css`)

Key classes:
- `.model-option-group` - Workflow model container
- `.workflow-model` - Clickable model row
- `.agent-submenu` - Collapsible agent list
- `.agent-model-btn` - Agent's model button
- `.agent-model-dropdown` - Model selection dropdown
- `.override-badge` - Gray badge for override count

## Files Modified

| File | Changes |
|------|---------|
| `app/opsagent/model_registry.py` | Added `TRIAGE_AGENTS`, `DYNAMIC_AGENTS` |
| `app/routes/models.py` | Added `react_mode` query param to `/agents` |
| `app/static/js/state.js` | Added model/agent caching state |
| `app/static/js/api.js` | Added `fetchAgents()`, updated `sendMessageStream()` |
| `app/static/js/main.js` | Cache models/agents at startup |
| `app/static/js/ui.js` | Two-level dropdown with inline updates |
| `app/static/js/handlers.js` | ReAct toggle clears overrides |
| `app/static/css/main.css` | Nested dropdown styles |
