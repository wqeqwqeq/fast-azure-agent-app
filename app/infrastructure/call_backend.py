"""PostgreSQL backend for call tracking storage."""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class CallRecord:
    """Represents a call record (agent or function call)."""

    conversation_id: str
    message_id: int
    agent_name: Optional[str] = None
    function_name: Optional[str] = None
    model: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    total_tokens: Optional[int] = None
    execution_time_ms: Optional[int] = None
    call_id: Optional[int] = None
    created_at: Optional[datetime] = None


class CallBackend:
    """Async PostgreSQL backend for call tracking.

    Tracks agent and function calls with token usage and timing metrics.
    """

    def __init__(self, pool: asyncpg.Pool):
        """Initialize with existing connection pool.

        Args:
            pool: asyncpg connection pool from main backend
        """
        self._pool = pool

    async def bulk_insert(self, records: list[dict]) -> None:
        """Insert multiple call records in a single transaction.

        Args:
            records: List of call record dictionaries
        """
        if not records:
            return

        async with self._pool.acquire() as conn:
            await conn.executemany(
                """
                INSERT INTO call (conversation_id, message_id, agent_name, function_name,
                                  model, input_tokens, output_tokens, total_tokens, execution_time_ms)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                """,
                [
                    (
                        r["conversation_id"],
                        r["message_id"],
                        r.get("agent_name"),
                        r.get("function_name"),
                        r.get("model"),
                        r.get("input_tokens"),
                        r.get("output_tokens"),
                        r.get("total_tokens"),
                        r.get("execution_time_ms"),
                    )
                    for r in records
                ],
            )
            logger.debug(f"Inserted {len(records)} call records")

    async def get_calls_by_message(self, message_id: int) -> list[CallRecord]:
        """Get all calls for a specific message.

        Args:
            message_id: Message ID

        Returns:
            List of CallRecord ordered by created_at ascending
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT call_id, conversation_id, message_id, agent_name, function_name,
                       model, input_tokens, output_tokens, total_tokens,
                       execution_time_ms, created_at
                FROM call
                WHERE message_id = $1
                ORDER BY created_at ASC
                """,
                message_id,
            )
            return [CallRecord(**dict(row)) for row in rows]

    async def get_calls_by_conversation(self, conversation_id: str) -> list[CallRecord]:
        """Get all calls for a conversation.

        Args:
            conversation_id: Conversation ID

        Returns:
            List of CallRecord ordered by created_at ascending
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT call_id, conversation_id, message_id, agent_name, function_name,
                       model, input_tokens, output_tokens, total_tokens,
                       execution_time_ms, created_at
                FROM call
                WHERE conversation_id = $1
                ORDER BY created_at ASC
                """,
                conversation_id,
            )
            return [CallRecord(**dict(row)) for row in rows]

    async def delete_old_calls(self, retention_days: int) -> int:
        """Delete calls older than retention_days.

        Args:
            retention_days: Number of days to retain calls

        Returns:
            Count of deleted rows
        """
        async with self._pool.acquire() as conn:
            result = await conn.execute(
                """
                DELETE FROM call
                WHERE created_at < NOW() - INTERVAL '1 day' * $1
                """,
                retention_days,
            )
            # result is like "DELETE 42"
            deleted_count = int(result.split()[-1])
            if deleted_count > 0:
                logger.info(f"Deleted {deleted_count} old call records")
            return deleted_count
