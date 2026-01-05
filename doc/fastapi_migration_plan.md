# FastAPI Migration Plan: OpsAgent Chat API

## Overview

Migrate Flask-based chat API from `opsagent2/flask_app.py` to FastAPI at `generic-ai/app/`.

**Key Requirements:**
- No local mode (PostgreSQL + Redis only)
- Write-through caching: Write to PostgreSQL first, then Redis
- Cache-aside reads: Redis first, PostgreSQL on miss
- Azure Easy Auth SSO support
- Both triage and dynamic workflows (via DYNAMIC_PLAN env var)

---

## Target File Structure

```
generic-ai/app/
├── main.py                    # FastAPI app with lifespan
├── config.py                  # Pydantic Settings
├── dependencies.py            # DI functions
├── db/
│   ├── __init__.py
│   ├── postgresql.py          # Async PostgreSQL backend (asyncpg)
│   ├── redis.py               # Async Redis backend (redis.asyncio)
│   └── manager.py             # AsyncChatHistoryManager
├── routes/
│   ├── __init__.py
│   ├── conversations.py       # CRUD endpoints
│   ├── messages.py            # POST messages + SSE thinking
│   ├── user.py                # GET /user
│   └── settings.py            # GET /models, /settings
├── schemas/
│   ├── __init__.py
│   ├── conversation.py        # ConversationCreate/Update/Response, MessageSchema
│   ├── message.py             # SendMessageRequest/Response
│   ├── user.py                # UserInfo
│   ├── settings.py            # SettingsResponse, ModelsResponse
│   └── events.py              # FunctionStartEvent, FunctionEndEvent, AgentInvokedEvent, AgentFinishedEvent
├── utils/
│   ├── __init__.py
│   └── event_stream.py        # AsyncEventStream for SSE (middleware events only)
└── opsagent/                  # (existing - unchanged)
```

**Note**: Video generation API (`/api/videos`) is excluded from this migration.

---

## Implementation Steps

### Phase 1: Configuration and Database Layer

**1.1 Create `app/config.py`**
- Pydantic Settings for: CHAT_HISTORY_MODE, RESOURCE_PREFIX, PostgreSQL/Redis config, DYNAMIC_PLAN

**1.2 Create `app/db/postgresql.py`**
- Async PostgreSQL backend using `asyncpg`
- Methods: `connect()`, `close()`, `list_conversations()`, `get_conversation()`, `save_conversation()`, `delete_conversation()`
- Source: Migrate from `opsagent2/opsagent/ui/app/storage/postgresql.py`

**1.3 Create `app/db/redis.py`**
- Async Redis backend using `redis.asyncio`
- Methods: cache get/set for conversations and messages
- Source: Migrate from `opsagent2/opsagent/ui/app/storage/redis.py`

**1.4 Create `app/db/manager.py`**
- AsyncChatHistoryManager orchestrating PostgreSQL + Redis
- Write-through: PostgreSQL first, then update Redis cache
- Cache-aside reads: Try Redis, fallback to PostgreSQL, populate cache
- Source: Migrate from `opsagent2/opsagent/ui/app/storage/manager.py`

### Phase 2: FastAPI Core

**2.1 Create `app/main.py`**
- FastAPI app with lifespan context manager
- Initialize PostgreSQL pool + Redis connection on startup
- Cleanup on shutdown
- CORS middleware
- Include routers from `app/routes/`

**2.2 Create `app/dependencies.py`**
- `get_history_manager()` - Returns AsyncChatHistoryManager
- `get_current_user()` - Extracts user from Azure Easy Auth headers
- `get_settings()` - Returns Settings instance

### Phase 3: Schemas (All API responses as Pydantic models)

**3.1 Create `app/schemas/conversation.py`**
```python
class MessageSchema(BaseModel):
    role: str
    content: str
    time: Optional[str] = None

class ConversationCreate(BaseModel):
    model: str = "gpt-4o-mini"

class ConversationUpdate(BaseModel):
    title: Optional[str] = None
    model: Optional[str] = None

class ConversationResponse(BaseModel):
    id: str
    title: str
    model: str
    messages: List[MessageSchema] = []
    created_at: str
    last_modified: str

class ConversationListResponse(BaseModel):
    conversations: List[ConversationResponse]
```

**3.2 Create `app/schemas/message.py`**
```python
class SendMessageRequest(BaseModel):
    message: str

class SendMessageResponse(BaseModel):
    user_message: MessageSchema
    assistant_message: MessageSchema
    title: str
```

**3.3 Create `app/schemas/user.py`**
```python
class UserInfo(BaseModel):
    user_id: str
    user_name: str
    first_name: Optional[str] = None
    principal_name: Optional[str] = None
    is_authenticated: bool
    mode: str
```

**3.4 Create `app/schemas/settings.py`**
```python
class SettingsResponse(BaseModel):
    show_func_result: bool

class ModelsResponse(BaseModel):
    models: List[str]
```

**3.5 Create `app/schemas/events.py`** (SSE event schemas)
```python
class FunctionStartEvent(BaseModel):
    type: Literal["function_start"] = "function_start"
    function: str
    arguments: Dict[str, Any]

class FunctionEndEvent(BaseModel):
    type: Literal["function_end"] = "function_end"
    function: str
    result: Any

class AgentInvokedEvent(BaseModel):
    type: Literal["agent_invoked"] = "agent_invoked"
    agent: str

class AgentFinishedEvent(BaseModel):
    type: Literal["agent_finished"] = "agent_finished"
    agent: str
```

