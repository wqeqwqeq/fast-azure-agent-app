# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

GenericAI is a FastAPI-based multi-agent chat application with PostgreSQL/Redis storage and Azure OpenAI integration. It provides real-time SSE streaming for agent thinking/function execution and supports conversation persistence with write-through caching.

**Tech Stack:** Python 3.12, FastAPI, UV package manager, Microsoft Agent Framework, PostgreSQL (asyncpg), Redis, Azure (OpenAI, Key Vault, Identity)

## Development Commands

```bash
# Install dependencies
uv sync

# Run development server (with auto-reload)
uv run uvicorn app.main:app --reload

# Run production server
uv run uvicorn app.main:app --host 0.0.0.0 --port 8000

# Add new package
uv add <package-name>
```

## Architecture

### Directory Structure

- `app/core/` - Internal building blocks with no external dependencies (SSE event utilities)
- `app/infrastructure/` - External service integrations (Key Vault, PostgreSQL, Redis, AsyncChatHistoryManager)
- `app/routes/` - FastAPI API endpoints
- `app/schemas/` - Pydantic request/response models
- `app/dependencies.py` - FastAPI dependency injection (HistoryManagerDep, CurrentUserDep, SettingsDep)
- `app/config.py` - Pydantic Settings for environment configuration
- `app/opsagent/` - Agent orchestration business logic:
  - `agents/` - Agent implementations (triage, clarify, servicenow, log_analytics, etc.)
  - `workflows/` - Workflow composition (triage_workflow, dynamic_workflow)
  - `tools/` - Tool definitions for agents
  - `prompts/` - System prompts for agents
  - `middleware/observability.py` - Agent/function call tracking for SSE events
- `app/memory_agent/` - Conversation memory management:
  - `agent.py` - Memory summarization agent
  - `service.py` - MemoryService orchestrates context retrieval and background summarization
  - `backend.py` - PostgreSQL operations for memory table
  - `schemas.py` - Pydantic models (MemoryRecord, ConversationContext)

### Key Patterns

**Lifespan Management (app/main.py):** All shared resources (database connections, secrets, service clients) are created once at startup via async context manager and stored in `app.state`. Never create connections per-request.

**Dependency Injection:** Use typed dependencies from `app/dependencies.py`:
```python
async def endpoint(history: HistoryManagerDep, current_user: CurrentUserDep, settings: SettingsDep):
```

**Write-Through Caching (AsyncChatHistoryManager):** Writes go to PostgreSQL first (source of truth), then update Redis. Reads check Redis first, fallback to PostgreSQL on cache miss.

**SSE Streaming:** Single POST endpoint (`/conversations/{id}/messages`) returns `StreamingResponse` with events: `message`, `thinking` (agent_invoked, function_start, function_end, agent_finished), `done`.

**Workflow Modes:** Controlled by `DYNAMIC_PLAN` env var - triage workflow (default) uses classification routing, dynamic workflow uses flexible orchestration.

**Memory Management:** Automatic conversation memory summarization for long conversations. Older messages are summarized by LLM and stored in PostgreSQL. Uses rolling window (last 7 rounds) + memory context. Background `asyncio.create_task()` for non-blocking summarization.

### Adding New Components

**New Route:** Create file in `app/routes/`, include router in `app/main.py` with `app.include_router()`

**New Agent:** Add files to `app/opsagent/agents/`, `prompts/`, `schemas/`, and optionally `tools/`. Integrate into workflows.

**Configuration:** Add env vars to `.env` and `Settings` class in `app/config.py`

## Environment Configuration

Key settings in `.env`:
- `RESOURCE_PREFIX` - Used to derive Azure service names (Key Vault, PostgreSQL, Redis hostnames)
- `CHAT_HISTORY_MODE` - Storage mode: `local`, `postgres`, `redis`
- `DYNAMIC_PLAN` - Enable dynamic workflow vs triage workflow
- `SHOW_FUNC_RESULT` - Show function args/results in UI
- `MEMORY_ROLLING_WINDOW` - Number of recent messages to keep (default: 14 = 7 rounds)
- `MEMORY_SUMMARIZE_THRESHOLD` - Start summarizing after N rounds (default: 4)
- `MEMORY_MODEL` - Model for summarization (default: gpt-4.1-mini)

Secrets are pre-loaded from Azure Key Vault at startup: `POSTGRES-ADMIN-PASSWORD`, `REDIS-PASSWORD`, `AZURE-OPENAI-API-KEY`, `APPLICATIONINSIGHTS-CONNECTION-STRING`

## Deployment

```bash
# Deploy Azure infrastructure
./deployment/deploy_infra.sh rg              # Resource group only
./deployment/deploy_infra.sh app --postgres-password <password>  # Full infra

# Build container
./deployment/build_container.sh

# Deploy application
./deployment/deploy_script.sh
```
