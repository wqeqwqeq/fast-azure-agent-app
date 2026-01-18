# Memory Agent

Automatic conversation memory management with sliding window summarization.

## Overview

The Memory Agent provides automatic summarization of conversation history using a **sliding window** approach. Instead of keeping all history, it maintains only the most recent N messages in the summary, while older messages are dropped. This prevents context overflow and reduces token usage while keeping the most relevant context.

**Key Features:**
- Sliding window: Only summarizes the most recent N messages
- Version chain: Each memory tracks its predecessor for audit trail
- Database-based concurrency: Uses status field to prevent duplicate tasks
- Background processing: Non-blocking summarization after each round

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        messages.py                               │
│  ┌──────────────────────┐     ┌──────────────────────┐         │
│  │ get_context_for_     │     │ trigger_summarization │         │
│  │ workflow()           │     │ _if_needed()          │         │
│  │ (at round START)     │     │ (at round END)        │         │
│  └──────────┬───────────┘     └──────────┬───────────┘         │
└─────────────┼─────────────────────────────┼─────────────────────┘
              │                              │
              ▼                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                      MemoryService                               │
│  • Get latest 'completed' memory + gap messages                 │
│  • Calculate sliding window range                                │
│  • Insert 'processing' record before background task            │
│  • Track version chain (base_memory_id)                         │
└─────────────────────────────────────────────────────────────────┘
              │                              │
              ▼                              ▼
┌──────────────────────┐     ┌────────────────────────────────────┐
│    MemoryBackend     │     │       Memory Agent (LLM)           │
│  • get_latest_memory │     │  • Incremental summarization       │
│    (status=completed)│     │  • Drop content outside window     │
│  • insert_memory     │     │  • Combine with base memory        │
│  • update_status     │     └────────────────────────────────────┘
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐
│   PostgreSQL         │
│   memory table       │
│   (with status &     │
│    base_memory_id)   │
└──────────────────────┘
```

## Configuration

Settings in `app/config.py`:

```python
# Memory feature settings (uses sequence numbers, not rounds)
memory_rolling_window_size: int = 14   # Window covers 14 messages (7 rounds)
memory_summarize_after_seq: int = 5    # Start summarizing when end_seq >= 5 (after round 3)
memory_model: str = "gpt-4.1-mini"     # Use mini model for faster/cheaper summarization
```

**Sequence number mapping:**
- Round 1 = seq 0-1 (user + assistant)
- Round 2 = seq 2-3
- Round 3 = seq 4-5 (summarization starts when seq 5 is saved)
- etc.

## Database Schema

```sql
CREATE TABLE IF NOT EXISTS memory (
    memory_id SERIAL PRIMARY KEY,
    conversation_id VARCHAR(50) NOT NULL REFERENCES conversations(conversation_id) ON DELETE CASCADE,
    memory_text TEXT NOT NULL,
    start_sequence INTEGER NOT NULL,           -- First message sequence in window
    end_sequence INTEGER NOT NULL,             -- Last message sequence in window
    base_memory_id INTEGER REFERENCES memory(memory_id),  -- Previous memory this was based on
    status VARCHAR(20) DEFAULT 'completed',    -- 'processing' | 'completed' | 'failed'
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    generation_time_ms INTEGER DEFAULT NULL    -- Observability: LLM call duration
);

-- Index for getting most recent COMPLETED memory
CREATE INDEX IF NOT EXISTS idx_memory_conversation_status
    ON memory (conversation_id, status, end_sequence DESC);
```

**Design decisions:**
- **Version chain**: `base_memory_id` tracks which memory was used as input (audit trail)
- **Status field**: Prevents concurrent summarization tasks for same conversation
- **Sliding window**: `start_sequence` increases as window slides forward
- **No empty rows**: Only write when actual summary exists

## How It Works

### Core Algorithms

#### 1. Trigger Condition (called AFTER each round ends)

```python
def should_trigger_summary(conversation_id: str, last_saved_seq: int) -> bool:
    # Check if enough messages
    if last_saved_seq < memory_summarize_after_seq:
        return False

    # Check if already processing
    if exists_memory(conversation_id, status='processing'):
        return False

    return True
