# Plan: Optional Model Injection for Agents and Workflows

## Summary

Add optional `ModelConfig` injection to all agents and workflows, allowing dynamic override of `deployment_name`, `api_key`, and `endpoint`.

**Key Design Decisions:**
- No global singleton - API key injected from backend
- `deployment_name` and `endpoint` fallback to environment variables
- Resolution happens at agent level (each agent can have different config)

## Architecture

### Priority Order (Highest to Lowest)

1. **Agent prompt config** - 每个 agent 在 prompts/ 里定义的 deployment_name, api_key, endpoint
2. **Injected ModelConfig** - 通过参数注入的配置
3. **Environment variables** - `AzOpenAIEnvSettings` 从 env 读取

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│ main.py (startup)                                                    │
│   app.state.azure_openai_api_key = akv.get_secret("AZURE-OPENAI-*") │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ messages.py (per request)                                            │
│   model_config = ModelConfig(                                        │
│       api_key=request.app.state.azure_openai_api_key                │
│   )                                                                  │
│   workflow = create_triage_workflow(model_config)                   │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ triage_workflow.py                                                   │
│   def create_triage_workflow(model_config):                         │
│       triage = create_triage_agent(model_config)                    │
│       servicenow = create_servicenow_agent(model_config)            │
│       ...                                                            │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ triage_agent.py (per agent)                                          │
│   def create_triage_agent(model_config):                            │
│       resolved = resolve_model_config(                              │
│           model_config=model_config,          # api_key from inject │
│           agent_config_deployment=TRIAGE_AGENT.deployment_name,     │
│           agent_config_api_key=TRIAGE_AGENT.api_key,                │
│           agent_config_endpoint=TRIAGE_AGENT.endpoint,              │
│       )                                                              │
│       # resolved.api_key = injected api_key                         │
│       # resolved.deployment_name = agent config or env              │
│       # resolved.endpoint = agent config or env                     │
└─────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────┐
│ settings.py: resolve_model_config()                                  │
│   env_settings = AzOpenAIEnvSettings()  # reads from .env           │
│   return ResolvedModelConfig(                                        │
│       deployment_name = agent_config or model_config or env,        │
│       api_key = agent_config or model_config or env,                │
│       endpoint = agent_config or model_config or env,               │
│   )                                                                  │
└─────────────────────────────────────────────────────────────────────┘
```

## Core Components

### `app/opsagent/settings.py`

```python
class AzOpenAIEnvSettings(BaseSettings):
    """Reads from environment variables - lowest priority fallback."""
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    azure_openai_api_key: str = ""
    azure_openai_endpoint: str = ""
    azure_openai_deployment_name: str = ""


@dataclass(frozen=True)
class ModelConfig:
    """Optional injection config - all fields optional."""
    deployment_name: Optional[str] = None
    api_key: Optional[str] = None
    endpoint: Optional[str] = None


@dataclass(frozen=True)
class ResolvedModelConfig:
    """Fully resolved config - all fields guaranteed."""
    deployment_name: str
    api_key: str
    endpoint: str


def resolve_model_config(
    model_config: Optional[ModelConfig] = None,
    agent_config_deployment: str = "",
    agent_config_api_key: str = "",
    agent_config_endpoint: str = "",
) -> ResolvedModelConfig:
    """Resolve with priority: agent_config > model_config > env."""
    env_settings = AzOpenAIEnvSettings()

    return ResolvedModelConfig(
        deployment_name=(
            agent_config_deployment
            or (model_config.deployment_name if model_config else None)
            or env_settings.azure_openai_deployment_name
        ),
        api_key=(
            agent_config_api_key
            or (model_config.api_key if model_config else None)
            or env_settings.azure_openai_api_key
        ),
        endpoint=(
            agent_config_endpoint
            or (model_config.endpoint if model_config else None)
            or env_settings.azure_openai_endpoint
        ),
    )