### Phase 4: Routes (Priority APIs first)

**4.1 Create `app/routes/messages.py`** (Priority)
- `POST /api/conversations/{id}/messages` - Execute workflow, save response
- `GET /api/conversations/{id}/thinking` - SSE streaming endpoint

**4.2 Create `app/utils/event_stream.py`** (Required for custom middleware)
- AsyncEventStream class with `asyncio.Queue` (replaces `threading.Queue`)
- ContextVar for current stream access (replaces `threading.local`)
- **Event sources**: Middleware only (NOT framework `run_stream()`)
  - `observability_agent_middleware` → emits agent invocation/completion
  - `observability_function_middleware` → emits function start/end with args/result
  - Both middleware point to the same AsyncEventStream instance
- Source: Migrate from `opsagent2/opsagent/utils/observability.py`

**4.3 Create `app/routes/conversations.py`** (CRUD)
- `GET /api/conversations` - List conversations
- `POST /api/conversations` - Create conversation
- `GET /api/conversations/{id}` - Get conversation
- `PUT /api/conversations/{id}` - Update conversation
- `DELETE /api/conversations/{id}` - Delete conversation

**4.4 Create `app/routes/user.py`**
- `GET /api/user` - Get current user info

**4.5 Create `app/routes/settings.py`**
- `GET /api/models` - List available models (returns `ModelsResponse`)
- `GET /api/settings` - Get UI settings/feature flags (returns `SettingsResponse`)

### Phase 5: Update Middleware

**5.1 Update `app/opsagent/middleware/observability.py`**
- Change EventStream imports to use new `app/utils/event_stream.py`

---

## Critical Source Files to Reference

| Target File | Source Reference |
|-------------|------------------|
| `app/db/postgresql.py` | `opsagent2/opsagent/ui/app/storage/postgresql.py` |
| `app/db/redis.py` | `opsagent2/opsagent/ui/app/storage/redis.py` |
| `app/db/manager.py` | `opsagent2/opsagent/ui/app/storage/manager.py` |
| `app/utils/event_stream.py` | `opsagent2/opsagent/utils/observability.py` |
| `app/routes/*.py` | `opsagent2/flask_app.py` (lines 276-520) |

---

## Key Patterns

### Lifespan Manager
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await app_state.history_manager.initialize(postgres_conn, redis_config)
    yield
    await app_state.history_manager.close()
```

### Write-Through Save
```python
async def save_conversation(self, conversation_id, user_id, conversation):
    # 1. Write to PostgreSQL (source of truth)
    await self.backend.save_conversation(conversation_id, user_id, conversation)
    # 2. Update Redis cache
    if self.cache:
        await self.cache.update_conversation_metadata(user_id, conversation_id, conversation)
        await self.cache.set_conversation_messages(conversation_id, conversation['messages'])
```

### Cache-Aside Read
```python
async def get_conversation(self, conversation_id, user_id):
    # 1. Try cache first
    if self.cache:
        cached = await self.cache.get_conversation_messages(conversation_id, user_id)
        if cached:
            return cached
    # 2. Cache miss -> read from PostgreSQL
    conversation = await self.backend.get_conversation(conversation_id, user_id)
    # 3. Populate cache
    if conversation and self.cache:
        await self.cache.set_conversation_messages(conversation_id, conversation['messages'])
    return conversation
```

### SSE + Middleware Interaction Flow
```
Frontend connects to /thinking SSE endpoint
       ↓
AsyncEventStream created, stored in _active_streams[id]
       ↓
Frontend sends POST /messages (in parallel)
       ↓
set_current_stream(stream) → makes stream available to middleware
       ↓
workflow.run(input) starts
       ↓
observability_function_middleware runs:
  - stream.emit({"type": "function_start", ...})  ← pushed to asyncio.Queue
  - await next(context)  ← actual function executes
  - stream.emit({"type": "function_end", ...})    ← pushed to asyncio.Queue
       ↓
SSE endpoint yields events from queue → data: {...}\n\n
       ↓
workflow completes → stream.stop() → sentinel pushed → SSE ends
```

### SSE Endpoint
```python
@router.get("/conversations/{id}/thinking")
async def thinking_stream(id: str):
    async def event_generator():
        stream = AsyncEventStream()
        _active_streams[id] = stream
        await stream.start()
        yield ": connected\n\n"
        try:
            async for event in stream.iter_events():
                yield f"data: {event}\n\n"
        finally:
            del _active_streams[id]
    return StreamingResponse(event_generator(), media_type="text/event-stream")
```

### AsyncEventStream Implementation
```python
class AsyncEventStream:
    def __init__(self):
        self._queue: asyncio.Queue[Optional[str]] = asyncio.Queue()
        self._active = False

    async def start(self):
        self._active = True

    def emit(self, message: str):  # Sync method - called from middleware
        if self._active:
            self._queue.put_nowait(message)  # Non-blocking put

    async def stop(self):
        self._active = False
        await self._queue.put(None)  # Sentinel

    async def iter_events(self) -> AsyncIterator[str]:
        while True:
            event = await self._queue.get()  # Blocking wait
            if event is None:
                break
            yield event
```

---

## Dependencies to Add (pyproject.toml)

```toml
fastapi = ">=0.109.0"
uvicorn = { version = ">=0.27.0", extras = ["standard"] }
asyncpg = ">=0.29.0"
redis = ">=5.0.0"
pydantic-settings = ">=2.0.0"
```
