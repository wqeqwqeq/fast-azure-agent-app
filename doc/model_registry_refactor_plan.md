# Model Registry Refactoring Plan

## Goal

Decouple model, workflow, and agent configurations to enable:
- Centralized model definitions via `ModelRegistry`
- Workflow-level agent-to-model mappings
- Agent-level model selection by name (not raw API credentials)

## 3 Modes

| Mode | Call | Use Case |
|------|------|----------|
| **Default** | `create_workflow()` | Local dev, devui |
| **Same Model** | `create_workflow(registry, workflow_model)` | User switches workflow-level model |
| **Specific** | `create_workflow(registry, workflow_model, agent_mapping)` | Per-agent customization |

**Priority**: `agent_mapping` > `workflow_model` > `env settings`

---

## Implementation

### 1. Model Registry (`app/opsagent/model_registry.py`)

```python
"""Model registry with centralized model definitions."""
from typing import TYPE_CHECKING, Optional
from pydantic import BaseModel

if TYPE_CHECKING:
    from app.infrastructure.keyvault import AKV


# --- Model Definitions ---
class GPT41:
    secret_name = 'AZURE-OPENAI-API-KEY'
    endpoint = 'https://stanleyai.cognitiveservices.azure.com/'
    deployment_name = 'gpt-4.1'
    display_name = 'GPT 4.1'


class GPT41Mini:
    secret_name = 'AZURE-OPENAI-API-KEY'
    endpoint = 'https://stanleyai.cognitiveservices.azure.com/'
    deployment_name = 'gpt-4.1-mini'
    display_name = 'GPT 4.1 Mini'


DEFAULT_MODEL = 'gpt-4.1'


# --- Model Registry ---
class ModelRegistry:
    """Registry that loads secrets at startup and resolves models."""

    REQUIRED_SECRETS = [
        'AZURE-OPENAI-API-KEY',
        # 'ANTHROPIC-API-KEY',  # future
    ]

    models = {
        'gpt-4.1': GPT41,
        'gpt-4.1-mini': GPT41Mini,
    }

    def __init__(self, akv: "AKV"):
        self._secrets: dict[str, str] = {}
        for secret_name in self.REQUIRED_SECRETS:
            self._secrets[secret_name] = akv.get_secret(secret_name)

    def get(self, model_name: str) -> dict:
        """Get resolved model config by name."""
        model_cls = self.models.get(model_name)
        if not model_cls:
            raise ValueError(f"Unknown model: {model_name}")
        return {
            'deployment_name': model_cls.deployment_name,
            'endpoint': model_cls.endpoint,
            'api_key': self._secrets[model_cls.secret_name],
        }


# --- Agent-Model Mapping ---
class AgentModelMapping(BaseModel):
    """Optional per-agent model override. None = use workflow_model."""
    triage: Optional[str] = None
    servicenow: Optional[str] = None
    log_analytics: Optional[str] = None
    service_health: Optional[str] = None
    review: Optional[str] = None
    clarify: Optional[str] = None
    dynamic_triage_user: Optional[str] = None
    dynamic_triage_review: Optional[str] = None


def resolve_agent_model(
    agent_key: str,
    workflow_model: Optional[str],
    agent_mapping: Optional[AgentModelMapping],
) -> str:
    """Resolve model for agent. Priority: mapping > workflow > default."""
    if agent_mapping:
        agent_model = getattr(agent_mapping, agent_key, None)
        if agent_model:
            return agent_model
    return workflow_model or DEFAULT_MODEL
```

### 2. Factory (`app/opsagent/factory.py`)

```python
def create_agent(
    name: str,
    description: str,
    instructions: str,
    registry: Optional[ModelRegistry] = None,
    model_name: Optional[str] = None,
    response_format: Optional[Type] = None,
    tools: Optional[List] = None,
) -> ChatAgent:
    """Create ChatAgent.

    Mode 1 (registry=None): Use env settings (AzOpenAIEnvSettings)
    Mode 2/3 (registry provided): Use registry.get(model_name)
    """
    if registry is None:
        # Mode 1: env settings for local dev
        env = AzOpenAIEnvSettings()
        api_key = env.azure_openai_api_key
        endpoint = env.azure_openai_endpoint
        deployment_name = env.azure_openai_deployment_name
    else:
        # Mode 2/3: registry
        resolved = registry.get(model_name or DEFAULT_MODEL)
        api_key = resolved['api_key']
        endpoint = resolved['endpoint']
        deployment_name = resolved['deployment_name']

    # ... create ChatAgent
```

### 3. Agent Factories

