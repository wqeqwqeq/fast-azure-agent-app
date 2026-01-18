"""PostgreSQL backend for memory storage."""

import logging
from datetime import datetime, timezone
from typing import Optional

import asyncpg

from .schemas import MemoryRecord

logger = logging.getLogger(__name__)


class MemoryBackend:
    """Async PostgreSQL backend for memory storage.

    Uses append-only pattern with version chain (base_memory_id).
    Uses status field for database-based concurrency control.
    """

    def __init__(self, pool: asyncpg.Pool):
        """Initialize with existing connection pool.

        Args:
            pool: asyncpg connection pool from main backend
        """
        self.pool = pool

    async def get_latest_memory(
        self, conversation_id: str, status: str = "completed"
    ) -> Optional[MemoryRecord]:
        """Get the most recent memory record for a conversation with given status.

        Args:
            conversation_id: Conversation ID
            status: Filter by status (default: 'completed')

        Returns:
            MemoryRecord if exists, None otherwise
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT memory_id, conversation_id, memory_text,
                       start_sequence, end_sequence, base_memory_id, status,
                       created_at, generation_time_ms
                FROM memory
                WHERE conversation_id = $1 AND status = $2
                ORDER BY end_sequence DESC
                LIMIT 1
                """,
                conversation_id,
                status,
            )

            if not row:
                return None

            return MemoryRecord(
                memory_id=row["memory_id"],
                conversation_id=row["conversation_id"],
                memory_text=row["memory_text"],
                start_sequence=row["start_sequence"],
                end_sequence=row["end_sequence"],
                base_memory_id=row["base_memory_id"],
                status=row["status"],
                created_at=row["created_at"],
                generation_time_ms=row["generation_time_ms"],
            )

    async def get_memory_by_id(self, memory_id: int) -> Optional[MemoryRecord]:
        """Get a memory record by ID.

        Args:
            memory_id: Memory ID

        Returns:
            MemoryRecord if exists, None otherwise
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT memory_id, conversation_id, memory_text,
                       start_sequence, end_sequence, base_memory_id, status,
                       created_at, generation_time_ms
                FROM memory
                WHERE memory_id = $1
                """,
                memory_id,
            )

            if not row:
                return None

            return MemoryRecord(
                memory_id=row["memory_id"],
                conversation_id=row["conversation_id"],
                memory_text=row["memory_text"],
                start_sequence=row["start_sequence"],
                end_sequence=row["end_sequence"],
                base_memory_id=row["base_memory_id"],
                status=row["status"],
                created_at=row["created_at"],
                generation_time_ms=row["generation_time_ms"],
            )

    async def exists_processing(self, conversation_id: str) -> bool:
        """Check if there's a 'processing' memory record for a conversation.

        Used to prevent concurrent summarization tasks.

        Args:
            conversation_id: Conversation ID

        Returns:
            True if a 'processing' record exists
        """
        async with self.pool.acquire() as conn:
            result = await conn.fetchval(
                """
                SELECT EXISTS(
                    SELECT 1 FROM memory
                    WHERE conversation_id = $1 AND status = 'processing'
                )
                """,
                conversation_id,
            )
            return result

    async def insert_memory(
        self,
        conversation_id: str,
        memory_text: str,
        start_sequence: int,
        end_sequence: int,
        base_memory_id: Optional[int] = None,
        status: str = "completed",
        generation_time_ms: Optional[int] = None,
    ) -> int:
        """Insert a new memory record.

        Args:
            conversation_id: Conversation ID
            memory_text: Summarized memory text (can be empty for 'processing' status)
            start_sequence: First message sequence in window
            end_sequence: Last message sequence in window
            base_memory_id: Previous memory this is based on (version chain)
            status: Status ('processing', 'completed', 'failed')
            generation_time_ms: How long summarization took

        Returns:
            The new memory_id
        """
        # Only validate non-empty text for completed status
        if status == "completed" and (not memory_text or not memory_text.strip()):
            raise ValueError("Cannot insert completed memory with empty text")

        now = datetime.now(timezone.utc)

        async with self.pool.acquire() as conn:
            memory_id = await conn.fetchval(
                """
                INSERT INTO memory
                    (conversation_id, memory_text, start_sequence, end_sequence,
                     base_memory_id, status, created_at, generation_time_ms)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING memory_id
                """,
                conversation_id,
                memory_text.strip() if memory_text else "",
                start_sequence,
                end_sequence,
                base_memory_id,
                status,
                now,
                generation_time_ms,
            )
            logger.debug(
                f"Inserted memory for conversation {conversation_id}: "
                f"seq {start_sequence}-{end_sequence}, status={status}"
            )
            return memory_id

    async def update_memory_status(
        self,
        memory_id: int,
        status: str,
        memory_text: Optional[str] = None,
        generation_time_ms: Optional[int] = None,
    ) -> None:
        """Update the status and optionally text of a memory record.

        Args:
            memory_id: Memory ID to update
            status: New status ('completed' or 'failed')
            memory_text: Summary text (required for 'completed' status)
            generation_time_ms: How long summarization took
        """
        if status == "completed" and (not memory_text or not memory_text.strip()):
            raise ValueError("Cannot mark memory as completed with empty text")

        async with self.pool.acquire() as conn:
            if memory_text is not None:
                await conn.execute(
                    """
                    UPDATE memory
                    SET status = $1, memory_text = $2, generation_time_ms = $3
                    WHERE memory_id = $4
                    """,
                    status,
                    memory_text.strip(),
                    generation_time_ms,
                    memory_id,
                )
            else:
                await conn.execute(
                    """
                    UPDATE memory
                    SET status = $1, generation_time_ms = $2
                    WHERE memory_id = $3
                    """,
                    status,
                    generation_time_ms,
                    memory_id,
                )
            logger.debug(f"Memory {memory_id} status updated to {status}")

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
                       start_sequence, end_sequence, base_memory_id, status,
                       created_at, generation_time_ms
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
                    base_memory_id=row["base_memory_id"],
                    status=row["status"],
                    created_at=row["created_at"],
                    generation_time_ms=row["generation_time_ms"],
                )
                for row in rows
            ]