```

### Agent Prompt Config

```python
# prompts/triage_agent.py
@dataclass(frozen=True)
class TriageAgentConfig:
    name: str = "triage-agent"
    description: str = "..."
    deployment_name: str = ""      # optional per-agent model
    api_key: str = ""              # optional per-agent api key
    endpoint: str = ""             # optional per-agent endpoint
    instructions: str = "..."
```

### Agent Factory

```python
# agents/triage_agent.py
def create_triage_agent(model_config: Optional[ModelConfig] = None) -> ChatAgent:
    resolved = resolve_model_config(
        model_config=model_config,
        agent_config_deployment=TRIAGE_AGENT.deployment_name,
        agent_config_api_key=TRIAGE_AGENT.api_key,
        agent_config_endpoint=TRIAGE_AGENT.endpoint,
    )

    chat_client = AzureOpenAIChatClient(
        api_key=resolved.api_key,
        endpoint=resolved.endpoint,
        deployment_name=resolved.deployment_name,
    )
    ...
```

### Workflow Factory

```python
# workflows/triage_workflow.py
def create_triage_workflow(model_config: Optional[ModelConfig] = None):
    triage = create_triage_agent(model_config)
    servicenow = create_servicenow_agent(model_config)
    log_analytics = create_log_analytics_agent(model_config)
    service_health = create_service_health_agent(model_config)
    ...
```

## Backend Integration

### `app/main.py`

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    ...
    # Store Azure OpenAI API key for injection into workflows
    app.state.azure_openai_api_key = akv.get_secret("AZURE-OPENAI-API-KEY")
    ...
```

### `app/routes/messages.py`

```python
from ..opsagent.settings import ModelConfig

@router.post("/conversations/{conversation_id}/messages")
async def send_message(
    conversation_id: str,
    body: SendMessageRequest,
    request: Request,  # Added to access app.state
    history: HistoryManagerDep,
    current_user: CurrentUserDep,
):
    ...
    # Create model config with API key from app state
    model_config = ModelConfig(
        api_key=request.app.state.azure_openai_api_key
    )

    # Create fresh workflow for this request
    if settings.dynamic_plan:
        workflow = create_dynamic_workflow(model_config)
    else:
        workflow = create_triage_workflow(model_config)
    ...
```

## Files Modified

| File | Changes |
|------|---------|
| `app/opsagent/settings.py` | New file with ModelConfig, ResolvedModelConfig, resolve_model_config, AzOpenAIEnvSettings |
| `app/opsagent/prompts/*.py` (7 files) | Added api_key, endpoint fields |
| `app/opsagent/agents/*.py` (7 files) | Added model_config parameter, use resolve_model_config |
| `app/opsagent/workflows/*.py` (2 files) | Added model_config parameter, pass to agents |
| `app/main.py` | Store api_key in app.state (removed singleton init) |
| `app/routes/messages.py` | Create ModelConfig and inject into workflow |
| `app/opsagent/utils/__init__.py` | Updated exports |
| `app/opsagent/__init__.py` | Export ModelConfig, ResolvedModelConfig |

## Usage Examples

```python
# Default: api_key from Key Vault, deployment_name/endpoint from env
workflow = create_triage_workflow(
    ModelConfig(api_key=app.state.azure_openai_api_key)
)

# Override deployment for all agents
workflow = create_triage_workflow(
    ModelConfig(
        api_key=app.state.azure_openai_api_key,
        deployment_name="gpt-4o"
    )
)

# Full override (multi-tenant)
workflow = create_triage_workflow(
    ModelConfig(
        deployment_name="tenant-gpt4",
        api_key=tenant_api_key,
        endpoint=tenant_endpoint,
    )
)
```

## Future Expansion

如果需要 per-conversation model selection:

```python
# messages.py
model_config = ModelConfig(
    api_key=request.app.state.azure_openai_api_key,
    deployment_name=convo.get("model"),  # from conversation settings
)
```

## Verification

```bash
# Verify imports
uv run python -c "from app.opsagent.settings import resolve_model_config, ModelConfig, AzOpenAIEnvSettings; print('OK')"

# Verify full app
uv run python -c "from app.main import app; print('OK')"

# Run server
uv run uvicorn app.main:app --reload
```