```

#### 2. Sliding Window Calculation

```python
def calculate_summary_range(last_saved_seq: int) -> tuple[int, int]:
    end_seq = last_saved_seq
    start_seq = max(0, end_seq - memory_rolling_window_size + 1)

    # Ensure start_seq is even (don't split user/assistant pairs)
    if start_seq % 2 != 0:
        start_seq = start_seq + 1

    return (start_seq, end_seq)
```

**Examples with window_size=14:**

| last_saved_seq | Calculation | Result | Messages in Window |
|----------------|-------------|--------|-------------------|
| 5  | max(0, 5-14+1) = 0  | (0, 5)   | 6 messages (window not full) |
| 13 | max(0, 13-14+1) = 0 | (0, 13)  | 14 messages (window exactly full) |
| 15 | max(0, 15-14+1) = 2 | (2, 15)  | 14 messages, seq 0-1 dropped |
| 19 | max(0, 19-14+1) = 6 | (6, 19)  | 14 messages, seq 0-5 dropped |

#### 3. Read Memory (called at START of each round)

```python
def get_context_for_workflow(conversation_id: str, current_messages: list) -> Context:
    # Get latest COMPLETED memory only
    latest_memory = query("""
        SELECT * FROM memory
        WHERE conversation_id = %s AND status = 'completed'
        ORDER BY end_sequence DESC LIMIT 1
    """)

    if latest_memory:
        # Calculate gap: messages after memory but before current user message
        gap_start = latest_memory.end_sequence + 1
        gap_end = len(current_messages) - 2  # exclude current user message
        gap_messages = current_messages[gap_start:gap_end+1]
        return Context(memory_text=latest_memory.memory_text, gap_messages=gap_messages)
    else:
        # Fallback: use raw messages (no memory ready yet)
        return Context(memory_text=None, gap_messages=current_messages[:-1])
```

#### 4. Background Summarization

```python
async def do_summarization(memory_id: int, conversation_id: str,
                           start_seq: int, end_seq: int, base_memory_id: int | None):
    try:
        base_memory = get_memory_by_id(base_memory_id) if base_memory_id else None

        if base_memory:
            # Incremental: only fetch new messages since base
            new_messages_start = base_memory.end_sequence + 1
        else:
            new_messages_start = start_seq

        new_messages = get_messages(conversation_id, new_messages_start, end_seq)

        # Call LLM with sliding window context
        summary = llm_summarize(
            previous_summary=base_memory.memory_text if base_memory else None,
            new_messages=new_messages,
            window_start_seq=start_seq  # Tell LLM to drop content before this
        )

        update_memory(memory_id, status='completed', memory_text=summary)

    except Exception:
        update_memory(memory_id, status='failed')
```

### Data Flow Timeline

```
Round 3 ends (seq 5 saved):
├─ Check: seq 5 >= threshold 5 ✅
├─ Check: no 'processing' task ✅
├─ Calculate range: (0, 5)
├─ Insert: memory(id=1, start=0, end=5, base_id=null, status='processing')
└─ Start background task

Round 4 starts:
├─ Query: completed memory → none yet (id=1 still processing)
├─ Fallback: use raw messages seq 0-6
└─ Respond to user

Round 4 ends (seq 7 saved):
├─ Check: id=1 still 'processing' → skip trigger
└─ No new task created

Round 5 starts:
├─ Query: completed memory → id=1 now completed (end_seq=5)
├─ Gap messages: seq 6-8 (round 4 + current user)
├─ Context: memory_text(id=1) + gap_messages
└─ Respond to user

Round 5 ends (seq 9 saved):
├─ Check: no 'processing' ✅
├─ Calculate range: max(0, 9-14+1) = 0 → (0, 9)
├─ Insert: memory(id=2, start=0, end=9, base_id=1, status='processing')
└─ Start background task (incremental from id=1)

... continues ...

