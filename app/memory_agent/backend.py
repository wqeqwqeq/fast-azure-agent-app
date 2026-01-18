"""PostgreSQL backend for memory storage."""

import logging
from datetime import datetime, timezone
from typing import Optional

import asyncpg

from .schemas import MemoryRecord

logger = logging.getLogger(__name__)


class MemoryBackend:
    """Async PostgreSQL backend for memory storage.

    Uses append-only pattern - each summarization creates a new row.
    Empty summaries are NOT written.
    """

    def __init__(self, pool: asyncpg.Pool):
        """Initialize with existing connection pool.

        Args:
            pool: asyncpg connection pool from main backend
        """
        self.pool = pool

    async def get_latest_memory(self, conversation_id: str) -> Optional[MemoryRecord]:
        """Get the most recent memory record for a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            MemoryRecord if exists, None otherwise
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT memory_id, conversation_id, memory_text,
                       start_sequence, end_sequence, created_at, generation_time_ms
                FROM memory
                WHERE conversation_id = $1
                ORDER BY end_sequence DESC
                LIMIT 1
                """,
                conversation_id,
            )

            if not row:
                return None

            return MemoryRecord(
                memory_id=row["memory_id"],
                conversation_id=row["conversation_id"],
                memory_text=row["memory_text"],
                start_sequence=row["start_sequence"],
                end_sequence=row["end_sequence"],
                created_at=row["created_at"],
                generation_time_ms=row["generation_time_ms"],
            )

    async def insert_memory(
        self,
        conversation_id: str,
        memory_text: str,
        start_sequence: int,
        end_sequence: int,
        generation_time_ms: Optional[int] = None,
    ) -> int:
        """Insert a new memory record (append-only).

        Only call this when memory_text is non-empty.

        Args:
            conversation_id: Conversation ID
            memory_text: Summarized memory text
            start_sequence: First message sequence included
            end_sequence: Last message sequence included
            generation_time_ms: How long summarization took

        Returns:
            The new memory_id
        """
        if not memory_text or not memory_text.strip():
            raise ValueError("Cannot insert empty memory")

        now = datetime.now(timezone.utc)

        async with self.pool.acquire() as conn:
            memory_id = await conn.fetchval(
                """
                INSERT INTO memory
                    (conversation_id, memory_text, start_sequence, end_sequence,
                     created_at, generation_time_ms)
                VALUES ($1, $2, $3, $4, $5, $6)
                RETURNING memory_id
                """,
                conversation_id,
                memory_text.strip(),
                start_sequence,
                end_sequence,
                now,
                generation_time_ms,
            )
            logger.debug(
                f"Inserted memory for conversation {conversation_id}: "
                f"seq {start_sequence}-{end_sequence}, {generation_time_ms}ms"
            )
            return memory_id

    async def get_memory_history(
        self, conversation_id: str, limit: int = 10
    ) -> list[MemoryRecord]:
        """Get memory history for a conversation (for debugging/observability).

        Args:
            conversation_id: Conversation ID
            limit: Maximum number of records to return

        Returns:
            List of MemoryRecord ordered by end_sequence descending
        """
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT memory_id, conversation_id, memory_text,
                       start_sequence, end_sequence, created_at, generation_time_ms
                FROM memory
                WHERE conversation_id = $1
                ORDER BY end_sequence DESC
                LIMIT $2
                """,
                conversation_id,
                limit,
            )

            return [
                MemoryRecord(
                    memory_id=row["memory_id"],
                    conversation_id=row["conversation_id"],
                    memory_text=row["memory_text"],
                    start_sequence=row["start_sequence"],
                    end_sequence=row["end_sequence"],
                    created_at=row["created_at"],
                    generation_time_ms=row["generation_time_ms"],
                )
                for row in rows
            ]