```python
def create_servicenow_agent(
    registry: Optional[ModelRegistry] = None,
    model_name: Optional[str] = None,
):
    return create_agent(
        name=CONFIG.name,
        description=CONFIG.description,
        instructions=CONFIG.instructions,
        registry=registry,
        model_name=model_name,
        tools=[...],
    )
```

### 4. Workflows

```python
def create_triage_workflow(
    registry: Optional[ModelRegistry] = None,
    workflow_model: Optional[str] = None,
    agent_mapping: Optional[AgentModelMapping] = None,
):
    if registry is None:
        # Mode 1: env settings
        triage = create_triage_agent()
        servicenow = create_servicenow_agent()
        ...
    else:
        # Mode 2 & 3: registry with model resolution
        triage = create_triage_agent(
            registry,
            resolve_agent_model('triage', workflow_model, agent_mapping)
        )
        servicenow = create_servicenow_agent(
            registry,
            resolve_agent_model('servicenow', workflow_model, agent_mapping)
        )
        ...
```

### 5. App Lifespan (`app/main.py`)

```python
from app.opsagent.model_registry import ModelRegistry

@asynccontextmanager
async def lifespan(app: FastAPI):
    akv = AKV(vault_name=app_settings.key_vault_name)
    akv.load_secrets(REQUIRED_SECRETS)
    app.state.keyvault = akv

    # Create ModelRegistry and store in app.state
    app.state.model_registry = ModelRegistry(akv)
    ...
```

### 6. Routes (`app/routes/messages.py`)

```python
async def send_message(...):
    registry = request.app.state.model_registry

    # Optional: parse from request body
    workflow_model = getattr(body, 'workflow_model', None)
    agent_mapping = getattr(body, 'agent_mapping', None)

    if settings.dynamic_plan:
        workflow = create_dynamic_workflow(registry, workflow_model, agent_mapping)
    else:
        workflow = create_triage_workflow(registry, workflow_model, agent_mapping)
```

---

## Files Changed

| File | Action |
|------|--------|
| `app/opsagent/model_registry.py` | **CREATE** |
| `app/opsagent/factory.py` | **UPDATE** - Support both env and registry modes |
| `app/opsagent/settings.py` | **SIMPLIFY** - Keep only AzOpenAIEnvSettings |
| `app/opsagent/__init__.py` | **UPDATE** - Export ModelRegistry, AgentModelMapping |
| `app/opsagent/agents/*.py` (7 files) | **UPDATE** - Optional registry + model_name |
| `app/opsagent/workflows/*.py` (2 files) | **UPDATE** - 3-mode support |
| `app/main.py` | **UPDATE** - Create ModelRegistry in lifespan |
| `app/routes/messages.py` | **UPDATE** - Use registry from app.state |
| `workflow_run/workflow_run_devui.py` | **NO CHANGE** - Mode 1 just works |

---

## Usage Examples

```python
# Mode 1: Local dev / DevUI (uses env settings)
workflow = create_triage_workflow()

# Mode 2: All agents use same model
registry = app.state.model_registry
workflow = create_triage_workflow(registry, "gpt-4.1-mini")

# Mode 3: Per-agent customization
workflow = create_triage_workflow(
    registry,
    "gpt-4.1",  # default for all
    AgentModelMapping(
        servicenow="gpt-4.1-mini",  # override
        log_analytics="gpt-4.1-mini",  # override
    )
)
```

---

## Adding New Models

To add a new model (e.g., Claude):

1. Add secret to `REQUIRED_SECRETS` in `model_registry.py`:
   ```python
   REQUIRED_SECRETS = [
       'AZURE-OPENAI-API-KEY',
       'ANTHROPIC-API-KEY',  # new
   ]
   ```

2. Define model class:
   ```python
   class Claude4Sonnet:
       secret_name = 'ANTHROPIC-API-KEY'
       endpoint = 'https://api.anthropic.com/'
       deployment_name = 'claude-sonnet-4-20250514'
       display_name = 'Claude 4 Sonnet'
   ```

3. Add to registry:
   ```python
   models = {
       'gpt-4.1': GPT41,
       'gpt-4.1-mini': GPT41Mini,
       'claude-4-sonnet': Claude4Sonnet,  # new
   }
   ```

4. Add secret to Azure Key Vault

---

## Verification

1. **Mode 1 (devui):**
   ```bash
   cd workflow_run && python workflow_run_devui.py
   ```

2. **Mode 2/3 (app):**
   ```bash
   uv run uvicorn app.main:app --reload
   ```
   - Send message to `/api/conversations/{id}/messages`
   - Verify SSE events stream correctly