Round 8 ends (seq 15 saved):
├─ Calculate range: max(0, 15-14+1) = 2 → (2, 15)  # SLIDING STARTS
├─ Insert: memory(id=X, start=2, end=15, base_id=..., status='processing')
└─ Summarization will DROP Round 1 (seq 0-1) content
```

### Memory Table Evolution

```
| id | start | end | base_id | status    | covers              |
|----|-------|-----|---------|-----------|---------------------|
| 1  | 0     | 5   | null    | completed | Round 1-3           |
| 2  | 0     | 9   | 1       | completed | Round 1-5           |
| 3  | 0     | 13  | 2       | completed | Round 1-7           |
| 4  | 2     | 15  | 3       | completed | Round 2-8 (R1 dropped) |
| 5  | 6     | 19  | 4       | completed | Round 4-10 (R1-3 dropped) |
```

**Key insight**: As `start_sequence` increases, older content is dropped from the summary. The sliding window ensures constant memory size regardless of conversation length.

## Files

| File | Description |
|------|-------------|
| `schemas.py` | Pydantic models: `MemoryRecord` (with status, base_memory_id), `MemorySummaryOutput`, `ConversationContext` |
| `backend.py` | PostgreSQL operations: `get_latest_memory` (status filter), `insert_memory`, `update_status` |
| `agent.py` | Memory agent with incremental summarization prompt |
| `service.py` | `MemoryService` - orchestrator with sliding window calculation |
| `__init__.py` | Module exports |

## Observability

### Database Queries

```sql
-- Get memory history with version chain
SELECT m.*,
       b.end_sequence as base_end_seq
FROM memory m
LEFT JOIN memory b ON m.base_memory_id = b.memory_id
WHERE m.conversation_id = 'conv_123'
ORDER BY m.end_sequence DESC;

-- Check for stuck 'processing' tasks
SELECT conversation_id, memory_id, created_at,
       NOW() - created_at as age
FROM memory
WHERE status = 'processing'
  AND created_at < NOW() - INTERVAL '5 minutes';

-- Monitor sliding window progression
SELECT
    conversation_id,
    start_sequence,
    end_sequence,
    end_sequence - start_sequence + 1 as window_size,
    generation_time_ms
FROM memory
WHERE status = 'completed'
ORDER BY created_at DESC
LIMIT 20;

-- Average summarization time
SELECT
    AVG(generation_time_ms) as avg_ms,
    MAX(generation_time_ms) as max_ms,
    COUNT(*) as total_summaries
FROM memory
WHERE status = 'completed'
  AND generation_time_ms IS NOT NULL;
```

### Logs

The memory service logs at INFO level:
- `Summarized messages {start}-{end} for {conversation_id} in {ms}ms`
- `Sliding window: dropping seq 0-{start-1} for {conversation_id}`

At DEBUG level:
- `No new messages to summarize for {conversation_id}`
- `Summarization already in progress for {conversation_id}`
- `Memory {id} status updated to {status}`

## Usage Example

The memory service is automatically used in `messages.py`:

```python
# At round START: get context before workflow
context = await memory_service.get_context_for_workflow(
    conversation_id, messages
)

# Prepend memory to first user message
if context.memory_text:
    content = f"[Previous context: {context.memory_text}]\n\n{content}"

# Include gap messages in context
workflow_messages = context.gap_messages + [current_message]

# ... run workflow ...

# At round END: trigger background summarization
memory_service.trigger_summarization_if_needed(
    conversation_id,
    last_saved_seq=new_assistant_message.sequence_number
)
```

## Testing

To test the memory feature:

1. Create a conversation with 4+ rounds (8+ messages)
2. Check the `memory` table:
   ```sql
   SELECT memory_id, start_sequence, end_sequence, base_memory_id, status
   FROM memory
   WHERE conversation_id = 'your_conv_id'
   ORDER BY memory_id;
   ```
3. Verify version chain: each row's `base_memory_id` points to previous row
4. Continue conversation to 8+ rounds and verify sliding window:
   - `start_sequence` should increase as window slides
5. Check for no concurrent tasks (only one 'processing' at a time)
