"""Async PostgreSQL backend for chat history storage using asyncpg."""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

import asyncpg

logger = logging.getLogger(__name__)


class AsyncPostgreSQLBackend:
    """Async PostgreSQL backend for chat history storage.

    Stores conversations in two tables:
    - conversations: metadata (title, model, timestamps)
    - messages: individual chat messages with sequence numbers
    """

    def __init__(self) -> None:
        """Initialize PostgreSQL backend (pool created via connect())."""
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self, connection_string: str) -> None:
        """Create async connection pool.

        Args:
            connection_string: PostgreSQL connection string
                Format: postgresql://user:pass@host:port/dbname?sslmode=require
        """
        try:
            self.pool = await asyncpg.create_pool(
                connection_string,
                min_size=1,
                max_size=10,
            )
            logger.info("PostgreSQL connection pool created successfully")
        except Exception as e:
            logger.error(f"Failed to create PostgreSQL pool: {e}")
            raise RuntimeError(f"Failed to connect to PostgreSQL: {e}")

    async def close(self) -> None:
        """Close all connections in the pool."""
        if self.pool:
            await self.pool.close()
            logger.info("PostgreSQL connection pool closed")

    async def list_conversations(
        self, user_id: str, days: int = 7
    ) -> List[Tuple[str, Dict[str, Any]]]:
        """Return list of (conversation_id, conversation_metadata) for a user.

        Only returns conversations created within the last `days` days.
        Messages are NOT included in the returned data.

        Args:
            user_id: User client ID (Azure Entra ID or local test ID)
            days: Number of days of history to load (default: 7)

        Returns:
            List of (conversation_id, conversation_dict) tuples, sorted by last_modified DESC
        """
        if not self.pool:
            raise RuntimeError("PostgreSQL pool not initialized")

        cutoff_date = datetime.now(timezone.utc) - timedelta(days=days)

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT conversation_id, user_client_id, title, model,
                       created_at, last_modified
                FROM conversations
                WHERE user_client_id = $1
                  AND created_at >= $2
                ORDER BY last_modified DESC
                """,
                user_id,
                cutoff_date,
            )

            conversations = []
            for row in rows:
                convo = {
                    "title": row["title"],
                    "model": row["model"],
                    "messages": [],  # Empty - not loaded yet
                    "created_at": row["created_at"].isoformat(),
                    "last_modified": row["last_modified"].isoformat(),
                }
                conversations.append((row["conversation_id"], convo))

            return conversations

    async def get_conversation(
        self, conversation_id: str, user_id: str
    ) -> Optional[Dict[str, Any]]:
        """Load a single conversation with all messages.

        Args:
            conversation_id: Conversation ID
            user_id: User client ID (for security check)

        Returns:
            Conversation dict with messages, or None if not found
        """
        if not self.pool:
            raise RuntimeError("PostgreSQL pool not initialized")

        async with self.pool.acquire() as conn:
            # Get conversation metadata
            conv_row = await conn.fetchrow(
                """
                SELECT conversation_id, user_client_id, title, model,
                       agent_model_mapping, created_at, last_modified
                FROM conversations
                WHERE conversation_id = $1 AND user_client_id = $2
                """,
                conversation_id,
                user_id,
            )

            if not conv_row:
                return None

            # Get messages ordered by sequence number
            message_rows = await conn.fetch(
                """
                SELECT role, content, timestamp, sequence_number
                FROM messages
                WHERE conversation_id = $1
                ORDER BY sequence_number ASC
                """,
                conversation_id,
            )

            messages = [
                {
                    "role": msg["role"],
                    "content": msg["content"],
                    "time": msg["timestamp"].isoformat(),
                }
                for msg in message_rows
            ]

            return {
                "title": conv_row["title"],
                "model": conv_row["model"],
                "messages": messages,
                "created_at": conv_row["created_at"].isoformat(),
                "last_modified": conv_row["last_modified"].isoformat(),
                **({"agent_model_mapping": conv_row["agent_model_mapping"]} if conv_row["agent_model_mapping"] else {}),
            }

    async def save_conversation(
        self, conversation_id: str, user_id: str, conversation: Dict[str, Any]
    ) -> None:
        """Save a conversation with all messages atomically.

        Uses a transaction to:
        1. UPSERT conversation metadata
        2. DELETE old messages
        3. INSERT new messages with sequence numbers

        Args:
            conversation_id: Conversation ID
            user_id: User client ID
            conversation: Conversation dict with messages
        """
        if not self.pool:
            raise RuntimeError("PostgreSQL pool not initialized")

        # Parse timestamps
        created_at = datetime.fromisoformat(
            conversation.get("created_at", datetime.now(timezone.utc).isoformat())
        )
        last_modified = datetime.fromisoformat(
            conversation.get("last_modified", datetime.now(timezone.utc).isoformat())
        )

        # Handle optional agent_model_mapping field
        agent_model_mapping = conversation.get("agent_model_mapping")
        agent_model_mapping_json = json.dumps(agent_model_mapping) if agent_model_mapping else None

        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # UPSERT conversation metadata
                await conn.execute(
                    """
                    INSERT INTO conversations
                        (conversation_id, user_client_id, title, model,
                         agent_model_mapping, created_at, last_modified)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                    ON CONFLICT (conversation_id)
                    DO UPDATE SET
                        title = EXCLUDED.title,
                        model = EXCLUDED.model,
                        agent_model_mapping = EXCLUDED.agent_model_mapping,
                        last_modified = EXCLUDED.last_modified
                    """,
                    conversation_id,
                    user_id,
                    conversation["title"],
                    conversation["model"],
                    agent_model_mapping_json,
                    created_at,
                    last_modified,
                )

                # Delete old messages
                await conn.execute(
                    "DELETE FROM messages WHERE conversation_id = $1",
                    conversation_id,
                )

                # Insert new messages with sequence numbers
                messages = conversation.get("messages", [])
                for seq_num, msg in enumerate(messages):
                    timestamp = datetime.fromisoformat(
                        msg.get("time", datetime.now(timezone.utc).isoformat())
                    )

                    await conn.execute(
                        """
                        INSERT INTO messages
                            (conversation_id, sequence_number, role, content, timestamp)
                        VALUES ($1, $2, $3, $4, $5)
                        """,
                        conversation_id,
                        seq_num,
                        msg["role"],
                        msg["content"],
                        timestamp,
                    )

    async def delete_conversation(
        self, conversation_id: str, user_id: str
    ) -> None:
        """Delete a conversation and all its messages.

        Args:
            conversation_id: Conversation ID
            user_id: User client ID (for security check)
        """
        if not self.pool:
            raise RuntimeError("PostgreSQL pool not initialized")

        async with self.pool.acquire() as conn:
            # Messages are cascade-deleted by foreign key constraint
            await conn.execute(
                """
                DELETE FROM conversations
                WHERE conversation_id = $1 AND user_client_id = $2
                """,
                conversation_id,
                user_id,
            )

    async def set_message_evaluation(
        self,
        conversation_id: str,
        sequence_number: int,
        is_satisfy: bool,
        comment: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Set message evaluation (thumb up/down).

        Args:
            conversation_id: Conversation ID
            sequence_number: Message sequence number
            is_satisfy: True for thumb up, False for thumb down
            comment: Optional feedback comment

        Returns:
            Updated evaluation info, or None if message not found
        """
        if not self.pool:
            raise RuntimeError("PostgreSQL pool not initialized")

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE messages
                SET is_satisfy = $1, comment = $2
                WHERE conversation_id = $3 AND sequence_number = $4
                RETURNING conversation_id, sequence_number, is_satisfy, comment
                """,
                is_satisfy,
                comment,
                conversation_id,
                sequence_number,
            )
            return dict(row) if row else None

    async def clear_message_evaluation(
        self,
        conversation_id: str,
        sequence_number: int,
    ) -> Optional[Dict[str, Any]]:
        """Clear message evaluation (set is_satisfy and comment to NULL).

        Args:
            conversation_id: Conversation ID
            sequence_number: Message sequence number

        Returns:
            Updated evaluation info, or None if message not found
        """
        if not self.pool:
            raise RuntimeError("PostgreSQL pool not initialized")

        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                UPDATE messages
                SET is_satisfy = NULL, comment = NULL
                WHERE conversation_id = $1 AND sequence_number = $2
                RETURNING conversation_id, sequence_number, is_satisfy, comment
                """,
                conversation_id,
                sequence_number,
            )
            return dict(row) if row else None
